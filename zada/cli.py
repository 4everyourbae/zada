"""Zada CLI launcher — arrow-key menu + aesthetic orange banner.

Type `zada` -> pick with UP/DOWN arrows, ENTER to confirm:
  - Run in this terminal (foreground)
  - Run in background + system tray (Claude pet icon)
  - Quit
"""
import os
import sys
import time
import subprocess
import webbrowser

from . import paths

# Ensure UTF-8 output so the banner/block art renders on Windows consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8421
URL = "http://localhost:{}".format(PORT)
ICON = paths.ICON_FILE

# ---------- ANSI colors (Claude clay/orange palette) ----------
RESET = "\x1b[0m"
ORANGE = "\x1b[38;2;217;119;87m"      # clay/orange
ORANGE_B = "\x1b[1;38;2;217;119;87m"
DIM = "\x1b[38;2;150;145;135m"
INK = "\x1b[38;2;235;230;220m"
INVERT = "\x1b[7m"
HIDE_CUR = "\x1b[?25l"
SHOW_CUR = "\x1b[?25h"


def _enable_ansi():
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            pass
    try:
        os.system("")  # kickstart ANSI on Windows terminals
    except Exception:
        pass


def _set_title(t):
    if os.name == "nt":
        try:
            os.system("title " + t)
        except Exception:
            pass


def clear():
    os.system("cls" if os.name == "nt" else "clear")


BANNER = r"""
    ███████  █████  ██████   █████
        ██  ██   ██ ██   ██ ██   ██
       ██   ███████ ██   ██ ███████
      ██    ██   ██ ██   ██ ██   ██
    ███████ ██   ██ ██████  ██   ██
"""


def draw(items, idx, msg=""):
    clear()
    print(ORANGE_B + BANNER + RESET)
    print("   " + ORANGE + "Claude Companion" + RESET + DIM + "  ·  9router control  ·  localhost:8421" + RESET)
    print("   " + DIM + "─" * 52 + RESET)
    print()
    for i, (label, desc) in enumerate(items):
        if i == idx:
            print("   " + ORANGE_B + "  " + label + RESET + "   " + ORANGE + desc + RESET)
        else:
            print("   " + DIM + "  " + label + "   " + desc + RESET)
    print()
    print("   " + DIM + "↑/↓ move    enter select    q quit" + RESET)
    if msg:
        print("\n   " + ORANGE + msg + RESET)


def _read_key():
    """Return 'up','down','enter','quit', or None."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            return {b"H": "up", b"P": "down"}.get(ch2)
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch.lower() == b"q":
            return "quit"
        if ch.lower() == b"w":
            return "up"
        if ch.lower() == b"s":
            return "down"
        return None
    else:
        import termios, tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            c = sys.stdin.read(1)
            if c == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    return "up"
                if seq == "[B":
                    return "down"
                return None
            if c in ("\r", "\n"):
                return "enter"
            if c.lower() == "q":
                return "quit"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return None


def menu():
    items = [
        ("Run in this terminal", ""),
        ("Run in background", ""),
        ("Quit", ""),
    ]
    idx = 0
    print(HIDE_CUR, end="")
    try:
        while True:
            draw(items, idx)
            key = _read_key()
            if key == "up":
                idx = (idx - 1) % len(items)
            elif key == "down":
                idx = (idx + 1) % len(items)
            elif key == "quit":
                return 2
            elif key == "enter":
                return idx
    finally:
        print(SHOW_CUR, end="")


def _server_cmd():
    return [sys.executable, "-m", "zada.dashboard"]


def run_foreground():
    clear()
    print(ORANGE_B + BANNER + RESET)
    print("   " + ORANGE + "Running in this terminal" + RESET + DIM + "  ·  " + URL + RESET + "\n")
    try:
        webbrowser.open(URL)
    except Exception:
        pass
    subprocess.call(_server_cmd(), cwd=BASE_DIR)


def run_tray():
    creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    proc = subprocess.Popen(_server_cmd(), cwd=BASE_DIR, creationflags=creationflags)
    time.sleep(1.5)
    try:
        webbrowser.open(URL)
    except Exception:
        pass
    try:
        import pystray
        from PIL import Image
    except Exception:
        clear()
        print(ORANGE + "Tray needs pystray + pillow:  pip install pystray pillow" + RESET)
        print(DIM + "Server running at " + URL + " — Ctrl+C to stop." + RESET)
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
        return
    try:
        image = Image.open(ICON)
    except Exception:
        image = Image.new("RGBA", (64, 64), (217, 119, 87, 255))

    def on_open(icon, item):
        webbrowser.open(URL)

    def on_quit(icon, item):
        try:
            proc.terminate()
        except Exception:
            pass
        icon.stop()

    menu_obj = pystray.Menu(
        pystray.MenuItem("Open Zada Dashboard", on_open, default=True),
        pystray.MenuItem("Quit Zada", on_quit),
    )
    icon = pystray.Icon("zada", image, "Zada — Claude Companion", menu_obj)
    clear()
    print(ORANGE_B + BANNER + RESET)
    print("   " + ORANGE + "Running in tray" + RESET + DIM + "  ·  right-click the pet icon" + RESET)
    print("   " + DIM + "You can close this window." + RESET)
    icon.run()


def main():
    _enable_ansi()
    _set_title("Zada — Claude Companion")
    paths.ensure_data_files()

    args = [a.lower() for a in sys.argv[1:]]
    if any(a in args for a in ("tray", "--tray", "-t", "bg")):
        return run_tray()
    if any(a in args for a in ("run", "--run", "fg")):
        return run_foreground()

    choice = menu()
    if choice == 0:
        run_foreground()
    elif choice == 1:
        run_tray()
    else:
        clear()
        print(ORANGE + "  Bye!" + RESET)


if __name__ == "__main__":
    main()
