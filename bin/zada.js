#!/usr/bin/env node
"use strict";

/*
 * Zada launcher (npm wrapper).
 * Forwards all arguments to the Python CLI: `python -m zada.cli`.
 * The actual program is Python; this just hands control over to it.
 */

const { spawnSync } = require("child_process");

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
  console.error(
    "Zada butuh Python 3.10+ terpasang dan ada di PATH.\n" +
      "Install dari https://www.python.org/downloads/ lalu coba lagi: zada"
  );
  process.exit(1);
}

const args = ["-m", "zada.cli", ...process.argv.slice(2)];
const res = spawnSync(python, args, { stdio: "inherit" });

if (res.error) {
  console.error("Gagal menjalankan zada:", res.error.message);
  process.exit(1);
}
process.exit(res.status === null ? 1 : res.status);
