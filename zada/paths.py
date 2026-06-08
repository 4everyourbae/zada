"""Central path resolution for Zada.

When Zada is installed (via pip), the package code lives in a read-only
location (site-packages). User data must NOT be written there. This module
resolves a per-user data directory and keeps all runtime files there:

  Windows : %APPDATA%\\zada
  macOS   : ~/Library/Application Support/zada
  Linux   : $XDG_DATA_HOME/zada  (or ~/.local/share/zada)

It also locates bundled, read-only assets (templates/static) that ship
inside the package.
"""
import os
import sys


def _data_dir():
    """Per-user, writable directory for accounts, cookies, profiles, logs."""
    env = os.environ.get("ZADA_DATA_DIR")
    if env:
        base = env
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA")
                            or os.path.expanduser("~"), "zada")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"),
                            "Library", "Application Support", "zada")
    else:
        base = os.path.join(os.environ.get("XDG_DATA_HOME")
                            or os.path.join(os.path.expanduser("~"),
                                            ".local", "share"), "zada")
    os.makedirs(base, exist_ok=True)
    return base


# ---- writable, per-user data ----
DATA_DIR = _data_dir()
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.txt")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
COOKIES_DIR = os.path.join(DATA_DIR, "cookies")
RESULTS_LOG = os.path.join(DATA_DIR, "results.log")
ANTIGRAVITY_LOG = os.path.join(DATA_DIR, "antigravity_results.log")

# ---- bundled, read-only assets (ship inside the package) ----
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(PKG_DIR, "templates")
STATIC_DIR = os.path.join(PKG_DIR, "static")
ICON_FILE = os.path.join(STATIC_DIR, "assets", "zada_icon.png")

# Template used to seed accounts.txt on first run.
_ACCOUNTS_TEMPLATE = """# Daftar akun Gmail - satu akun per baris
# Format: email:password  atau  email|password
# Baris diawali '#' diabaikan.
#
# Contoh:
# myemail@gmail.com:mypassword
# another@gmail.com|anotherpassword
"""


def ensure_data_files():
    """Create the data dirs + a starter accounts.txt on first run."""
    os.makedirs(PROFILES_DIR, exist_ok=True)
    os.makedirs(COOKIES_DIR, exist_ok=True)
    if not os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            f.write(_ACCOUNTS_TEMPLATE)
    return DATA_DIR
