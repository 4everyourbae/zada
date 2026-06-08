"""ANTIGRAVITY Control Panel - dashboard web lokal (Flask).

Semua tool dikontrol dari localhost:8421:
  - status 9router + ringkasan akun
  - kelola koneksi (toggle aktif, test, delete)
  - cek credit antigravity (paralel)
  - jalankan login Gmail / daftar antigravity dengan log live (SSE)
  - editor accounts.txt
"""
import os
import io
import json
import time
import queue
import threading
import contextlib

from flask import Flask, render_template, jsonify, request, Response

from . import antigravity_login as ag
from . import gmail_login as g
from . import antigravity_credits as cred
from . import paths

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8421

app = Flask(__name__,
            template_folder=paths.TEMPLATES_DIR,
            static_folder=paths.STATIC_DIR)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True


@app.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

# ----------------- Job manager (untuk log live via SSE) -----------------
_jobs = {}
_jobs_lock = threading.Lock()


class Job:
    def __init__(self, name):
        self.name = name
        self.q = queue.Queue()
        self.done = False

    def emit(self, line):
        self.q.put(line)

    def finish(self):
        self.done = True
        self.q.put(None)


def _new_job(name):
    job_id = "{}-{}".format(name, int(time.time() * 1000))
    with _jobs_lock:
        _jobs[job_id] = Job(name)
    return job_id


def _get_job(job_id):
    with _jobs_lock:
        return _jobs.get(job_id)


def _token():
    return ag.get_cli_token()


# ----------------- Pages -----------------
@app.route("/")
def index():
    return render_template("index.html")


# ----------------- Status & accounts -----------------
@app.route("/api/status")
def api_status():
    tok = _token()
    if not tok:
        return jsonify({"online": False, "reason": "cli-token tidak tersedia"})
    alive = ag.server_alive(tok)
    if not alive:
        return jsonify({"online": False, "reason": "server 9router mati"})
    ok, data = ag.api_request("GET", "/api/providers", tok)
    conns = (data.get("connections") or []) if ok else []
    by_prov = {}
    active = 0
    for c in conns:
        p = c.get("provider") or c.get("providerId") or "?"
        by_prov[p] = by_prov.get(p, 0) + 1
        if c.get("isActive"):
            active += 1
    return jsonify({
        "online": True,
        "total": len(conns),
        "active": active,
        "byProvider": by_prov,
    })


@app.route("/api/accounts")
def api_accounts():
    tok = _token()
    ok, data = ag.api_request("GET", "/api/providers", tok)
    if not ok:
        return jsonify({"error": str(data)}), 502
    conns = data.get("connections") or []
    out = []
    for c in conns:
        out.append({
            "id": c.get("id"),
            "provider": c.get("provider") or c.get("providerId"),
            "email": c.get("email") or c.get("name") or "(tanpa email)",
            "isActive": bool(c.get("isActive")),
            "testStatus": c.get("testStatus") or "?",
            "priority": c.get("priority") or 999,
        })
    out.sort(key=lambda x: (x["provider"], x["priority"], x["email"]))
    return jsonify({"accounts": out})


@app.route("/api/accounts/<cid>/toggle", methods=["POST"])
def api_toggle(cid):
    tok = _token()
    want = request.json.get("active") if request.is_json else None
    ok, data = ag.api_request("PUT", "/api/providers/{}".format(cid), tok, {"isActive": bool(want)})
    return jsonify({"ok": ok, "data": data if ok else str(data)})


@app.route("/api/accounts/<cid>/test", methods=["POST"])
def api_test(cid):
    tok = _token()
    ok, data = ag.api_request("POST", "/api/providers/{}/test".format(cid), tok)
    return jsonify({"ok": ok, "data": data if ok else str(data)})


@app.route("/api/accounts/<cid>", methods=["DELETE"])
def api_delete(cid):
    tok = _token()
    ok, data = ag.api_request("DELETE", "/api/providers/{}".format(cid), tok)
    return jsonify({"ok": ok})


@app.route("/api/accounts/delete-all", methods=["POST"])
def api_delete_all():
    """Delete connections. Body: {"scope":"all"|"error", "provider":"antigravity"|null}."""
    tok = _token()
    body = request.json or {}
    scope = body.get("scope", "all")
    provider = body.get("provider")
    ok, data = ag.api_request("GET", "/api/providers", tok)
    if not ok:
        return jsonify({"ok": False, "error": str(data)}), 502
    conns = data.get("connections") or []
    deleted = 0
    for c in conns:
        if provider and (c.get("provider") or c.get("providerId")) != provider:
            continue
        if scope == "error" and (c.get("testStatus") or "") != "error":
            continue
        okd, _ = ag.api_request("DELETE", "/api/providers/{}".format(c.get("id")), tok)
        if okd:
            deleted += 1
    return jsonify({"ok": True, "deleted": deleted})


# ----------------- Credits (paralel) -----------------
@app.route("/api/credits")
def api_credits():
    from concurrent.futures import ThreadPoolExecutor
    tok = _token()
    ok, data = ag.api_request("GET", "/api/providers", tok)
    if not ok:
        return jsonify({"error": str(data)}), 502
    conns = [c for c in (data.get("connections") or [])
             if (c.get("provider") or c.get("providerId")) == "antigravity"]
    conns.sort(key=lambda c: (c.get("priority") or 999, (c.get("email") or "")))

    def fetch(c):
        ok2, u = ag.api_request("GET", "/api/usage/{}".format(c["id"]), tok)
        return c, ok2, u

    results = []
    if conns:
        with ThreadPoolExecutor(max_workers=min(16, len(conns))) as ex:
            for c, ok2, u in ex.map(fetch, conns):
                models = []
                if ok2:
                    for mid, qd in (u.get("quotas") or {}).items():
                        total = qd.get("total", 0)
                        used = qd.get("used", 0)
                        models.append({
                            "name": qd.get("displayName") or mid,
                            "used": used,
                            "total": total,
                            "remaining": max(0, total - used),
                            "pct": qd.get("remainingPercentage", 0),
                            "unlimited": bool(qd.get("unlimited")),
                            "resetAt": qd.get("resetAt"),
                            "gemini": "gemini" in (mid + str(qd.get("displayName") or "")).lower(),
                        })
                results.append({
                    "email": c.get("email") or c.get("name"),
                    "isActive": bool(c.get("isActive")),
                    "testStatus": c.get("testStatus") or "?",
                    "plan": (u.get("plan") if ok2 else "?"),
                    "models": models,
                })
    return jsonify({"accounts": results})


# ----------------- accounts.txt editor -----------------
@app.route("/api/accountsfile", methods=["GET"])
def api_accountsfile_get():
    try:
        with open(g.ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return jsonify({"content": f.read()})
    except Exception:
        return jsonify({"content": ""})


@app.route("/api/accountsfile", methods=["POST"])
def api_accountsfile_post():
    content = (request.json or {}).get("content", "")
    try:
        with open(g.ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------- Run tasks (background + SSE) -----------------
def _run_with_logging(job, target):
    """Jalankan target() sambil menangkap output log ke job queue."""
    class _Writer(io.TextIOBase):
        def write(self, s):
            if s and s.strip():
                job.emit(s.rstrip("\n"))
            return len(s)

    w = _Writer()
    try:
        with contextlib.redirect_stdout(w):
            target()
    except SystemExit:
        pass
    except Exception as e:
        job.emit("ERROR: {}".format(e))
    finally:
        job.emit("=== selesai ===")
        job.finish()


@app.route("/api/run/gmail", methods=["POST"])
def api_run_gmail():
    job_id = _new_job("gmail")
    job = _get_job(job_id)
    threading.Thread(target=_run_with_logging, args=(job, g.main), daemon=True).start()
    return jsonify({"jobId": job_id})


def _run_install(job):
    """(Re)install Python dependencies, streaming output to the job."""
    import subprocess
    import sys as _sys
    deps = [
        "flask>=3.0.0",
        "undetected-chromedriver>=3.5.5",
        "selenium>=4.41.0",
        "requests>=2.31.0",
        "pystray>=0.19.5",
        "pillow>=10.0.0",
    ]
    job.emit("=== Installing dependencies ===")
    job.emit("$ python -m pip install " + " ".join(deps))
    try:
        proc = subprocess.Popen(
            [_sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *deps],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.strip():
                job.emit(line)
        proc.wait()
        if proc.returncode == 0:
            job.emit("SUCCESS  all Python dependencies installed")
        else:
            job.emit("FAILED   pip exited with code {}".format(proc.returncode))
    except Exception as e:
        job.emit("FAILED   install error: {}".format(e))

    # Node.js check
    try:
        out = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if out.returncode == 0:
            job.emit("Node.js detected: {}".format(out.stdout.strip()))
        else:
            job.emit("WARN     Node.js not found (needed by 9router)")
    except Exception:
        job.emit("WARN     Node.js not found (needed by 9router)")
    job.emit("=== done ===")
    job.finish()


@app.route("/api/deps")
def api_deps():
    """Check whether core dependencies are installed."""
    missing = []
    for mod in ("flask", "undetected_chromedriver", "selenium", "requests"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    return jsonify({"ok": len(missing) == 0, "missing": missing})


@app.route("/api/run/install", methods=["POST"])
def api_run_install():
    job_id = _new_job("install")
    job = _get_job(job_id)
    threading.Thread(target=_run_install, args=(job,), daemon=True).start()
    return jsonify({"jobId": job_id})


# ----------------- Round-robin strategy (antigravity) -----------------
@app.route("/api/strategy")
def api_strategy_get():
    tok = _token()
    ok, data = ag.api_request("GET", "/api/settings", tok)
    if not ok:
        return jsonify({"ok": False, "error": str(data)}), 502
    ps = (data.get("providerStrategies") or {}).get("antigravity") or {}
    return jsonify({
        "ok": True,
        "fallbackStrategy": ps.get("fallbackStrategy", "round-robin"),
        "stickyRoundRobinLimit": ps.get("stickyRoundRobinLimit", 1),
    })


@app.route("/api/strategy", methods=["POST"])
def api_strategy_set():
    tok = _token()
    body = request.json or {}
    strat = body.get("fallbackStrategy", "round-robin")
    limit = int(body.get("stickyRoundRobinLimit", 1) or 1)
    ok, data = ag.api_request("GET", "/api/settings", tok)
    if not ok:
        return jsonify({"ok": False, "error": str(data)}), 502
    ps = data.get("providerStrategies") or {}
    ps["antigravity"] = {"fallbackStrategy": strat, "stickyRoundRobinLimit": max(1, limit)}
    ok2, res = ag.api_request("PATCH", "/api/settings", tok, {"providerStrategies": ps})
    return jsonify({"ok": ok2, "error": None if ok2 else str(res)})


@app.route("/api/run/antigravity", methods=["POST"])
def api_run_antigravity():
    workers = (request.json or {}).get("workers")
    if workers:
        try:
            ag.PARALLEL_WORKERS = max(1, int(workers))
        except Exception:
            pass
    job_id = _new_job("antigravity")
    job = _get_job(job_id)

    def _task():
        _kill_stale_chrome(job)
        ag.main()

    threading.Thread(target=_run_with_logging, args=(job, _task), daemon=True).start()
    return jsonify({"jobId": job_id, "workers": ag.PARALLEL_WORKERS})


def _kill_stale_chrome(job=None):
    """Bersihkan proses chrome/chromedriver zombie sebelum run baru."""
    import subprocess
    for name in ("chromedriver.exe", "undetected_chromedriver.exe"):
        try:
            subprocess.run(["taskkill", "/F", "/IM", name], capture_output=True)
        except Exception:
            pass
    if job:
        print("Membersihkan proses Chrome lama...")


@app.route("/api/stream/<job_id>")
def api_stream(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "job tidak ada"}), 404

    def gen():
        yield "retry: 2000\n\n"
        yield ": connected\n\n"
        while True:
            line = job.q.get()
            if line is None:
                yield "event: done\ndata: end\n\n"
                break
            yield "data: {}\n\n".format(json.dumps(line))

    resp = Response(gen(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache, no-transform"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp


if __name__ == "__main__":
    print("ANTIGRAVITY Control Panel -> http://localhost:{}".format(PORT))
    app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False)
