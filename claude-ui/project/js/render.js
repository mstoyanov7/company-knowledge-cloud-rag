/* ============================================================
   render.js — HTML builders (return strings unless noted)
   ============================================================ */
const R = (() => {
  const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[c]));
  const chev = ICON.chevron({ s: 13 });

  let _user = ME;                      // current identity (set by app)
  const setUser = (u) => { _user = u; };
  const firstName = (n) => String(n || "").trim().split(/\s+/)[0] || "there";
  const initials = (n) => String(n || "").trim().split(/\s+/).slice(0, 2).map(w => w[0] || "").join("").toUpperCase() || "U";

  /* ---------- RAIL: notebooks tree ---------- */
  function notebooks() {
    return `<div class="tree">` + NOTEBOOKS.map(nb => {
      if (nb.restricted) {
        return `<div class="node node--restricted">
          <button class="node__row" data-act="restricted" data-nb="${nb.id}">
            <span class="node__chev" style="visibility:hidden">${chev}</span>
            <span class="node__ico">${ICON.lock({ s: 14 })}</span>
            <span class="node__label">${esc(nb.name)}</span>
            <span class="node__lock">${ICON.lock({ s: 12 })}</span>
          </button></div>`;
      }
      const sections = nb.sections.map(sec => {
        const pages = sec.pages.map(pg => `
          <div class="node node--page">
            <button class="node__row" data-act="page" data-pg="${pg.id}"
              data-label="${esc(pg.title)}" data-path="${esc(nb.name)} ▸ ${esc(sec.name)} ▸ ${esc(pg.title)}">
              <span class="node__chev" style="visibility:hidden">${chev}</span>
              <span class="node__ico">${ICON.page({ s: 13 })}</span>
              <span class="node__label">${esc(pg.title)}</span>
              <span class="node__meta">${pg.edited}</span>
            </button>
          </div>`).join("");
        return `<div class="node">
          <button class="node__row" data-act="toggle">
            <span class="node__chev">${chev}</span>
            <span class="node__ico">${ICON.section({ s: 14 })}</span>
            <span class="node__label">${esc(sec.name)}</span>
            <span class="node__meta">${sec.pages.length}</span>
          </button>
          <div class="node__children">${pages}</div>
        </div>`;
      }).join("");
      return `<div class="node ${nb.id === "nb-hr" ? "is-open" : ""}">
        <button class="node__row" data-act="toggle">
          <span class="node__chev">${chev}</span>
          <span class="node__ico">${ICON[nb.icon]({ s: 15 })}</span>
          <span class="node__label">${esc(nb.name)}</span>
          <span class="node__meta">${nb.pages}</span>
        </button>
        <div class="node__children">${sections}</div>
      </div>`;
    }).join("") + `</div>`;
  }

  /* ---------- RAIL: topics ---------- */
  function topics() {
    return TOPICS.map(t => `
      <button class="topic-row" data-act="topic" data-id="${t.id}" data-label="${esc(t.name)}">
        <span class="topic-row__sw" style="background:${t.color}"></span>
        <span class="topic-row__label">${esc(t.name)}</span>
        <span class="topic-row__meta">${t.count}</span>
      </button>`).join("");
  }

  /* ---------- RAIL: pinned + recent (always below) ---------- */
  function railLists() {
    const liRow = (item, opts) => {
      const pinned = opts.pinned;
      return `<div class="li-wrap">
        <button class="li" data-act="ask" ${item.a ? `data-a="${item.a}"` : ""} data-q="${esc(item.q)}">
          <span class="li__ico">${opts.icon}</span>
          <span class="li__label">${esc(item.q)}</span>
          ${item.time ? `<span class="li__time">${esc(item.time)}</span>` : ""}
        </button>
        <button class="li__pin ${pinned ? "is-pinned" : ""}" data-act="${pinned ? "unpin" : "pin"}"
          data-q="${esc(item.q)}" ${item.a ? `data-a="${item.a}"` : ""} ${item.time ? `data-time="${esc(item.time)}"` : ""}
          title="${pinned ? "Unpin" : "Pin"}" aria-label="${pinned ? "Unpin" : "Pin"}">${ICON.pin({ s: 12 })}</button>
      </div>`;
    };
    const pin = PINNED.length
      ? PINNED.map(p => liRow(p, { pinned: true, icon: ICON.pin({ s: 13 }) })).join("")
      : `<div class="rail__empty">Pin an answer to keep it handy.</div>`;
    const rec = RECENT.map(r => liRow(r, { pinned: PINNED.some(p => p.q === r.q), icon: ICON.clock({ s: 13 }) })).join("");
    return `
      <div class="rail__sectlabel">Pinned answers</div>${pin}
      <div class="rail__sectlabel">Recent <button data-act="clear-recent">Clear</button></div>${rec}`;
  }

  /* ---------- HOME ---------- */
  function home() {
    const grp = (icon, title, sub, items) => `
      <div class="home__group">
        <div class="home__grouph">
          <span class="ic">${icon}</span><b>${title}</b><span class="sub">${sub}</span>
        </div>
        <div class="starts">${items.map(startRow).join("")}</div>
      </div>`;
    const cards = TOPICS.map(t => `
      <button class="topic-card" data-act="topic" data-id="${t.id}" data-label="${esc(t.name)}">
        <div class="topic-card__top">
          <span class="topic-card__ic" style="background:color-mix(in oklch, ${t.color} 18%, transparent);color:${t.color}">${ICON[t.icon]({ s: 16 })}</span>
          <span class="topic-card__n">${t.count} pages</span>
        </div>
        <div class="topic-card__name">${esc(t.name)}</div>
        <div class="topic-card__desc">${esc(t.desc)}</div>
      </button>`).join("");
    return `<div class="home fade-in">
      <div class="home__hello">
        <span class="home__sun">${ICON.sun({ s: 19 })}</span>
        <h1>Good morning, ${esc(firstName(_user.name))}.<span class="accent"></span></h1>
      </div>
      <p class="home__lead">Ask anything across Vantor's OneNote knowledge base — every answer is grounded in source pages you can open and verify. Here's what's relevant to you today.</p>
      ${grp(ICON.refresh({ s: 13 }), "Recently updated", "docs that changed this week", HOME.updated)}
      ${grp(ICON.trend({ s: 13 }), "Trending questions", "what colleagues are asking", HOME.trending)}
      <div class="home__group">
        <div class="home__grouph"><span class="ic">${ICON.layers({ s: 13 })}</span><b>Browse by topic</b><span class="sub">auto-clustered domains</span></div>
        <div class="topic-grid">${cards}</div>
      </div>
    </div>`;
  }
  function startRow(it) {
    const badge = it.badge
      ? `<span class="start__badge start__badge--${it.kind}">${it.kind === "hot" ? ICON.trend({ s: 11 }) : ICON.refresh({ s: 11 })} ${esc(it.badge)}</span>`
      : (it.meta ? `<span class="start__badge">${esc(it.meta)}</span>` : "");
    return `<button class="start" data-act="ask" ${it.a ? `data-a="${it.a}"` : ""} data-q="${esc(it.q)}">
      <span class="start__q">${esc(it.q)}</span>
      <span class="start__meta">${badge}<span class="start__arrow">${ICON.arrowR({ s: 14 })}</span></span>
    </button>`;
  }

  /* ---------- USER message ---------- */
  function userMsg(q) {
    return `<div class="msg msg--user fade-in"><div class="bubble-user">${esc(q)}</div></div>`;
  }

  /* ---------- source-used card ---------- */
  function srcCard(sid, n) {
    const s = SOURCES[sid];
    return `<button class="srccard" data-act="open-src" data-src="${sid}" data-n="${n}">
      <span class="srccard__n">${n}</span>
      <span class="srccard__main">
        <span class="srccard__title">${esc(s.page)}</span>
        <span class="srccard__path">${esc(s.notebook)} ▸ ${esc(s.section)}</span>
      </span>
      <span class="srccard__fresh">${esc(s.edited)}</span>
    </button>`;
  }

  /* ---------- SOURCE PANEL ---------- */
  function sourcePanel(sid, n) {
    const s = SOURCES[sid];
    const path = `<div class="onenote-path">
      <span class="seg2">${esc(s.notebook)}</span>${ICON.chevron({ s: 12 })}
      <span class="seg2">${esc(s.section)}</span>${ICON.chevron({ s: 12 })}
      <span class="seg2 is-page">${esc(s.page)}</span></div>`;
    const body = s.doc.map((b, i) => {
      if (b.h) return `<h5>${esc(b.h)}</h5>`;
      const flag = i === s.relevantIdx ? `<div class="relevant-flag">${ICON.spark2({ s: 12 })} Most relevant to your question</div>` : "";
      return `${flag}<p>${b.p}</p>`;
    }).join("");
    return `
      <div class="source__head">
        <span class="source__kicker"><span class="source__n">${n}</span> Source</span>
        <div class="topbar__spacer"></div>
        <button class="iconbtn" data-act="close-src" aria-label="Close source">${ICON.x({ s: 16 })}</button>
      </div>
      <div class="source__scroll scroll">
        ${path}
        <h2 class="source__title">${esc(s.page)}</h2>
        <div class="source__byline">
          <span class="ed"><span class="mini-ava">${esc(s.init)}</span> ${esc(s.editor)}</span>
          <span>·</span><span>Last edited ${esc(s.editedFull)}</span>
        </div>
        <div class="source__freshrow">
          <span class="chip-meta"><span>${ICON.clock({ s: 12 })}</span> Updated ${esc(s.edited)}</span>
        </div>
        <div class="source__doc">${body}</div>
        <div class="source__links">
          <button class="deeplink" data-act="toast" data-msg="Opening page in OneNote for the web…">
            <span class="deeplink__ic">${ICON.globe({ s: 16 })}</span>
            <span class="deeplink__main"><b>Open in OneNote for the web</b><span>onenote.vantor.com/…/${esc(s.page.toLowerCase().replace(/[^a-z]+/g, "-"))}</span></span>
            <span class="deeplink__go">${ICON.arrowR({ s: 15 })}</span>
          </button>
          <button class="deeplink" data-act="toast" data-msg="Launching the OneNote desktop app…">
            <span class="deeplink__ic">${ICON.monitor({ s: 16 })}</span>
            <span class="deeplink__main"><b>Open in OneNote desktop</b><span>onenote:///Vantor/${esc(s.notebook)}</span></span>
            <span class="deeplink__go">${ICON.arrowR({ s: 15 })}</span>
          </button>
        </div>
      </div>`;
  }

  /* ---------- NO-ANSWER state ---------- */
  function noAnswer(q) {
    return `<div class="statecard statecard--gap fade-in">
      <div class="statecard__icon">${ICON.alert({ s: 20 })}</div>
      <h3>No grounded answer found</h3>
      <p>I couldn't find anything in Vantor's OneNote that reliably answers <strong>"${esc(q)}"</strong>. Rather than guess, I'd rather be honest — this looks like a genuine gap in the docs.</p>
      <div class="statecard__row">
        <button class="btn btn--accent" data-act="flag-gap" data-q="${esc(q)}">${ICON.flag({ s: 14 })} Flag this gap to Finance</button>
        <button class="btn" data-act="ask" data-a="A_expense" data-q="How do I expense a client dinner?">Try a related question</button>
      </div>
      <div class="statecard__hint">${ICON.info({ s: 14 })}<span>Flagged gaps go to the relevant notebook owner with your question attached, so missing docs get written. You'll be notified when it's answered.</span></div>
    </div>`;
  }

  /* ---------- RESTRICTED state ---------- */
  function restricted(nb) {
    return `<div class="statecard statecard--lock fade-in">
      <div class="statecard__icon">${ICON.lock({ s: 20 })}</div>
      <h3>${esc(nb.name)} is restricted</h3>
      <p>This notebook holds ${nb.pages} pages scoped to the <strong>${esc(nb.owner)}</strong>. Your current role (People Operations) doesn't include access, so the assistant won't surface answers or snippets from it.</p>
      <div class="statecard__row">
        <button class="btn btn--accent" data-act="toast" data-msg="Access request sent to ${esc(nb.owner)}." data-kind="ok">${ICON.shield({ s: 14 })} Request access</button>
        <button class="btn" data-act="toast" data-msg="The notebook owner has been notified.">${ICON.user({ s: 14 })} Notify owner</button>
      </div>
      <div class="statecard__hint">${ICON.info({ s: 14 })}<span>Permissions mirror OneNote and your Vantor SSO group membership. Access is granted by the notebook owner, not by the assistant.</span></div>
    </div>`;
  }

  /* ============================================================
     AUTH — login & register screens
     ============================================================ */
  function field(o) {
    return `<label class="fld">
      <span class="fld__lbl">${esc(o.label)}</span>
      <span class="fld__box">
        <span class="fld__ico">${o.icon}</span>
        <input class="fld__in" type="${o.type || "text"}" name="${o.name}" placeholder="${esc(o.ph || "")}"
          ${o.value ? `value="${esc(o.value)}"` : ""} ${o.req === false ? "" : "required"} autocomplete="${o.ac || "off"}" />
        ${o.toggle ? `<button type="button" class="fld__eye" data-act="toggle-pw" tabindex="-1" aria-label="Show password">${ICON.eye({ s: 16 })}</button>` : ""}
      </span>
    </label>`;
  }

  function authShell(inner) {
    return `<div class="auth__bg"></div>
      <div class="auth__panel">
        <div class="auth__brandrow">
          <span class="auth__mark">${ICON.layers({ s: 19 })}</span>
          <div><div class="auth__brand">Company Knowledge</div>
          <div class="auth__brandsub">Assistant · powered by OneNote</div></div>
        </div>
        ${inner}
        <div class="auth__legal">Vantor internal tool · Access is governed by your SSO group membership.</div>
      </div>`;
  }

  function loginScreen(err) {
    return authShell(`
      <h1 class="auth__h">Sign in</h1>
      <p class="auth__sub">Welcome back. Sign in to search your company's knowledge base.</p>
      ${err ? `<div class="auth__err">${ICON.alert({ s: 14 })} ${esc(err)}</div>` : ""}
      <button class="auth__sso" data-act="sso">${ICON.shield({ s: 17 })} Continue with Vantor SSO</button>
      <div class="auth__or"><span>or sign in with email</span></div>
      <form class="auth__form" data-form="login">
        ${field({ label: "Work email", name: "email", type: "email", icon: ICON.mail({ s: 16 }), ph: "you@vantor.com", value: _user.email, ac: "username" })}
        ${field({ label: "Password", name: "password", type: "password", icon: ICON.lock({ s: 16 }), ph: "••••••••", toggle: true, ac: "current-password" })}
        <div class="auth__rowbtwn">
          <label class="auth__check"><input type="checkbox" name="remember" checked /> <span>Keep me signed in</span></label>
          <button type="button" class="auth__link" data-act="forgot">Forgot password?</button>
        </div>
        <button type="submit" class="auth__submit">Sign in ${ICON.arrowR({ s: 15 })}</button>
      </form>
      <div class="auth__foot">Don't have access yet? <button class="auth__link" data-act="goto-register">Request an account</button></div>`);
  }

  function registerScreen(err) {
    const depts = DEPTS.map(d => `<option value="${esc(d)}">${esc(d)}</option>`).join("");
    return authShell(`
      <button class="auth__back" data-act="goto-login">${ICON.chevron({ s: 14, w: 2.4 })} Back to sign in</button>
      <h1 class="auth__h">Request access</h1>
      <p class="auth__sub">New here? Request an account — the relevant notebook owners approve access based on your role.</p>
      ${err ? `<div class="auth__err">${ICON.alert({ s: 14 })} ${esc(err)}</div>` : ""}
      <form class="auth__form" data-form="register">
        ${field({ label: "Full name", name: "name", icon: ICON.user({ s: 16 }), ph: "Alex Morgan" })}
        ${field({ label: "Work email", name: "email", type: "email", icon: ICON.mail({ s: 16 }), ph: "alex.morgan@vantor.com" })}
        <label class="fld">
          <span class="fld__lbl">Department</span>
          <span class="fld__box">
            <span class="fld__ico">${ICON.building({ s: 16 })}</span>
            <select class="fld__in fld__sel" name="dept">${depts}</select>
            <span class="fld__chev">${ICON.chevDown({ s: 15 })}</span>
          </span>
        </label>
        ${field({ label: "Create password", name: "password", type: "password", icon: ICON.lock({ s: 16 }), ph: "At least 8 characters", toggle: true, ac: "new-password" })}
        <label class="auth__check auth__check--block"><input type="checkbox" name="agree" required /> <span>I understand access is scoped to my role and audited.</span></label>
        <button type="submit" class="auth__submit">Create account ${ICON.arrowR({ s: 15 })}</button>
      </form>
      <div class="auth__foot">Already have an account? <button class="auth__link" data-act="goto-login">Sign in</button></div>`);
  }

  /* ============================================================
     PROFILE — popover menu + modal
     ============================================================ */
  function bigAva(u) { return `<span class="p-ava">${esc(initials(u.name))}</span>`; }

  function profileMenu(u, theme) {
    return `<div class="pmenu__id">
        ${bigAva(u)}
        <div class="pmenu__idmain">
          <b>${esc(u.name)}</b>
          <span>${esc(u.email)}</span>
        </div>
      </div>
      <div class="pmenu__rolepill">${ICON.badge({ s: 12 })} ${esc(u.role)}</div>
      <div class="pmenu__div"></div>
      <button class="pmenu__item" data-act="open-profile">${ICON.user({ s: 16 })} <span>Account &amp; profile</span></button>
      <button class="pmenu__item" data-act="profile-theme">${theme === "dark" ? ICON.sun({ s: 16 }) : ICON.moon({ s: 16 })} <span>Switch to ${theme === "dark" ? "light" : "dark"} mode</span></button>
      <button class="pmenu__item" data-act="open-tweaks">${ICON.settings({ s: 16 })} <span>Preferences</span></button>
      <div class="pmenu__div"></div>
      <button class="pmenu__item pmenu__item--danger" data-act="signout">${ICON.logout({ s: 16 })} <span>Sign out</span></button>`;
  }

  function profileModal(u) {
    const accessible = NOTEBOOKS.filter(n => !n.restricted);
    const totalPages = accessible.reduce((a, n) => a + n.pages, 0);
    const roleOpts = ROLES.map(r => `<option value="${esc(r)}" ${r === u.role ? "selected" : ""}>${esc(r)}</option>`).join("");
    return `<div class="modal__scrim" data-act="close-modal"></div>
      <div class="modal pmodal" role="dialog" aria-label="Profile">
        <button class="modal__x" data-act="close-modal" aria-label="Close">${ICON.x({ s: 17 })}</button>
        <div class="pmodal__head">
          <span class="p-ava p-ava--xl">${esc(initials(u.name))}</span>
          <div class="pmodal__headmain">
            <h2>${esc(u.name)}</h2>
            <div class="pmodal__meta">
              <span>${ICON.mail({ s: 13 })} ${esc(u.email)}</span>
              <span>${ICON.badge({ s: 13 })} ${esc(u.role)}</span>
            </div>
          </div>
        </div>

        <div class="pmodal__stats">
          <div class="pstat"><b>${accessible.length}</b><span>Notebooks</span></div>
          <div class="pstat"><b>${totalPages.toLocaleString()}</b><span>Pages accessible</span></div>
          <div class="pstat"><b>${esc(u.since)}</b><span>Member since</span></div>
        </div>

        <form class="pmodal__form" data-form="profile">
          <div class="pmodal__sect">Profile details</div>
          ${field({ label: "Display name", name: "name", icon: ICON.user({ s: 16 }), value: u.name })}
          ${field({ label: "Work email", name: "email", type: "email", icon: ICON.mail({ s: 16 }), value: u.email })}
          <div class="pmodal__grid2">
            <label class="fld">
              <span class="fld__lbl">Role</span>
              <span class="fld__box">
                <span class="fld__ico">${ICON.badge({ s: 16 })}</span>
                <select class="fld__in fld__sel" name="role">${roleOpts}</select>
                <span class="fld__chev">${ICON.chevDown({ s: 15 })}</span>
              </span>
            </label>
            ${field({ label: "Department", name: "dept", icon: ICON.building({ s: 16 }), value: u.dept })}
          </div>
          <div class="pmodal__hint">${ICON.info({ s: 13 })} Your role tailors the home suggestions and which notebooks answers draw from.</div>
          <div class="pmodal__actions">
            <button type="button" class="btn" data-act="signout">${ICON.logout({ s: 14 })} Sign out</button>
            <div class="topbar__spacer"></div>
            <button type="button" class="btn" data-act="close-modal">Cancel</button>
            <button type="submit" class="btn btn--accent">${ICON.check({ s: 14 })} Save changes</button>
          </div>
        </form>
      </div>`;
  }

  return { esc, initials, notebooks, topics, railLists, home, userMsg, srcCard, sourcePanel, noAnswer, restricted,
    setUser, loginScreen, registerScreen, profileMenu, profileModal };
})();
