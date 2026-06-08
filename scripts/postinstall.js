#!/usr/bin/env node
"use strict";

/*
 * postinstall: dijalankan otomatis setelah `npm install zada`.
 * Memasang paket Python (yang dibundel di folder ini) plus dependensinya,
 * sehingga perintah `zada` langsung bisa dipakai.
 *
 * Dilewati saat CI / npm publish (mis. env ZADA_SKIP_PY=1).
 */

const { spawnSync } = require("child_process");
const path = require("path");

if (process.env.ZADA_SKIP_PY === "1") {
  process.exit(0);
}

function pickPython() {
  const candidates =
    process.platform === "win32"
      ? ["py", "python", "python3"]
      : ["python3", "python"];
  for (const exe of candidates) {
    const probe = spawnSync(exe, ["--version"], { stdio: "ignore" });
    if (!probe.error && probe.status === 0) return exe;
  }
  return null;
}

const python = pickPython();
if (!python) {
  console.warn(
    "\n[zada] Python 3.10+ tidak ditemukan di PATH.\n" +
      "[zada] Install Python dari https://www.python.org/downloads/\n" +
      "[zada] lalu jalankan: pip install " +
      JSON.stringify(__dirname) +
      "/..\n"
  );
  // Jangan gagalkan instalasi npm; cuma kasih peringatan.
  process.exit(0);
}

const pkgRoot = path.resolve(__dirname, "..");
console.log("[zada] Memasang komponen Python (pip install) ...");

const res = spawnSync(
  python,
  ["-m", "pip", "install", "--upgrade", pkgRoot],
  { stdio: "inherit" }
);

if (res.error || res.status !== 0) {
  console.warn(
    "\n[zada] Pemasangan komponen Python belum selesai.\n" +
      "[zada] Coba manual:  " +
      python +
      " -m pip install \"" +
      pkgRoot +
      "\"\n"
  );
  // Tetap jangan gagalkan npm install.
  process.exit(0);
}

console.log("[zada] Selesai. Ketik `zada` untuk mulai.");
