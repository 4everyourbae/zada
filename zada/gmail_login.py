import os
import re
import sys
import json
import time
import datetime

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from . import paths

# ----------------------- CONFIG -----------------------
ACCOUNTS_FILE = paths.ACCOUNTS_FILE
PROFILES_DIR = paths.PROFILES_DIR
COOKIES_DIR = paths.COOKIES_DIR
RESULTS_LOG = paths.RESULTS_LOG

HEADLESS = True           # set True to hide browser windows
CHROME_VERSION_MAIN = 148 # match installed Chrome major version
PAGE_TIMEOUT = 15         # seconds to wait for elements
SHORT_PAUSE = 0.25        # small human-like delay
KEEP_OPEN_SECONDS = 0     # pause before closing after success

# Login web standar. continue -> Gmail, jadi setelah sukses kita mendarat di inbox
# dan cookie akun tersimpan di profil (profil jadi "sudah login Gmail").
LOGIN_URL = "https://accounts.google.com/ServiceLogin?continue=https://mail.google.com/mail/u/0/"
GMAIL_URL = "https://mail.google.com/mail/u/0/"
# ------------------------------------------------------


def cookie_file(email):
    return os.path.join(COOKIES_DIR, sanitize(email) + ".json")


def save_cookies(driver, email):
    """Ambil SEMUA cookie via CDP (termasuk httpOnly) lalu simpan ke JSON.

    undetected-chromedriver mematikan paksa proses Chrome saat quit, sehingga
    Chrome sering belum sempat menulis cookie ke disk. Menyimpan manual via CDP
    membuat sesi login benar-benar persisten.
    """
    try:
        os.makedirs(COOKIES_DIR, exist_ok=True)
        data = driver.execute_cdp_cmd("Network.getAllCookies", {})
        cookies = data.get("cookies", [])
        with open(cookie_file(email), "w", encoding="utf-8") as f:
            json.dump(cookies, f)
        return len(cookies)
    except Exception as e:
        log("   (gagal simpan cookie: {})".format(e))
        return 0


def load_cookies(driver, email):
    """Pulihkan cookie dari JSON via CDP sebelum membuka Gmail."""
    path = cookie_file(email)
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not cookies:
            return False
        # Buka domain Google dulu supaya konteks cookie valid.
        driver.get("https://www.google.com/")
        time.sleep(1)
        driver.execute_cdp_cmd("Network.enable", {})
        for c in cookies:
            ck = {k: c[k] for k in c if k in (
                "name", "value", "domain", "path", "secure",
                "httpOnly", "expires", "sameSite",
            )}
            if "expires" in ck and ck["expires"] in (-1, None):
                ck.pop("expires", None)
            try:
                driver.execute_cdp_cmd("Network.setCookie", ck)
            except Exception:
                pass
        return True
    except Exception as e:
        log("   (gagal muat cookie: {})".format(e))
        return False


def log(msg):
    line = "[{}] {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    try:
        with open(RESULTS_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def sanitize(email):
    return re.sub(r"[^A-Za-z0-9._-]", "_", email)


def load_accounts(path):
    accounts = []
    if not os.path.exists(path):
        log("accounts.txt tidak ditemukan: {}".format(path))
        return accounts
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            sep = None
            if "|" in line:
                sep = "|"
            elif ":" in line:
                sep = ":"
            if sep is None:
                log("Baris dilewati (format salah, tidak ada ':' atau '|'): {}".format(line))
                continue
            email, password = line.split(sep, 1)
            email = email.strip()
            password = password.strip()
            if email and password:
                accounts.append((email, password))
            else:
                log("Baris dilewati (email/password kosong): {}".format(line))
    return accounts


def build_driver(profile_path):
    options = uc.ChromeOptions()
    options.add_argument("--user-data-dir={}".format(profile_path))
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Jangan tunggu seluruh resource halaman selesai; cukup DOM siap.
    options.page_load_strategy = "eager"
    if HEADLESS:
        options.add_argument("--headless=new")
    driver = uc.Chrome(options=options, version_main=CHROME_VERSION_MAIN)
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    return driver


def has_existing_session(profile_path):
    """Cek cepat tanpa buka browser: apakah profil sudah punya data sesi."""
    default = os.path.join(profile_path, "Default")
    return os.path.exists(os.path.join(default, "Cookies")) or os.path.exists(
        os.path.join(default, "Network", "Cookies")
    )


def is_gmail_logged_in(driver):
    """Verifikasi jujur: buka Gmail, cek apakah benar masuk inbox.

    Kalau belum login, Gmail redirect ke accounts.google.com (halaman login).
    Kalau sudah, URL tetap di mail.google.com/mail dan ada elemen inbox.
    """
    try:
        driver.get(GMAIL_URL)
        WebDriverWait(driver, PAGE_TIMEOUT).until(
            lambda d: "accounts.google.com" in d.current_url
            or "/mail/u/" in d.current_url
        )
    except TimeoutException:
        pass
    # Belum login -> Gmail melempar ke accounts.google.com.
    # Sudah login -> URL tetap di /mail/u/.
    return "/mail/u/" in driver.current_url and "accounts.google.com" not in driver.current_url


def already_logged_in(driver):
    return is_gmail_logged_in(driver)


def _type_into(driver, element, text):
    """Isi field dengan andal: klik, ketik, lalu pastikan nilainya benar-benar masuk."""
    for attempt in range(3):
        try:
            try:
                element.click()
            except Exception:
                driver.execute_script("arguments[0].focus();", element)
            element.clear()
            element.send_keys(text)
            if (element.get_attribute("value") or "") == text:
                return True
            # Fallback: set value via JS lalu trigger event input Google
            driver.execute_script(
                "arguments[0].value=arguments[1];"
                "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                element, text,
            )
            if (element.get_attribute("value") or "") == text:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return (element.get_attribute("value") or "") == text


def do_login(driver, email, password):
    wait = WebDriverWait(driver, PAGE_TIMEOUT)

    driver.get(LOGIN_URL)
    # Step 1: email
    try:
        email_input = wait.until(EC.element_to_be_clickable((By.ID, "identifierId")))
    except TimeoutException:
        if "/mail/u/" in driver.current_url:
            return True, "Sudah login"
        return False, "Field email tidak muncul"

    if not _type_into(driver, email_input, email):
        return False, "Gagal mengisi email"
    _click_next(driver)

    # Step 2: password
    try:
        pwd_input = WebDriverWait(driver, PAGE_TIMEOUT).until(
            EC.element_to_be_clickable((By.NAME, "Passwd"))
        )
    except TimeoutException:
        return False, _detect_problem(driver, "Field password tidak muncul")

    # Pastikan field benar-benar siap menerima input (animasi transisi Google)
    time.sleep(SHORT_PAUSE)
    if not _type_into(driver, pwd_input, password):
        return False, "Gagal mengisi password"
    _click_next(driver)

    # Lewati halaman interupsi (passkey / "Not now" / simpan info) bila muncul.
    _dismiss_interstitials(driver)

    # Step 3: tunggu hasil
    return _verify_login(driver)


def _dismiss_interstitials(driver):
    """Klik halaman interupsi setelah password:
    - konfirmasi "Saya mengerti" / "I understand" (id=confirm)
    - tawaran passkey / simpan sandi ("Not now" / "Nanti saja").
    """
    deadline = time.time() + 10
    # Tombol konfirmasi lanjut (diklik duluan supaya lolos ke langkah berikut)
    confirm_xpaths = [
        "//*[@id='confirm']",
        "//input[@name='confirm']",
        "//button[@name='confirm']",
        "//button[.//span[contains(text(),'Saya mengerti') or contains(text(),'I understand')]]",
        "//*[@value='Saya mengerti' or @value='I understand']",
        "//button[.//span[contains(text(),'Continue') or contains(text(),'Lanjutkan')]]",
    ]
    dismiss_xpaths = [
        "//button[.//span[contains(text(),'Not now') or contains(text(),'Nanti')]]",
        "//button[contains(text(),'Not now') or contains(text(),'Nanti')]",
        "//*[@id='cancel']",
        "//a[contains(text(),'Not now') or contains(text(),'Nanti')]",
    ]
    while time.time() < deadline:
        if "/mail/u/" in driver.current_url:
            return
        clicked = False
        for xp in confirm_xpaths + dismiss_xpaths:
            try:
                for b in driver.find_elements(By.XPATH, xp):
                    if b.is_displayed() and b.is_enabled():
                        b.click()
                        clicked = True
                        time.sleep(1)
                        break
            except Exception:
                continue
            if clicked:
                break
        if not clicked:
            time.sleep(0.5)


def _click_next(driver):
    """Klik tombol Next/Berikutnya pada form login Google."""
    selectors = [
        (By.ID, "identifierNext"),
        (By.ID, "passwordNext"),
        (By.XPATH, "//button[.//span[contains(text(),'Next') or contains(text(),'Berikutnya')]]"),
    ]
    for by, sel in selectors:
        try:
            btns = driver.find_elements(by, sel)
            for b in btns:
                if b.is_displayed() and b.is_enabled():
                    b.click()
                    return True
        except Exception:
            continue
    return False


def _detect_problem(driver, default_msg):
    url = driver.current_url.lower()
    page = ""
    try:
        page = driver.page_source.lower()
    except Exception:
        pass
    if "wrong password" in page or "password salah" in page or "salah sandi" in page:
        return "Password salah"
    if "couldn't find your" in page or "tidak dapat menemukan akun" in page:
        return "Akun tidak ditemukan"
    if "verify it" in page or "verifikasi" in page or "challenge" in url or "verify" in url:
        return "Butuh verifikasi keamanan (suspicious login)"
    if "captcha" in page:
        return "Diblokir CAPTCHA"
    return default_msg


def _verify_login(driver):
    """Tunggu hasil submit password. Sukses kalau benar mendarat di Gmail."""
    try:
        WebDriverWait(driver, PAGE_TIMEOUT + 10).until(
            lambda d: "/mail/u/" in d.current_url
            or "mail.google.com" in d.current_url
            or "challenge" in d.current_url
            or "rejected" in d.current_url
            or "/signin/v2/challenge" in d.current_url
            or "speedbump" in d.current_url
        )
    except TimeoutException:
        pass

    # Kalau sudah mendarat di Gmail, langsung sukses tanpa reload.
    if "/mail/u/" in driver.current_url:
        return True, "Login berhasil (Gmail)"
    # Selain itu, verifikasi dengan memuat Gmail sekali.
    if is_gmail_logged_in(driver):
        return True, "Login berhasil (Gmail)"
    return False, _detect_problem(driver, "Login gagal (URL: {})".format(driver.current_url))


def process_account(email, password):
    profile_path = os.path.join(PROFILES_DIR, sanitize(email))
    os.makedirs(profile_path, exist_ok=True)
    log("=== Memproses: {} ===".format(email))

    driver = None
    try:
        driver = build_driver(profile_path)

        # Pulihkan cookie tersimpan (kalau ada), lalu cek apakah sudah login.
        if os.path.exists(cookie_file(email)):
            load_cookies(driver, email)
            if already_logged_in(driver):
                save_cookies(driver, email)  # refresh
                log("SUCCESS  {} (sesi cookie tersimpan, sudah login)".format(email))
                return True

        ok, reason = do_login(driver, email, password)
        if ok:
            n = save_cookies(driver, email)
            log("SUCCESS  {} - {} (cookie disimpan: {})".format(email, reason, n))
            return True
        else:
            log("FAILED   {} - {}".format(email, reason))
            return False
    except WebDriverException as e:
        log("FAILED   {} - WebDriver error: {}".format(email, str(e).splitlines()[0]))
        return False
    except Exception as e:
        log("FAILED   {} - Error: {}".format(email, e))
        return False
    finally:
        if driver is not None:
            graceful_quit(driver)
        time.sleep(0.5)


def graceful_quit(driver):
    """Tutup Chrome dengan rapi supaya cookie/profil ter-flush ke disk.

    undetected-chromedriver memanggil taskkill saat .quit(), sehingga Chrome
    tidak sempat menulis data. Kita minta Chrome menutup diri lewat CDP dulu,
    beri waktu flush, baru quit.
    """
    try:
        driver.execute_cdp_cmd("Browser.close", {})
        time.sleep(1.5)
    except Exception:
        pass
    try:
        driver.quit()
    except Exception:
        pass
    time.sleep(0.3)


def main():
    log("################ MULAI AUTO-LOGIN GMAIL ################")
    paths.ensure_data_files()
    accounts = load_accounts(ACCOUNTS_FILE)
    if not accounts:
        log("Tidak ada akun untuk diproses. Isi accounts.txt ({}) dengan format email:password".format(ACCOUNTS_FILE))
        sys.exit(1)

    log("Total akun: {}".format(len(accounts)))
    success = 0
    failed = 0
    for idx, (email, password) in enumerate(accounts, 1):
        log("--- [{}/{}] ---".format(idx, len(accounts)))
        if process_account(email, password):
            success += 1
        else:
            failed += 1

    log("################ SELESAI ################")
    log("Berhasil: {} | Gagal: {} | Total: {}".format(success, failed, len(accounts)))


if __name__ == "__main__":
    main()
