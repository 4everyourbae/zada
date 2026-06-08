import os
import sys
import re
import json
import time

import undetected_chromedriver as uc

from . import paths

# ----------------------- CONFIG -----------------------
PROFILES_DIR = paths.PROFILES_DIR
COOKIES_DIR = paths.COOKIES_DIR
CHROME_VERSION_MAIN = 148  # match installed Chrome major version
START_URL = "https://mail.google.com/"
HEADLESS = False           # buka profil = browser harus tampil biar bisa dipakai
# ------------------------------------------------------


def load_cookies(driver, profile_name):
    """Pulihkan cookie tersimpan (profile_name = nama file cookie)."""
    path = os.path.join(COOKIES_DIR, profile_name + ".json")
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not cookies:
            return False
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
        print("(gagal muat cookie: {})".format(e))
        return False


def list_profiles():
    if not os.path.isdir(PROFILES_DIR):
        return []
    items = []
    for name in sorted(os.listdir(PROFILES_DIR)):
        full = os.path.join(PROFILES_DIR, name)
        if os.path.isdir(full):
            items.append(name)
    return items


def open_profile(profile_name):
    profile_path = os.path.join(PROFILES_DIR, profile_name)
    options = uc.ChromeOptions()
    options.add_argument("--user-data-dir={}".format(profile_path))
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if HEADLESS:
        options.add_argument("--headless=new")
    driver = uc.Chrome(options=options, version_main=CHROME_VERSION_MAIN)
    load_cookies(driver, profile_name)
    driver.get(START_URL)
    print("Chrome dibuka untuk profil: {}".format(profile_name))
    print("Tekan ENTER di sini untuk menutup browser...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    # Tutup rapi supaya profil ter-flush ke disk.
    try:
        driver.execute_cdp_cmd("Browser.close", {})
        time.sleep(2)
    except Exception:
        pass
    try:
        driver.quit()
    except Exception:
        pass


def main():
    profiles = list_profiles()
    if not profiles:
        print("Belum ada profil tersimpan di: {}".format(PROFILES_DIR))
        print("Jalankan gmail_login.py dulu untuk login akun.")
        sys.exit(1)

    # Boleh kasih argumen langsung: python open_profile.py namaprofil / nomor / email
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg:
        # cocokkan via nomor
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(profiles):
                open_profile(profiles[idx])
                return
        # cocokkan via nama / email (disanitasi)
        target = re.sub(r"[^A-Za-z0-9._-]", "_", arg)
        for p in profiles:
            if p == target or p == arg:
                open_profile(p)
                return
        print("Profil '{}' tidak ditemukan.".format(arg))

    print("=== Profil yang tersedia ===")
    for i, p in enumerate(profiles, 1):
        print("  {}. {}".format(i, p))
    print()
    choice = input("Pilih nomor profil yang mau dibuka: ").strip()
    if not choice.isdigit():
        print("Input tidak valid.")
        sys.exit(1)
    idx = int(choice) - 1
    if not (0 <= idx < len(profiles)):
        print("Nomor di luar jangkauan.")
        sys.exit(1)
    open_profile(profiles[idx])


if __name__ == "__main__":
    main()
