/* ============================================================
   app.js — state, wiring, streaming, palette, tweaks
   ============================================================ */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  const state = {
    view: "home",
    railMode: "notebook",
    scope: null,          // { kind:'page'|'topic', label, path }
    openSrc: null,
    theme: "dark",
    density: "compact",
    accentH: 45,
  };

  const app = $("#app"), thread = $("#thread"), topbarTitle = $("#topbar-title");

  /* ---------- static icon hydration ---------- */
  function hydrateIcons() {
    const map = {
      "ic-search": ICON.search(), "ic-book": ICON.book({ s: 14 }), "ic-hash": ICON.hash({ s: 14 }),
      "ic-plus": ICON.plus({ s: 14 }), "ic-filter": ICON.filter({ s: 13 }),
      "ic-mark": ICON.layers({ s: 15 }),
    };
    for (const cls in map) $$("." + cls).forEach(e => { e.innerHTML = map[cls]; });
    $("#send-btn").innerHTML = ICON.arrowUp({ s: 17 });
    $("#cmdk-ico").innerHTML = ICON.search();
    $("#twk-close").innerHTML = ICON.x({ s: 15 });
    paintThemeIcon();
  }
  function paintThemeIcon() {
    $("#theme-toggle").innerHTML = state.theme === "dark" ? ICON.moon({ s: 16 }) : ICON.sun({ s: 16 });
  }

  /* ---------- toasts ---------- */
  function toast(msg, kind) {
    const wrap = $("#toast-wrap");
    const t = document.createElement("div");
    t.className = "toast" + (kind === "ok" ? " ok" : "");
    t.innerHTML = (kind === "ok" ? ICON.check({ s: 16 }) : ICON.info({ s: 16 })) + `<span>${msg}</span>`;
    wrap.appendChild(t);
    setTimeout(() => { t.style.transition = "opacity .3s, transform .3s"; t.style.opacity = "0"; t.style.transform = "translateY(8px)"; }, 2600);
    setTimeout(() => t.remove(), 3000);
  }

  /* ============================================================
     RAIL
     ============================================================ */
  function renderRail() {
    const body = state.railMode === "notebook" ? R.notebooks() : R.topics();
    $("#rail-scroll").innerHTML = body + `<div id="rail-lists">${R.railLists()}</div>`;
    syncRailActive();
  }
  function syncRailActive() {
    $$("#rail-scroll .is-active").forEach(e => e.classList.remove("is-active"));
    if (!state.scope) return;
    if (state.scope.kind === "topic")
      $$(`.topic-row[data-id="${state.scope.id}"]`).forEach(e => e.classList.add("is-active"));
    if (state.scope.kind === "page")
      $$(`.node__row[data-pg="${state.scope.pg}"]`).forEach(e => e.classList.add("is-active"));
  }

  function refreshLists() {
    const c = document.getElementById("rail-lists");
    if (c) c.innerHTML = R.railLists();
  }

  $("#rail-seg").addEventListener("click", e => {
    const b = e.target.closest("button[data-mode]"); if (!b) return;
    state.railMode = b.dataset.mode;
    $("#rail-seg").dataset.i = state.railMode === "notebook" ? "0" : "1";
    $$("#rail-seg button").forEach(x => x.setAttribute("aria-selected", x === b));
    renderRail();
  });

  $("#rail-scroll").addEventListener("click", e => {
    const row = e.target.closest("[data-act]"); if (!row) return;
    const act = row.dataset.act;
    if (act === "toggle") { row.closest(".node").classList.toggle("is-open"); return; }
    if (act === "page") { setScope({ kind: "page", pg: row.dataset.pg, label: row.dataset.label, path: row.dataset.path }); return; }
    if (act === "topic") { setScope({ kind: "topic", id: row.dataset.id, label: row.dataset.label }); return; }
    if (act === "restricted") { showRestricted(NOTEBOOKS.find(n => n.id === row.dataset.nb)); return; }
    if (act === "ask") { ask(row.dataset.q, row.dataset.a); return; }
    if (act === "pin") {
      const q = row.dataset.q;
      if (!PINNED.some(p => p.q === q)) PINNED.unshift({ q, a: row.dataset.a || undefined });
      refreshLists(); toast("Pinned to your saved answers.", "ok"); return;
    }
    if (act === "unpin") {
      const q = row.dataset.q, i = PINNED.findIndex(p => p.q === q);
      if (i >= 0) PINNED.splice(i, 1);
      refreshLists(); toast("Removed from pinned answers."); return;
    }
    if (act === "clear-recent") { RECENT.length = 0; refreshLists(); toast("Recent conversations cleared."); return; }
  });

  /* ============================================================
     SCOPE
     ============================================================ */
  function setScope(s) {
    state.scope = s;
    renderScopebar();
    syncRailActive();
    toast(`Scoped to ${s.label}. Answers will prefer this ${s.kind === "topic" ? "topic" : "page"}.`);
  }
  function clearScope() { state.scope = null; renderScopebar(); syncRailActive(); }
  function renderScopebar() {
    const bar = $("#scopebar");
    if (!state.scope) {
      bar.innerHTML = `<span class="scope-none">${ICON.filter({ s: 12 })} Searching all notebooks you can access</span>`;
      return;
    }
    const s = state.scope;
    bar.innerHTML = `<span class="scopebar__label">Scope</span>
      <span class="scope-chip">
        ${s.kind === "topic" ? ICON.hash({ s: 12 }) : ICON.page({ s: 12 })}
        <span>${R.esc(s.label)}</span>
        ${s.path ? `<span class="scope-chip__path">${R.esc(s.path)}</span>` : ""}
        <button class="scope-chip__x" data-act="clear-scope" aria-label="Clear scope">${ICON.x({ s: 13 })}</button>
      </span>`;
  }
  $("#scopebar").addEventListener("click", e => { if (e.target.closest('[data-act="clear-scope"]')) clearScope(); });

  /* scope picker popover */
  function closeScopeMenu() {
    const m = document.getElementById("scope-menu");
    if (m) m.remove();
    document.removeEventListener("click", outsideScope, true);
    $("#scope-tool").setAttribute("aria-expanded", "false");
  }
  function outsideScope(e) {
    if (!e.target.closest("#scope-menu") && !e.target.closest("#scope-tool")) closeScopeMenu();
  }
  function openScopeMenu() {
    const btn = $("#scope-tool");
    const cur = state.scope;
    const topics = TOPICS.map(t => `
      <button class="scope-menu__item" data-act="scope-pick" data-id="${t.id}" data-label="${R.esc(t.name)}">
        <span class="scope-menu__sw" style="background:${t.color}"></span>
        <span class="scope-menu__l">${R.esc(t.name)}</span>
        <span class="scope-menu__n">${t.count}</span>
        <span class="scope-menu__ck">${cur && cur.id === t.id ? ICON.check({ s: 14 }) : ""}</span>
      </button>`).join("");
    const menu = document.createElement("div");
    menu.className = "scope-menu";
    menu.id = "scope-menu";
    menu.innerHTML = `
      <div class="scope-menu__h">Scope answers to a topic</div>
      <button class="scope-menu__item" data-act="scope-all">
        <span class="scope-menu__ico">${ICON.layers({ s: 14 })}</span>
        <span class="scope-menu__l">All notebooks you can access</span>
        <span class="scope-menu__ck">${!cur ? ICON.check({ s: 14 }) : ""}</span>
      </button>
      <div class="scope-menu__div"></div>
      ${topics}
      <div class="scope-menu__foot">${ICON.info({ s: 12 })} You can also click any page in the left rail to scope to it.</div>`;
    document.body.appendChild(menu);

    const r = btn.getBoundingClientRect();
    menu.style.left = r.left + "px";
    menu.style.bottom = (window.innerHeight - r.top + 8) + "px";
    requestAnimationFrame(() => {
      const mr = menu.getBoundingClientRect();
      if (mr.right > window.innerWidth - 12) menu.style.left = Math.max(12, window.innerWidth - 12 - mr.width) + "px";
      menu.classList.add("is-open");
    });

    menu.addEventListener("click", e => {
      const it = e.target.closest("[data-act]"); if (!it) return;
      if (it.dataset.act === "scope-all") { clearScope(); toast("Scope cleared — searching all notebooks."); }
      else if (it.dataset.act === "scope-pick") setScope({ kind: "topic", id: it.dataset.id, label: it.dataset.label });
      closeScopeMenu();
    });
    btn.setAttribute("aria-expanded", "true");
    setTimeout(() => document.addEventListener("click", outsideScope, true), 0);
  }
  $("#scope-tool").addEventListener("click", e => {
    e.stopPropagation();
    document.getElementById("scope-menu") ? closeScopeMenu() : openScopeMenu();
  });

  /* ============================================================
     VIEWS
     ============================================================ */
  function goHome() {
    state.view = "home";
    topbarTitle.innerHTML = "<h1>Home</h1>";
    thread.innerHTML = R.home();
    closeSource();
  }
  function ensureConversation(title) {
    if (state.view !== "conversation") {
      state.view = "conversation";
      thread.innerHTML = `<div class="thread__inner" id="tinner"></div>`;
    }
    topbarTitle.innerHTML = `<h1>${R.esc(title)}</h1>`;
  }
  function scrollDown() { thread.scrollTop = thread.scrollHeight; }

  $("#new-chat").addEventListener("click", goHome);

  /* ============================================================
     ASK / ANSWER
     ============================================================ */
  function routeQuestion(q) {
    const t = " " + q.toLowerCase().replace(/[^a-z0-9 -]/g, " ") + " ";
    const hit = (k) => new RegExp("(^|[^a-z0-9])" + k.replace(/-/g, "[- ]") + "([^a-z0-9]|$)").test(t);
    for (const r of ROUTES) if (r.kw.some(hit)) return r.a;
    return null;
  }

  async function ask(q, aId) {
    q = (q || "").trim(); if (!q) return;
    const answerId = aId || routeQuestion(q);
    const ans = answerId ? ANSWERS[answerId] : null;
    ensureConversation(q.length > 52 ? q.slice(0, 52) + "…" : q);
    const inner = $("#tinner");
    inner.insertAdjacentHTML("beforeend", R.userMsg(q));

    // bot shell
    const bot = document.createElement("div");
    bot.className = "msg msg--bot fade-in";
    bot.innerHTML = `<div class="bot-ava">${ICON.layers({ s: 15 })}</div><div class="bot-body">
      <div class="bot-name">Knowledge Assistant <span class="tag">Grounded answer</span></div>
      <div class="thinking"><span class="spin"></span> Searching ${state.scope ? R.esc(state.scope.label) : "across notebooks"}…</div>
    </div>`;
    inner.appendChild(bot);
    scrollDown();

    await sleep(820);
    const body = bot.querySelector(".bot-body");
    body.querySelector(".thinking").remove();

    if (!ans) { body.insertAdjacentHTML("beforeend", R.noAnswer(q)); scrollDown(); return; }
    await streamAnswer(bot, body, ans);
  }

  async function streamAnswer(bot, body, ans) {
    bot._sources = ans.sources;
    // meta chips
    const freshCls = ans.fresh_warn ? "chip-meta chip-meta--warn" : "chip-meta";
    const meta = document.createElement("div");
    meta.className = "answer-meta fade-in";
    meta.innerHTML =
      `<span class="chip-meta"><span>${ICON.layers({ s: 12 })}</span> Based on <b>${ans.coverage} page${ans.coverage > 1 ? "s" : ""}</b></span>
       <span class="${freshCls}"><span>${ICON.clock({ s: 12 })}</span> ${R.esc(ans.freshness)}</span>
       ${ans.fresh_warn ? `<span class="chip-meta chip-meta--warn"><span>${ICON.alert({ s: 12 })}</span> Verify before relying</span>` : ""}`;
    body.appendChild(meta);

    // prose, block by block
    const prose = document.createElement("div");
    prose.className = "prose";
    body.appendChild(prose);
    const tmp = document.createElement("div");
    tmp.innerHTML = ans.html.trim();
    const blocks = [...tmp.children];
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      b.classList.add("fade-in");
      prose.appendChild(b);
      const caret = document.createElement("span");
      caret.className = "caret";
      b.appendChild(caret);
      scrollDown();
      await sleep(190 + Math.random() * 130);
      caret.remove();
    }

    // sources used
    const srcWrap = document.createElement("div");
    srcWrap.className = "srcline fade-in";
    srcWrap.innerHTML = `<div class="srcline__h">${ICON.book({ s: 12 })} Sources · ${ans.sources.length} OneNote page${ans.sources.length > 1 ? "s" : ""}</div>`
      + ans.sources.map((sid, i) => R.srcCard(sid, i + 1)).join("");
    body.appendChild(srcWrap);

    // followups
    const fu = document.createElement("div");
    fu.className = "followups fade-in";
    fu.innerHTML = ans.followups.map(f => `<button class="chip-follow" data-act="ask" data-q="${R.esc(f)}">${ICON.sparkle({ s: 13 })} ${R.esc(f)}</button>`).join("");
    body.appendChild(fu);
    scrollDown();
  }

  /* thread delegation: citations, source cards, followups, feedback, state buttons */
  thread.addEventListener("click", e => {
    const cite = e.target.closest(".cite");
    if (cite) {
      const msg = cite.closest(".msg--bot");
      msg.querySelectorAll(".cite.is-active").forEach(c => c.classList.remove("is-active"));
      cite.classList.add("is-active");
      const n = +cite.dataset.c;
      openSource(msg._sources[n - 1], n);
      return;
    }
    const act = e.target.closest("[data-act]"); if (!act) return;
    const a = act.dataset.act;
    if (a === "open-src") { openSource(act.dataset.src, +act.dataset.n); return; }
    if (a === "ask") { ask(act.dataset.q, act.dataset.a); return; }
    if (a === "topic") { setScope({ kind: "topic", id: act.dataset.id, label: act.dataset.label }); return; }
    if (a === "flag-gap") { act.closest(".statecard").innerHTML = gapFlagged(act.dataset.q); return; }
    if (a === "toast") { toast(act.dataset.msg, act.dataset.kind); return; }
  });

  function gapFlagged(q) {
    return `<div class="statecard__icon" style="background:color-mix(in oklch,var(--ok) 16%,transparent);color:var(--ok)">${ICON.check({ s: 20 })}</div>
      <h3>Gap flagged — thank you</h3>
      <p>Your question has been sent to the <strong>Finance notebook owner</strong> with context. We'll notify you here when a page is added that answers it.</p>
      <div class="statecard__hint">${ICON.info({ s: 14 })}<span>Tracking ID <span style="font-family:var(--font-mono)">GAP-4471</span> · typically answered within 3 business days.</span></div>`;
  }
  function showRestricted(nb) {
    ensureConversation(nb.name);
    $("#tinner").innerHTML = R.restricted(nb);
    closeSource();
  }

  /* ============================================================
     SOURCE PANEL
     ============================================================ */
  function openSource(sid, n) {
    state.openSrc = sid;
    $("#source-panel").innerHTML = R.sourcePanel(sid, n);
    app.dataset.source = "open";
    $("#source-panel").setAttribute("aria-hidden", "false");
  }
  function closeSource() {
    state.openSrc = null;
    app.dataset.source = "closed";
    $("#source-panel").setAttribute("aria-hidden", "true");
  }
  $("#source-panel").addEventListener("click", e => {
    const act = e.target.closest("[data-act]"); if (!act) return;
    if (act.dataset.act === "close-src") closeSource();
    if (act.dataset.act === "toast") toast(act.dataset.msg, act.dataset.kind);
  });

  /* ============================================================
     COMPOSER
     ============================================================ */
  const input = $("#composer-input");
  function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; toggleSend(); }
  function toggleSend() { $("#send-btn").disabled = !input.value.trim(); }
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitComposer(); }
  });
  $("#send-btn").addEventListener("click", submitComposer);
  function submitComposer() {
    const q = input.value.trim(); if (!q) return;
    input.value = ""; autosize();
    ask(q);
  }
  toggleSend();

  /* ============================================================
     COMMAND PALETTE
     ============================================================ */
  const overlay = $("#cmdk-overlay"), cmdkInput = $("#cmdk-input"), cmdkList = $("#cmdk-list");
  let cmdSel = 0, cmdItems = [];

  function baseCommands() {
    const cmds = [
      { grp: "Navigate", icon: "sun", label: "Go to Home", run: goHome },
      { grp: "Navigate", icon: "plus", label: "Start a new chat", run: goHome },
      { grp: "Try a state", icon: "spark2", label: "Streaming answer — parental leave", sub: "grounded, 3 sources", run: () => ask("How much parental leave am I eligible for, and how do I file?", "A_parental") },
      { grp: "Try a state", icon: "alert", label: "No-answer found example", sub: "graceful gap + flag", run: () => ask("What's our policy on paying contractors in cryptocurrency?") },
      { grp: "Try a state", icon: "lock", label: "Restricted notebook", sub: "Exec / Board", run: () => showRestricted(NOTEBOOKS.find(n => n.id === "nb-exec")) },
      { grp: "Appearance", icon: state.theme === "dark" ? "sun" : "moon", label: `Switch to ${state.theme === "dark" ? "light" : "dark"} mode`, run: toggleTheme },
    ];
    Object.keys(SOURCES).forEach(sid => {
      const s = SOURCES[sid];
      cmds.push({ grp: "OneNote pages", icon: "page", label: s.page, sub: `${s.notebook} ▸ ${s.section}`, run: () => openSource(sid, 1) });
    });
    return cmds;
  }
  function openCmdk() {
    overlay.classList.add("is-open"); cmdkInput.value = ""; renderCmdk(""); cmdkInput.focus();
  }
  function closeCmdk() { overlay.classList.remove("is-open"); }
  function renderCmdk(q) {
    q = q.toLowerCase().trim();
    let list = baseCommands();
    if (q) list = list.filter(c => (c.label + " " + (c.sub || "")).toLowerCase().includes(q));
    cmdItems = [];
    let html = "";
    if (q) {
      cmdItems.push({ icon: "spark2", label: `Ask the assistant: “${q}”`, run: () => ask(cmdkInput.value.trim()) });
      html += `<div class="cmdk__grouph">Ask</div>` + itemHtml(cmdItems[0], 0);
    }
    let lastGrp = "";
    list.forEach(c => {
      const idx = cmdItems.length; cmdItems.push(c);
      if (c.grp !== lastGrp) { html += `<div class="cmdk__grouph">${c.grp}</div>`; lastGrp = c.grp; }
      html += itemHtml(c, idx);
    });
    if (!cmdItems.length) html = `<div class="cmdk__grouph">No matches</div>`;
    cmdkList.innerHTML = html;
    cmdSel = 0; paintSel();
  }
  function itemHtml(c, i) {
    return `<div class="cmdk__item" data-i="${i}">
      <span class="ci">${ICON[c.icon] ? ICON[c.icon]({ s: 15 }) : ICON.search({ s: 15 })}</span>
      <span class="cm"><b>${R.esc(c.label)}</b>${c.sub ? `<span>${R.esc(c.sub)}</span>` : ""}</span>
      <span class="ck">↵</span></div>`;
  }
  function paintSel() {
    $$(".cmdk__item", cmdkList).forEach(el => el.classList.toggle("is-sel", +el.dataset.i === cmdSel));
    const sel = $(`.cmdk__item[data-i="${cmdSel}"]`, cmdkList);
    if (sel) sel.scrollIntoView({ block: "nearest" });
  }
  function runSel() { const c = cmdItems[cmdSel]; if (c) { closeCmdk(); c.run(); } }

  cmdkInput.addEventListener("input", () => renderCmdk(cmdkInput.value));
  cmdkInput.addEventListener("keydown", e => {
    if (e.key === "ArrowDown") { e.preventDefault(); cmdSel = Math.min(cmdSel + 1, cmdItems.length - 1); paintSel(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); cmdSel = Math.max(cmdSel - 1, 0); paintSel(); }
    else if (e.key === "Enter") { e.preventDefault(); runSel(); }
    else if (e.key === "Escape") closeCmdk();
  });
  cmdkList.addEventListener("click", e => { const it = e.target.closest(".cmdk__item"); if (!it) return; cmdSel = +it.dataset.i; runSel(); });
  overlay.addEventListener("click", e => { if (e.target === overlay) closeCmdk(); });
  $("#open-cmdk").addEventListener("click", openCmdk);
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); overlay.classList.contains("is-open") ? closeCmdk() : openCmdk(); }
    if (e.key === "Escape" && state.openSrc && !overlay.classList.contains("is-open")) closeSource();
  });

  /* ============================================================
     THEME + TWEAKS
     ============================================================ */
  function applyTheme() {
    const r = document.documentElement;
    r.classList.add("no-tx");
    r.dataset.theme = state.theme;
    r.dataset.density = state.density;
    r.style.setProperty("--accent-h", state.accentH);
    paintThemeIcon();
    void r.offsetWidth;                       // force reflow so colors swap instantly
    setTimeout(() => r.classList.remove("no-tx"), 60);
  }
  function toggleTheme() { state.theme = state.theme === "dark" ? "light" : "dark"; applyTheme(); syncTweaks(); }
  $("#theme-toggle").addEventListener("click", toggleTheme);

  // tweaks panel controls
  $("#twk-theme").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; state.theme = b.dataset.v; applyTheme(); syncTweaks(); });
  $("#twk-density").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; state.density = b.dataset.v; applyTheme(); syncTweaks(); });
  $("#twk-accent").addEventListener("click", e => { const b = e.target.closest("button"); if (!b) return; state.accentH = +b.dataset.h; applyTheme(); syncTweaks(); persistTweak({ accentH: state.accentH }); });
  function syncTweaks() {
    $$("#twk-theme button").forEach(b => b.setAttribute("aria-pressed", b.dataset.v === state.theme));
    $$("#twk-density button").forEach(b => b.setAttribute("aria-pressed", b.dataset.v === state.density));
    $$("#twk-accent button").forEach(b => b.setAttribute("aria-pressed", +b.dataset.h === state.accentH));
  }
  function persistTweak(edits) { try { window.parent.postMessage({ type: "__edit_mode_set_keys", edits }, "*"); } catch (e) {} }

  // tweaks host protocol
  const twk = $("#twk");
  $("#twk-close").addEventListener("click", () => { twk.classList.remove("is-open"); try { window.parent.postMessage({ type: "__edit_mode_dismissed" }, "*"); } catch (e) {} });
  window.addEventListener("message", e => {
    const t = e?.data?.type;
    if (t === "__activate_edit_mode") twk.classList.add("is-open");
    else if (t === "__deactivate_edit_mode") twk.classList.remove("is-open");
  });
  try { window.parent.postMessage({ type: "__edit_mode_available" }, "*"); } catch (e) {}

  /* ============================================================
     AUTH + PROFILE
     ============================================================ */
  const AUTH_KEY = "atlas.auth.v1";
  const authRoot = $("#auth-root");
  const menuRoot = $("#profile-menu-root");
  const modalRoot = $("#modal-root");

  function loadAuth() { try { return JSON.parse(localStorage.getItem(AUTH_KEY) || "null"); } catch (e) { return null; } }
  function saveAuth() { try { localStorage.setItem(AUTH_KEY, JSON.stringify({ authed: state.authed, user: state.user })); } catch (e) {} }

  function applyUser(u) {
    u.init = R.initials(u.name);
    state.user = u;
    R.setUser(u);
    $("#me-ava").textContent = u.init;
    $("#me-name").textContent = u.name;
    $("#me-role").textContent = u.role;
    if (state.view === "home") thread.innerHTML = R.home();   // refresh greeting only
  }

  function userFromEmail(email, base) {
    if (base && base.email && base.email.toLowerCase() === email.toLowerCase()) return { ...base };
    const local = (email.split("@")[0] || "user").replace(/[._-]+/g, " ").trim();
    const name = local.replace(/\b\w/g, c => c.toUpperCase());
    return { name, email, role: "Employee", dept: "—", init: R.initials(name), since: "Today" };
  }

  /* ---- screens ---- */
  function showLogin(err) { state.authScreen = "login"; authRoot.innerHTML = R.loginScreen(err); authRoot.classList.add("is-open"); authRoot.setAttribute("aria-hidden", "false"); focusFirst(); }
  function showRegister(err) { state.authScreen = "register"; authRoot.innerHTML = R.registerScreen(err); authRoot.classList.add("is-open"); authRoot.setAttribute("aria-hidden", "false"); focusFirst(); }
  function hideAuth() { authRoot.classList.remove("is-open"); authRoot.setAttribute("aria-hidden", "true"); authRoot.innerHTML = ""; }
  function focusFirst() { setTimeout(() => { const i = authRoot.querySelector("input"); if (i) i.focus(); }, 60); }

  function signIn(u, msg) {
    applyUser(u); state.authed = true; saveAuth(); hideAuth(); closeMenu(); closeModal();
    toast(msg || `Signed in as ${u.name}.`, "ok");
  }
  function signOut() {
    state.authed = false; saveAuth(); closeMenu(); closeModal(); goHome();
    showLogin();
  }

  /* ---- auth form / button delegation ---- */
  authRoot.addEventListener("submit", e => {
    e.preventDefault();
    const f = e.target, d = Object.fromEntries(new FormData(f).entries());
    if (f.dataset.form === "login") {
      if (!/^\S+@\S+\.\S+$/.test(d.email || "")) return showLogin("Enter a valid work email address.");
      if (!d.password) return showLogin("Enter your password.");
      signIn(userFromEmail(d.email.trim(), state.user), "Welcome back!");
    } else if (f.dataset.form === "register") {
      if (!d.name || !d.name.trim()) return showRegister("Please enter your full name.");
      if (!/^\S+@\S+\.\S+$/.test(d.email || "")) return showRegister("Enter a valid work email address.");
      if ((d.password || "").length < 8) return showRegister("Password must be at least 8 characters.");
      const u = { name: d.name.trim(), email: d.email.trim(), role: d.dept, dept: d.dept, since: "Today" };
      signIn(u, "Account created — welcome to Company Knowledge!");
    }
  });
  authRoot.addEventListener("click", e => {
    const a = e.target.closest("[data-act]"); if (!a) return;
    const act = a.dataset.act;
    if (act === "sso") return signIn(state.user || { ...ME }, "Signed in with Vantor SSO.");
    if (act === "goto-register") return showRegister();
    if (act === "goto-login") return showLogin();
    if (act === "forgot") return toast("Password reset link sent to your email.");
    if (act === "toggle-pw") {
      const box = a.closest(".fld__box"), inp = box.querySelector("input");
      const show = inp.type === "password"; inp.type = show ? "text" : "password";
      a.innerHTML = show ? ICON.eyeOff({ s: 16 }) : ICON.eye({ s: 16 });
    }
  });

  /* ---- profile popover ---- */
  function closeMenu() {
    const m = $("#pmenu"); if (m) m.remove();
    document.removeEventListener("click", outsideMenu, true);
    $("#profile-btn").setAttribute("aria-expanded", "false");
  }
  function outsideMenu(e) { if (!e.target.closest("#pmenu") && !e.target.closest("#profile-btn")) closeMenu(); }
  function openMenu() {
    const btn = $("#profile-btn"), r = btn.getBoundingClientRect();
    const m = document.createElement("div");
    m.className = "pmenu"; m.id = "pmenu";
    m.innerHTML = R.profileMenu(state.user, state.theme);
    menuRoot.appendChild(m);
    m.style.left = r.left + "px";
    m.style.bottom = (window.innerHeight - r.top + 8) + "px";
    requestAnimationFrame(() => {
      const mr = m.getBoundingClientRect();
      if (mr.right > window.innerWidth - 12) m.style.left = Math.max(12, window.innerWidth - 12 - mr.width) + "px";
      m.classList.add("is-open");
    });
    btn.setAttribute("aria-expanded", "true");
    setTimeout(() => document.addEventListener("click", outsideMenu, true), 0);
  }
  $("#profile-btn").addEventListener("click", e => { e.stopPropagation(); $("#pmenu") ? closeMenu() : openMenu(); });

  menuRoot.addEventListener("click", e => {
    const a = e.target.closest("[data-act]"); if (!a) return;
    const act = a.dataset.act;
    if (act === "signout") return signOut();
    if (act === "open-profile") { closeMenu(); return openProfile(); }
    if (act === "open-tweaks") { closeMenu(); twk.classList.add("is-open"); return; }
    if (act === "profile-theme") { toggleTheme(); const m = $("#pmenu"); if (m) m.innerHTML = R.profileMenu(state.user, state.theme); return; }
  });

  /* ---- profile modal ---- */
  function closeModal() { modalRoot.innerHTML = ""; }
  function openProfile() {
    const host = document.createElement("div");
    host.className = "modal-host";
    host.innerHTML = R.profileModal(state.user);
    modalRoot.appendChild(host);
  }
  modalRoot.addEventListener("click", e => {
    const a = e.target.closest("[data-act]"); if (!a) return;
    const act = a.dataset.act;
    if (act === "close-modal") return closeModal();
    if (act === "signout") return signOut();
  });
  modalRoot.addEventListener("submit", e => {
    e.preventDefault();
    if (e.target.dataset.form !== "profile") return;
    const d = Object.fromEntries(new FormData(e.target).entries());
    if (!d.name || !d.name.trim()) return toast("Display name can't be empty.");
    const u = { ...state.user, name: d.name.trim(), email: d.email.trim(), role: d.role, dept: d.dept };
    applyUser(u); saveAuth(); closeModal();
    toast("Profile updated.", "ok");
  });

  document.addEventListener("keydown", e => {
    if (e.key !== "Escape") return;
    if ($("#pmenu")) closeMenu();
    else if (modalRoot.firstChild) closeModal();
  });

  function initAuth() {
    const saved = loadAuth();
    const u = (saved && saved.user) || { ...ME };
    applyUser(u);
    if (saved && saved.authed === false) { state.authed = false; showLogin(); }
    else { state.authed = true; saveAuth(); }
  }

  /* ============================================================
     INIT
     ============================================================ */
  hydrateIcons();
  renderRail();
  renderScopebar();
  goHome();
  applyTheme();
  syncTweaks();
  initAuth();
})();
