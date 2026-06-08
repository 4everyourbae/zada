"""Daftar akun yang berhasil terdaftar di 9router + jumlahnya.

Menampilkan semua koneksi (semua provider), dikelompokkan per provider,
beserta status (aktif/nonaktif, testStatus) dan totalnya.
"""
import sys

from . import antigravity_login as a

# Warna ANSI
C_RESET = "\x1b[0m"
C_BOLD = "\x1b[1m"
C_DIM = "\x1b[2m"
C_GREEN = "\x1b[32m"
C_YELLOW = "\x1b[33m"
C_RED = "\x1b[31m"
C_CYAN = "\x1b[36m"


def status_mark(conn):
    tstat = (conn.get("testStatus") or "").lower()
    if tstat == "active":
        return C_GREEN + "OK" + C_RESET
    if tstat == "error":
        return C_RED + "ERR" + C_RESET
    return C_DIM + "?" + C_RESET


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

    conns = data.get("connections") or []
    if not conns:
        print("Belum ada akun terdaftar di 9router.")
        return

    # Kelompokkan per provider
    by_provider = {}
    for c in conns:
        prov = c.get("provider") or c.get("providerId") or "(unknown)"
        by_provider.setdefault(prov, []).append(c)

    print()
    print(C_BOLD + "=== Akun Terdaftar di 9router ===" + C_RESET)

    total_active = 0
    for prov in sorted(by_provider.keys()):
        items = by_provider[prov]
        items.sort(key=lambda c: (c.get("priority") or 999, (c.get("email") or "")))
        active_count = sum(1 for c in items if c.get("isActive"))
        total_active += active_count

        print()
        print("{}{}{}  {}({} akun, {} aktif){}".format(
            C_BOLD + C_CYAN, prov, C_RESET,
            C_DIM, len(items), active_count, C_RESET))

        for i, c in enumerate(items, 1):
            email = c.get("email") or c.get("name") or "(tanpa email)"
            active = (C_GREEN + "aktif" + C_RESET) if c.get("isActive") else (C_DIM + "nonaktif" + C_RESET)
            print("   {:>2}. {:<32} [{}]  {}".format(i, email, status_mark(c), active))

    print()
    print(C_BOLD + "--- Ringkasan ---" + C_RESET)
    for prov in sorted(by_provider.keys()):
        print("   {:<16} : {} akun".format(prov, len(by_provider[prov])))
    print("   {:<16} : {}{}{} akun".format("TOTAL", C_BOLD, len(conns), C_RESET))
    print("   {:<16} : {} akun".format("aktif", total_active))
    print()


if __name__ == "__main__":
    main()
