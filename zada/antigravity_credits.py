"""Cek akun antigravity yang terdaftar di 9router + sisa credit/quota tiap akun.

Menampilkan, per koneksi antigravity:
  - email, status (aktif/error), plan
  - kuota per model: terpakai / total, sisa %, kapan reset

Pakai endpoint lokal 9router:
  GET /api/providers           -> daftar koneksi
  GET /api/usage/{connectionId} -> plan + quotas per model
"""
import sys
from concurrent.futures import ThreadPoolExecutor

from . import antigravity_login as a

PROVIDER = "antigravity"

# Warna ANSI ringan
C_RESET = "\x1b[0m"
C_BOLD = "\x1b[1m"
C_DIM = "\x1b[2m"
C_GREEN = "\x1b[32m"
C_YELLOW = "\x1b[33m"
C_RED = "\x1b[31m"
C_CYAN = "\x1b[36m"


def bar(pct, width=20):
    pct = max(0, min(100, int(pct)))
    filled = int(round(pct / 100 * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def pct_color(pct):
    if pct >= 50:
        return C_GREEN
    if pct >= 20:
        return C_YELLOW
    return C_RED


def fmt_reset(iso):
    if not iso:
        return ""
    # tampilkan tanggal+jam ringkas
    return iso.replace("T", " ").replace("Z", " UTC")


def main():
    token = a.get_cli_token()
    if not token:
        print("FATAL: CLI token 9router tidak bisa dihitung. Pastikan 9router pernah dijalankan.")
        sys.exit(1)

    if not a.server_alive(token):
        print("FATAL: Server 9router tidak merespons di http://{}:{}.".format(a.ROUTER_HOST, a.ROUTER_PORT))
        print("       Buka aplikasi 9router dulu.")
        sys.exit(1)

    ok, data = a.api_request("GET", "/api/providers", token)
    if not ok:
        print("Gagal ambil daftar provider:", data)
        sys.exit(1)

    conns = [c for c in (data.get("connections") or [])
             if (c.get("provider") or c.get("providerId")) == PROVIDER]

    print()
    print(C_BOLD + "=== Akun Antigravity di 9router: {} koneksi ===".format(len(conns)) + C_RESET)
    if not conns:
        print("Belum ada koneksi antigravity. Jalankan antigravity.bat dulu.")
        return

    # urutkan by priority lalu email
    conns.sort(key=lambda c: (c.get("priority") or 999, (c.get("email") or "")))

    # Ambil semua usage SEKALIGUS (paralel) biar cepat.
    def fetch_usage(c):
        ok2, usage = a.api_request("GET", "/api/usage/{}".format(c["id"]), token)
        return c["id"], ok2, usage

    usage_map = {}
    with ThreadPoolExecutor(max_workers=min(16, len(conns))) as ex:
        for cid, ok2, usage in ex.map(fetch_usage, conns):
            usage_map[cid] = (ok2, usage)

    for idx, c in enumerate(conns, 1):
        email = c.get("email") or c.get("name") or "(tanpa email)"
        active = "AKTIF" if c.get("isActive") else "nonaktif"
        tstat = c.get("testStatus") or "?"
        stat_col = C_GREEN if tstat == "active" else (C_RED if tstat == "error" else C_DIM)

        print()
        print("{}{}. {}{}  {}[{}]{}  {}{}{}".format(
            C_BOLD, idx, email, C_RESET,
            stat_col, tstat, C_RESET,
            C_DIM, active, C_RESET))

        ok2, usage = usage_map.get(c["id"], (False, "tidak ada data"))
        if not ok2:
            print("   {}gagal ambil usage: {}{}".format(C_RED, usage, C_RESET))
            continue

        plan = usage.get("plan", "Unknown")
        print("   Plan: {}{}{}".format(C_CYAN, plan, C_RESET))

        quotas = usage.get("quotas") or {}
        if not quotas:
            print("   {}(tidak ada data kuota){}".format(C_DIM, C_RESET))
            continue

        # tampilkan ringkas per model
        for mid, q in quotas.items():
            name = q.get("displayName") or mid
            used = q.get("used", 0)
            total = q.get("total", 0)
            unlimited = q.get("unlimited")
            if unlimited:
                line = "   {:<28} {}unlimited{}".format(name[:28], C_GREEN, C_RESET)
                print(line)
                continue
            pct = q.get("remainingPercentage", 0)
            col = pct_color(pct)
            reset = fmt_reset(q.get("resetAt"))
            remaining = max(0, total - used)
            print("   {:<28} {}{} {}{:>3}%{}  sisa {}/{}  {}reset {}{}".format(
                name[:28],
                col, bar(pct), C_BOLD, pct, C_RESET,
                remaining, total,
                C_DIM, reset, C_RESET))

    print()


if __name__ == "__main__":
    main()
