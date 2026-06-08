function zada() {
  return {
    tab: "accounts",
    tabs: [
      { id: "accounts", label: "Accounts" },
      { id: "credits", label: "Credits" },
      { id: "run", label: "Terminal" },
      { id: "editor", label: "accounts" },
      { id: "auto", label: "Auto-Offline" },
    ],
    theme: "night",
    status: { online: false, total: 0, active: 0, byProvider: {} },
    accounts: [],
    credits: [],
    busy: { accounts: false, credits: false },
    fileContent: "",
    fileMsg: "",
    fileMsgOk: true,
    termLines: [],
    running: false,
    current: "",
    statusLine: "",
    workers: 3,
    petState: "idle",
    bubble: "",
    displayTotal: 0,
    displayActive: 0,
    _es: null,
    _blinkTimer: null,
    setupDone: true,
    setupLog: [],
    testingAll: false,
    rr: { fallbackStrategy: "round-robin", stickyRoundRobinLimit: 1 },
    rrBusy: false,
    rrMsg: "",
    rrMsgOk: true,

    get petStateClass() {
      return {
        "zada-running": this.petState === "running",
        "zada-success": this.petState === "success",
        "zada-fail": this.petState === "fail",
        "zada-sleep": this.petState === "sleep",
      };
    },

    // ---------- theme ----------
    applyTheme() {
      document.body.classList.toggle("t-night", this.theme === "night");
      document.body.classList.toggle("t-claude", this.theme !== "night");
    },
    toggleTheme() {
      this.theme = this.theme === "claude" ? "night" : "claude";
      try { localStorage.setItem("zada-theme", this.theme); } catch (e) { }
      this.applyTheme();
    },

    // ---------- pet ----------
    setPet(state, ms) {
      this.petState = state;
      if (ms) setTimeout(() => {
        this.petState = this.running ? "running" : (this.status.online ? "idle" : "sleep");
      }, ms);
    },
    say(text, ms) {
      this.bubble = text;
      if (ms) setTimeout(() => { if (this.bubble === text) this.bubble = ""; }, ms);
    },
    poke() {
      const lines = ["Hi, I'm Zada", "Ready to work", "Try the Run tab", "9router all good?", "Let's go"];
      this.say(lines[Math.floor(Math.random() * lines.length)], 2600);
      this.setPet("success", 800);
    },

    skipSetup() {
      this.setupDone = true;
      try { localStorage.setItem("zada-setup", "done"); } catch (e) { }
    },

    runSetup() {
      if (this.running) return;
      this.running = true;
      this.setupLog = ["$ installing requirements…"];
      this.petState = "running";
      fetch("/api/run/install", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
        .then((r) => r.json())
        .then((d) => {
          const es = new EventSource(`/api/stream/${d.jobId}`);
          es.onmessage = (ev) => {
            let line; try { line = JSON.parse(ev.data); } catch { line = ev.data; }
            this.setupLog.push(line);
            this.$nextTick(() => { const b = document.getElementById("setupbox"); if (b) b.scrollTop = b.scrollHeight; });
          };
          es.addEventListener("done", () => {
            es.close();
            this.running = false;
            this.petState = "success";
            this.setupDone = true;
            try { localStorage.setItem("zada-setup", "done"); } catch (e) { }
            this.say("All set", 2500);
            setTimeout(() => this.refreshStatus(), 500);
          });
          es.onerror = () => { es.close(); this.running = false; };
        })
        .catch(() => { this.running = false; this.setupLog.push("ERROR: failed to start install"); });
    },

    async testAll() {
      if (this.testingAll) return;
      this.testingAll = true;
      for (const a of this.accounts) {
        try {
          const r = await fetch(`/api/accounts/${a.id}/test`, { method: "POST" });
          const d = await r.json();
          a.testStatus = d.ok ? "active" : "error";
        } catch (e) { a.testStatus = "error"; }
      }
      this.testingAll = false;
      this.setPet("success", 800);
      this.say("Tested all connections", 2200);
    },

    async loadStrategy() {
      try {
        const r = await fetch("/api/strategy");
        const d = await r.json();
        if (d.ok) this.rr = { fallbackStrategy: d.fallbackStrategy, stickyRoundRobinLimit: d.stickyRoundRobinLimit };
      } catch (e) { }
    },

    async saveStrategy() {
      this.rrBusy = true;
      this.rrMsg = "";
      try {
        const r = await fetch("/api/strategy", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.rr),
        });
        const d = await r.json();
        this.rrMsgOk = !!d.ok;
        this.rrMsg = d.ok ? "Saved." : "Failed: " + (d.error || "");
      } catch (e) { this.rrMsgOk = false; this.rrMsg = "Failed."; }
      this.rrBusy = false;
      setTimeout(() => (this.rrMsg = ""), 3000);
    },
    blinkLoop() {
      const wrap = () => {
        document.querySelectorAll(".zada-blink-host").forEach((el) => {
          el.classList.add("zada-blink");
          setTimeout(() => el.classList.remove("zada-blink"), 130);
        });
        this._blinkTimer = setTimeout(wrap, 2600 + Math.random() * 3600);
      };
      this._blinkTimer = setTimeout(wrap, 2600);
    },

    // ---------- count up ----------
    countTo(field, target) {
      const start = this[field] || 0;
      if (start === target) { this[field] = target; return; }
      const t0 = performance.now(), dur = 650;
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        this[field] = Math.round(start + (target - start) * e);
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    },

    init() {
      try { this.theme = localStorage.getItem("zada-theme") || "night"; } catch (e) { }
      this.setupDone = true;
      this.applyTheme();
      this.refreshStatus();
      this.loadAccounts();
      this.loadFile();
      this.blinkLoop();
      setInterval(() => this.refreshStatus(), 8000);
      this.$watch("tab", (v) => {
        if (v === "credits") { if (this.credits.length === 0) this.loadCredits(); this.loadStrategy(); }
      });
      setTimeout(() => {
        document.querySelectorAll(".zada").forEach((el) => el.classList.add("zada-wave"));
        setTimeout(() => document.querySelectorAll(".zada").forEach((el) => el.classList.remove("zada-wave")), 2200);
        this.say("Hi, I'm Zada", 3000);
      }, 700);
    },

    async refreshStatus() {
      try { const r = await fetch("/api/status"); this.status = await r.json(); }
      catch (e) { this.status = { online: false }; }
      this.countTo("displayTotal", this.status.total || 0);
      this.countTo("displayActive", this.status.active || 0);
      if (!this.running) this.petState = this.status.online ? "idle" : "sleep";
    },

    async loadAccounts() {
      this.busy.accounts = true;
      try { const r = await fetch("/api/accounts"); const d = await r.json(); this.accounts = d.accounts || []; }
      catch (e) { }
      this.busy.accounts = false;
    },

    async toggle(a) {
      const want = !a.isActive;
      a.isActive = want;
      try {
        await fetch(`/api/accounts/${a.id}/toggle`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active: want }),
        });
      } catch (e) { a.isActive = !want; }
      this.refreshStatus();
    },

    async testConn(a) {
      const r = await fetch(`/api/accounts/${a.id}/test`, { method: "POST" });
      const d = await r.json();
      a.testStatus = d.ok ? "active" : "error";
    },

    async del(a) {
      if (!confirm(`Delete connection ${a.email}?`)) return;
      await fetch(`/api/accounts/${a.id}`, { method: "DELETE" });
      this.accounts = this.accounts.filter((x) => x.id !== a.id);
      this.refreshStatus();
    },

    async deleteAll() {
      const errs = this.accounts.filter((a) => a.testStatus === "error");
      if (errs.length === 0) { this.say("No error accounts to delete", 2400); return; }
      if (!confirm(`Delete ${errs.length} error/dead connection(s)? This cannot be undone.`)) return;
      this.busy.accounts = true;
      try {
        const r = await fetch("/api/accounts/delete-all", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scope: "error" }),
        });
        const d = await r.json();
        this.say("Deleted " + (d.deleted || 0) + " error connections", 2400);
      } catch (e) {}
      await this.loadAccounts();
      this.refreshStatus();
    },

    async loadCredits() {
      this.busy.credits = true;
      try { const r = await fetch("/api/credits"); const d = await r.json(); this.credits = d.accounts || []; }
      catch (e) { }
      this.busy.credits = false;
    },

    async loadFile() {
      const r = await fetch("/api/accountsfile");
      const d = await r.json();
      this.fileContent = d.content || "";
    },

    async saveFile() {
      const r = await fetch("/api/accountsfile", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: this.fileContent }),
      });
      const d = await r.json();
      this.fileMsgOk = !!d.ok;
      this.fileMsg = d.ok ? "Saved." : "Save failed: " + (d.error || "");
      setTimeout(() => (this.fileMsg = ""), 3000);
    },

    // ---------- terminal styling ----------
    lineStyle(l) {
      if (/SUCCESS|berhasil/i.test(l)) return "color:var(--leaf)";
      if (/FAILED|FATAL|ERROR|gagal/i.test(l)) return "color:var(--clay-2)";
      if (/SKIP|dilewati/i.test(l)) return "color:var(--amber)";
      if (/===|####|---/.test(l)) return "color:rgba(232,229,216,.45)";
      return "color:rgba(232,229,216,.85)";
    },
    marker(l) {
      if (/SUCCESS|berhasil|FAILED|FATAL|ERROR|gagal|SKIP|dilewati/i.test(l)) return "\u23fa";
      if (/===|####|---/.test(l)) return " ";
      if (/^\$/.test(l)) return "\u276f";
      return "\u00b7";
    },
    markerStyle(l) {
      if (/SUCCESS|berhasil/i.test(l)) return "color:var(--leaf)";
      if (/FAILED|FATAL|ERROR|gagal/i.test(l)) return "color:var(--clay-2)";
      if (/SKIP|dilewati/i.test(l)) return "color:var(--amber)";
      if (/^\$/.test(l)) return "color:var(--leaf)";
      return "color:rgba(232,229,216,.3)";
    },

    pushLine(text) {
      this.termLines.push(text);
      this.statusLine = text.replace(/^\[[^\]]*\]\s*/, "").slice(0, 60);
      if (/SUCCESS|berhasil/i.test(text)) { this.setPet("success", 900); this.say("All done", 2200); }
      else if (/FAILED|FATAL|gagal/i.test(text)) { this.setPet("fail", 900); this.say("Something broke", 2200); }
      this.$nextTick(() => { const b = document.getElementById("termbox"); if (b) b.scrollTop = b.scrollHeight; });
    },

    async run(kind) {
      if (this.running) return;
      // cek dependency dulu; kalau belum lengkap, tampilkan gate install
      try {
        const dr = await fetch("/api/deps");
        const dd = await dr.json();
        if (!dd.ok) {
          this.setupDone = false;
          this.setupLog = ["Missing: " + (dd.missing || []).join(", ")];
          this.say("Install requirements first", 2600);
          return;
        }
      } catch (e) { }
      this.tab = "run";
      this.running = true;
      this.current = kind;
      this.petState = "running";
      this.say("On it…", 2500);
      this.pushLine("$ running " + kind + " …");
      const body = kind === "antigravity" ? { workers: this.workers } : {};
      let jobId;
      try {
        const r = await fetch(`/api/run/${kind}`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const d = await r.json();
        jobId = d.jobId;
      } catch (e) {
        this.pushLine("ERROR: failed to start task");
        this.running = false; this.petState = "idle";
        return;
      }
      this._es = new EventSource(`/api/stream/${jobId}`);
      this._es.onmessage = (ev) => { try { this.pushLine(JSON.parse(ev.data)); } catch { this.pushLine(ev.data); } };
      this._es.addEventListener("done", () => {
        this._es.close();
        this.running = false;
        this.petState = this.status.online ? "idle" : "sleep";
        this.refreshStatus();
        this.loadAccounts();
      });
      this._es.onerror = () => { this._es.close(); this.running = false; this.petState = "idle"; };
    },
  };
}
