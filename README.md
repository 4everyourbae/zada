# Zada â€” Claude Companion

Control panel lokal untuk mengelola akun **9router + Antigravity**: login Gmail
otomatis, daftar OAuth Antigravity, cek credit/quota, dan kelola koneksi lewat
dashboard web di `localhost:8421`.

## Instalasi

Butuh **Python 3.10+** dan **Google Chrome** terpasang. 9router harus sudah
pernah dijalankan (Zada membaca kredensial CLI 9router dari `%APPDATA%\9router`).

Install langsung dari GitHub:

```bash
pip install git+https://github.com/4everyourbae/zada.git
```

Perintah `zada` otomatis terdaftar di PATH. Untuk update ke versi terbaru:

```bash
pip install --upgrade git+https://github.com/4everyourbae/zada.git
```

## Pemakaian

Cukup ketik di terminal/CMD:

```bash
zada
```

Lalu pilih dengan panah â†‘/â†“:

- **Run in this terminal** â€” jalankan dashboard di foreground, browser kebuka otomatis.
- **Run in background** â€” jalankan di system tray (ikon Claude pet).
- **Quit**

Argumen langsung juga didukung:

```bash
zada run     # langsung foreground
zada tray    # langsung ke system tray
```

Dashboard terbuka di http://localhost:8421

## Data & konfigurasi

Semua data pengguna disimpan di folder per-user (BUKAN di dalam paket), jadi
aman saat upgrade:

| File/Folder    | Lokasi (Windows)                  | Isi                          |
| -------------- | --------------------------------- | ---------------------------- |
| `accounts.txt` | `%APPDATA%\zada\accounts.txt`     | Daftar akun `email:password` |
| `cookies/`     | `%APPDATA%\zada\cookies\`         | Sesi login Gmail tersimpan   |
| `profiles/`    | `%APPDATA%\zada\profiles\`        | Profil Chrome per akun       |
| `*.log`        | `%APPDATA%\zada\`                 | Log hasil run                |

Pada macOS/Linux, lokasinya `~/Library/Application Support/zada` atau
`~/.local/share/zada`. Override dengan env var `ZADA_DATA_DIR`.

Isi `accounts.txt` dengan satu akun per baris:

```
myemail@gmail.com:mypassword
another@gmail.com|anotherpassword
```

Bisa juga diedit langsung dari dashboard.

## Pengembangan

```bash
git clone https://github.com/4everyourbae/zada.git
cd zada
pip install -e .
zada
```

## Catatan keamanan

`accounts.txt`, `cookies/`, dan `profiles/` berisi kredensial dan sesi login.
Semuanya disimpan lokal di mesin kamu dan tidak pernah dikirim ke mana pun
selain server 9router lokal (`127.0.0.1:20128`). Jangan commit file-file ini
ke git (sudah diabaikan via `.gitignore`).
