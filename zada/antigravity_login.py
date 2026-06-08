"""Auto-authorize akun Gmail ke provider Antigravity di 9router (lokal).

Alur per akun:
  1. Minta authUrl OAuth dari 9router (GET /api/oauth/antigravity/authorize).
  2. Buka authUrl di profil Chrome yang SUDAH login Gmail (pakai cookie tersimpan).
  3. Otomatis pilih akun + klik consent (Continue/Allow), lewati layar
     "app belum diverifikasi" bila muncul.
  4. Tangkap 'code' dari redirect ke http://localhost:20128/callback.
  5. Tukar code -> token (POST /api/oauth/antigravity/exchange).

Akun yang emailnya SUDAH punya koneksi antigravity akan dilewati (SKIP_EXISTING).
"""
import os
import sys
import json
import time
import hashlib
import urllib.request
import threading
from concurrent.futures import ThreadPoolExecutor

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from . import gmail_login as g
from . import paths

# Consent OAuth antigravity TIDAK andal di headless (halaman consent Google
# butuh render nyata) -> paksa tampil browser.
g.HEADLESS = False

# ----------------------- CONFIG -----------------------
RESULTS_LOG = paths.ANTIGRAVITY_LOG

ROUTER_HOST = "127.0.0.1"
ROUTER_PORT = 20128
REDIRECT_URI = "http://localhost:20128/callback"
PROVIDER = "antigravity"

SKIP_EXISTING = True       # lewati akun yang sudah punya koneksi antigravity
CONSENT_TIMEOUT = 150      # detik; dinaikkan karena 3 Chrome paralel saling rebutan
HTTP_TIMEOUT = 30
PARALLEL_WORKERS = 1       # jumlah Chrome yang jalan bersamaan (default 1 = paling stabil)

APPDATA = os.environ.get("APPDATA", "")
ROUTER_DATA_DIR = os.path.join(APPDATA, "9router")
MACHINE_ID_FILE = os.path.join(ROUTER_DATA_DIR, "machine-id")
CLI_SECRET_FILE = os.path.join(ROUTER_DATA_DIR, "auth", "cli-secret")
CLI_TOKEN_SALT = "9r-cli-auth"
CLI_TOKEN_HEADER = "x-9r-cli-token"
# ------------------------------------------------------


def log(msg):
    import datetime
    line = "[{}] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    with _LOG_LOCK:
        print(line)
        try:
            with open(RESULTS_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


_LOG_LOCK = threading.Lock()
_DRIVER_LOCK = threading.Lock()


def get_cli_token():
    """Token = sha256(machineId + salt + cliSecret)[:16], dibaca dari file lokal 9router."""
    try:
        with open(MACHINE_ID_FILE, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        with open(CLI_SECRET_FILE, "r", encoding="utf-8") as f:
            secret = f.read().strip()
    except Exception as e:
        log("FATAL: gagal baca kredensial CLI 9router: {}".format(e))
        return None
    if not raw or not secret:
        return None
    h = hashlib.sha256((raw + CLI_TOKEN_SALT + secret).encode("utf-8")).hexdigest()
    return h[:16]


def api_request(method, path, token, body=None):
    """Request ke server 9router lokal. Return (ok, parsed_json_or_error)."""
    url = "http://{}:{}{}".format(ROUTER_HOST, ROUTER_PORT, path)
    data = None
    headers = {"Content-Type": "application/json", CLI_TOKEN_HEADER: token}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            if parsed.get("error"):
                return False, parsed.get("error")
            return True, parsed
    except urllib.error.HTTPError as e:
        try:
            parsed = json.loads(e.read().decode("utf-8"))
            return False, parsed.get("error", "HTTP {}".format(e.code))
        except Exception:
            return False, "HTTP {}".format(e.code)
    except Exception as e:
        return False, "Network error: {}".format(e)


def server_alive(token):
    ok, _ = api_request("GET", "/api/providers", token)
    return ok


def existing_antigravity_emails(token):
    """Set email (lowercase) yang sudah punya koneksi antigravity."""
    ok, data = api_request("GET", "/api/providers", token)
    emails = set()
    if not ok:
        return emails, False
    for conn in data.get("connections", []) or []:
        prov = conn.get("provider") or conn.get("providerId")
        if prov == PROVIDER:
            em = (conn.get("email") or conn.get("name") or "").strip().lower()
            if em:
                emails.add(em)
    return emails, True


def get_auth_url(token):
    import urllib.parse
    path = "/api/oauth/{}/authorize?redirect_uri={}".format(
        PROVIDER, urllib.parse.quote(REDIRECT_URI, safe="")
    )
    ok, data = api_request("GET", path, token)
    if not ok:
        return None, data
    return data, None


def exchange_code(token, code, code_verifier, state):
    body = {
        "code": code,
        "redirectUri": REDIRECT_URI,
        "codeVerifier": code_verifier,
        "state": state,
    }
    return api_request("POST", "/api/oauth/{}/exchange".format(PROVIDER), token, body)


# ------------------ Consent automation ------------------

def _click_first(driver, xpaths, pause=0.8):
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    time.sleep(pause)
                    return True
        except Exception:
            continue
    return False


def _drive_consent(driver, email, password=None):
    """Jalankan alur OAuth sampai callback. Mendukung login langsung:
    isi email + password kalau Google memintanya. Return True kalau sampai callback."""
    deadline = time.time() + CONSENT_TIMEOUT
    email_low = email.strip().lower()
    while time.time() < deadline:
        url = driver.current_url
        # Callback sungguhan: URL diawali redirect_uri DAN membawa code/error.
        if url.startswith("http://localhost:20128/callback") or url.startswith(
            "http://127.0.0.1:20128/callback"
        ):
            if "code=" in url or "error=" in url:
                return True

        # A) Field EMAIL (login langsung) -> isi lalu Next
        try:
            ids = driver.find_elements(By.ID, "identifierId")
            ids = [e for e in ids if e.is_displayed()]
            if ids and not (ids[0].get_attribute("value") or "").strip():
                g._type_into(driver, ids[0], email)
                _click_first(driver, ["//*[@id='identifierNext']",
                    "//button[.//span[contains(text(),'Next') or contains(text(),'Berikutnya')]]"], pause=1.5)
                continue
        except Exception:
            pass

        # B) Field PASSWORD -> isi lalu Next
        if password:
            try:
                pws = driver.find_elements(By.NAME, "Passwd")
                pws = [e for e in pws if e.is_displayed()]
                if pws:
                    time.sleep(0.4)
                    g._type_into(driver, pws[0], password)
                    _click_first(driver, ["//*[@id='passwordNext']",
                        "//button[.//span[contains(text(),'Next') or contains(text(),'Berikutnya')]]"], pause=1.8)
                    continue
            except Exception:
                pass

        # C) Account chooser (HANYA di halaman chooser, supaya tidak loop di consent)
        if "accountchooser" in url or "/signin/v2/identifier" in url:
            if _click_first(driver, [
                "//div[@data-identifier='{}']".format(email_low),
                "//*[@data-identifier='{}']".format(email_low),
                "//*[normalize-space(text())='{}']".format(email_low),
            ], pause=1.5):
                continue

        # D) Layar "app belum diverifikasi" -> Advanced -> Go to ...
        if _click_first(driver, [
            "//button[.//span[contains(text(),'Advanced')]]",
            "//a[contains(text(),'Advanced')]",
            "//*[@id='details-button']",
        ], pause=0.6):
            _click_first(driver, [
                "//a[contains(translate(text(),'GO TO','go to'),'go to')]",
                "//*[contains(text(),'(unsafe)')]",
                "//*[@id='proceed-link']",
            ], pause=1.0)
            continue

        # E) Konfirmasi "Saya mengerti" / "I understand"
        if _click_first(driver, [
            "//*[@id='confirm']",
            "//input[@name='confirm']",
            "//button[@name='confirm']",
            "//*[@value='Saya mengerti' or @value='I understand']",
            "//button[.//span[contains(text(),'Saya mengerti') or contains(text(),'I understand')]]",
        ], pause=1.0):
            continue

        # F) Tombol Sign in / Continue / Allow / Izinkan / Lanjutkan
        if _click_first(driver, [
            "//button[.//span[normalize-space(text())='Sign in' or normalize-space(text())='Masuk']]",
            "//button[.//span[contains(text(),'Continue') or contains(text(),'Lanjutkan')]]",
            "//button[.//span[contains(text(),'Allow') or contains(text(),'Izinkan')]]",
            "//span[contains(text(),'Sign in') or contains(text(),'Continue') or contains(text(),'Allow') or contains(text(),'Izinkan')]/ancestor::button",
            "//*[@id='submit_approve_access']",
        ], pause=1.5):
            continue

        time.sleep(0.6)
    return False


def extract_code(driver):
    """Ambil code & state dari URL callback."""
    import urllib.parse
    url = driver.current_url
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    code = qs.get("code", [None])[0]
    state = qs.get("state", [None])[0]
    err = qs.get("error", [None])[0]
    return code, state, err


def process_account(email, password, token):
    log("=== Antigravity: {} ===".format(email))
    profile_path = os.path.join(g.PROFILES_DIR, g.sanitize(email))
    os.makedirs(profile_path, exist_ok=True)

    # 1) Minta authUrl baru (state & codeVerifier sekali pakai)
    auth, err = get_auth_url(token)
    if not auth:
        log("FAILED   {} - gagal ambil authUrl: {}".format(email, err))
        return False
    auth_url = auth.get("authUrl")
    state = auth.get("state")
    code_verifier = auth.get("codeVerifier")
    if not auth_url or not code_verifier:
        log("FAILED   {} - authUrl/codeVerifier kosong".format(email))
        return False

    driver = None
    try:
        # undetected_chromedriver mem-patch file chromedriver.exe yang sama saat
        # start; kalau beberapa instance start bersamaan -> bentrok file.
        # Serialize pembuatan driver saja (login/consent tetap paralel).
        with _DRIVER_LOCK:
            driver = g.build_driver(profile_path)
            time.sleep(2.5)

        # Pulihkan cookie Gmail kalau ada (lebih cepat, lewati form login).
        if os.path.exists(g.cookie_file(email)):
            g.load_cookies(driver, email)

        # 2) Buka consent OAuth langsung. _drive_consent akan mengisi
        #    email + password sendiri kalau Google memintanya.
        driver.get(auth_url)

        # 3) Otomatis: login (kalau perlu) + consent sampai callback
        reached = _drive_consent(driver, email, password)
        if not reached:
            log("FAILED   {} - timeout/menyangkut di layar consent".format(email))
            return False

        code, cb_state, cb_err = extract_code(driver)
        if cb_err:
            log("FAILED   {} - consent ditolak: {}".format(email, cb_err))
            return False
        if not code:
            log("FAILED   {} - tidak ada code di callback".format(email))
            return False

        # 4) Tukar code -> token
        ok, data = exchange_code(token, code, code_verifier, cb_state or state)
        if ok:
            log("SUCCESS  {} - koneksi antigravity tersimpan".format(email))
            return True
        log("FAILED   {} - exchange gagal: {}".format(email, data))
        return False
    except Exception as e:
        log("FAILED   {} - error: {}".format(email, e))
        return False
    finally:
        if driver is not None:
            g.graceful_quit(driver)
        time.sleep(0.5)


def main():
    log("############ MULAI AUTO-AUTHORIZE ANTIGRAVITY ############")

    token = get_cli_token()
    if not token:
        log("FATAL: CLI token 9router tidak bisa dihitung. Pastikan 9router pernah dijalankan.")
        sys.exit(1)

    if not server_alive(token):
        log("FATAL: Server 9router tidak merespons di http://{}:{}.".format(ROUTER_HOST, ROUTER_PORT))
        log("       Buka aplikasi 9router dulu, lalu jalankan lagi.")
        sys.exit(1)

    paths.ensure_data_files()
    accounts = g.load_accounts(g.ACCOUNTS_FILE)
    if not accounts:
        log("Tidak ada akun di accounts.txt")
        sys.exit(1)

    existing, ok = existing_antigravity_emails(token)
    if ok and existing:
        log("Koneksi antigravity yang sudah ada: {}".format(", ".join(sorted(existing))))

    # Saring akun yang perlu diproses (lewati yang sudah terdaftar).
    todo = []
    skipped = 0
    for email, password in accounts:
        if SKIP_EXISTING and email.strip().lower() in existing:
            log("SKIP     {} - sudah terdaftar di antigravity".format(email))
            skipped += 1
        else:
            todo.append((email, password))

    if not todo:
        log("############ SELESAI ############")
        log("Berhasil: 0 | Gagal: 0 | Dilewati: {} | Total: {}".format(skipped, len(accounts)))
        return

    workers = max(1, min(PARALLEL_WORKERS, len(todo)))
    log("Memproses {} akun dengan {} Chrome paralel...".format(len(todo), workers))

    success = failed = 0
    counter_lock = threading.Lock()

    def worker(item):
        nonlocal success, failed
        email, password = item
        try:
            okp = process_account(email, password, token)
        except Exception as e:
            log("FAILED   {} - error tak terduga: {}".format(email, e))
            okp = False
        with counter_lock:
            if okp:
                success += 1
            else:
                failed += 1

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(worker, todo))

    log("############ SELESAI ############")
    log("Berhasil: {} | Gagal: {} | Dilewati: {} | Total: {}".format(
        success, failed, skipped, len(accounts)))


if __name__ == "__main__":
    main()
