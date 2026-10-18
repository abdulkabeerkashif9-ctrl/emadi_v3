"use strict";
/* Fleet Manager UI — vanilla JS, hash routed, no build step. */

// ───────────────────────────── helpers ─────────────────────────────
const ICONS = {
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  server: '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
  box: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  settings: '<path d="M20 7h-9M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8M21 3v5h-5M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16M8 16H3v5"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (n, c = "") => `<svg class="ic ${c}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ""}</svg>`;

const ST = {
  up: ["Active", "green"], down: ["Down", "red"], error: ["Broken", "red"], creating: ["Creating", "amber"],
  ready: ["Ready", "green"], new: ["Not set up", "gray"], bootstrapped: ["Connected", "blue"], configuring: ["Configuring", "amber"],
  done: ["Done", "green"], failed: ["Failed", "red"], running: ["Running", "amber"],
};
const badge = s => { const [l, c] = ST[s] || [s, "gray"]; return `<span class="badge ${c}"><i></i>${esc(l)}</span>`; };
const meter = p => `<div class="meter ${p > 90 ? "hi" : p > 70 ? "mid" : ""}"><i style="width:${Math.max(0, Math.min(100, p))}%"></i></div>`;
const ver = v => String(v || "").replace("version-", "v");
const siteUrl = s => `${s.ssl ? "https" : "http"}://${s.domain}`;
function ago(ts) {
  if (!ts) return "—";
  const d = new Date(String(ts).replace(" ", "T") + "Z"), s = (Date.now() - d) / 1000;
  if (isNaN(s)) return String(ts);
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + " min ago";
  if (s < 86400) return Math.floor(s / 3600) + " h ago";
  return Math.floor(s / 86400) + " d ago";
}
function copyText(t) {
  const done = () => toast("Copied");
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t).then(done, done);
  const ta = document.createElement("textarea"); ta.value = t; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch { /* ignore */ } ta.remove(); done();
}
function toast(msg, err) {
  const el = document.createElement("div"); el.className = "toast" + (err ? " err" : ""); el.textContent = msg;
  $("#toasts").appendChild(el); setTimeout(() => el.remove(), err ? 7000 : 2600);
}
async function api(method, url, body) {
  const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  let data = null; try { data = await r.json(); } catch { /* not json */ }
  if (r.status === 401 && S.user) { S.user = null; showAuth(); }
  if (!r.ok) {
    const d = data && data.detail;
    const e = new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : "Request failed (" + r.status + ")");
    e.status = r.status; e.detail = d; throw e;
  }
  return data;
}
async function busy(btn, fn) {
  if (btn) { btn.disabled = true; btn.dataset.h = btn.innerHTML; btn.innerHTML = `<span class="spin"></span>${btn.textContent.trim()}`; }
  try { return await fn(); }
  catch (e) { if (e.status !== 401) toast(e.message, true); }
  finally { if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = btn.dataset.h; } }
}

const S = { user: null, page: "", sites: [], servers: [], apps: [], jobs: [], versions: null, running: undefined, ui: { q: "", f: "all" } };
const URLS = { sites: "/api/sites", servers: "/api/servers", apps: "/api/apps", jobs: "/api/jobs" };
const load = (...n) => Promise.all(n.map(async k => { S[k] = await api("GET", URLS[k]); }));

function cleanLog(raw) {
  const lines = String(raw).replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").split(/\r\n|\r|\n/);
  const out = []; let key = null;
  for (const l of lines) {
    const m = l.match(/^(.*?)\s*:?\s*\[[=\- >#]*\]\s*\d+%/) || (/^\(Reading database \.\.\. \d+%/.test(l) ? [l, "readdb"] : null);
    if (m) { if (m[1] === key) { out[out.length - 1] = l; continue; } key = m[1]; out.push(l); continue; }
    key = null; out.push(l);
  }
  return out.slice(-4000).join("\n");
}

// ───────────────────────────── overlays ─────────────────────────────
function dialog(title, body, footer, opts = {}) {
  const o = document.createElement("div"); o.className = "overlay";
  o.innerHTML = `<div class="dialog ${opts.wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><header><h2>${esc(title)}</h2><button class="xbtn" data-close aria-label="Close">${icon("x")}</button></header><div class="body">${body}</div><footer>${footer || ""}</footer></div>`;
  o.close = () => o.remove();
  o.addEventListener("mousedown", e => { if (e.target === o) o.close(); });
  o.addEventListener("click", e => { if (e.target.closest("[data-close]")) o.close(); });
  document.body.appendChild(o);
  const f = $("input:not([type=checkbox]),textarea,select", o); if (f && !opts.noFocus) f.focus();
  return o;
}
function confirmBox(title, html, okLabel = "Confirm", danger = false) {
  return new Promise(res => {
    const d = dialog(title, `<p class="muted" style="margin:0 0 6px">${html}</p>`,
      `<button class="btn" data-close>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" id="ok">${esc(okLabel)}</button>`);
    let done = false; const close = d.close;
    d.close = () => { close(); if (!done) { done = true; res(false); } };
    $("#ok", d).onclick = () => { done = true; close(); res(true); };
  });
}
let drawer = null;
function closeDrawer() { if (drawer) drawer._stop(); }
function openJob(id, title) {
  closeDrawer();
  const d = document.createElement("aside"); d.className = "drawer"; d.setAttribute("aria-label", "Job log");
  d.innerHTML = `<header><h2>${esc(title || "Job #" + id)}</h2><span id="jst"></span><button class="xbtn" data-x aria-label="Close">${icon("x")}</button></header><pre class="log" id="jlog">Waiting for output…</pre><footer><span id="jmeta">Job #${id}</span><button class="btn sm" id="jcopy">${icon("copy")}Copy log</button></footer>`;
  document.body.appendChild(d); drawer = d;
  let raw = "", off = 0, stopped = false, finished = false;
  d._stop = () => { stopped = true; d.remove(); drawer = null; if (finished) route(true); };
  $("[data-x]", d).onclick = () => d._stop();
  $("#jcopy", d).onclick = () => copyText(cleanLog(raw));
  const logEl = $("#jlog", d);
  (async function poll() {
    if (stopped) return;
    try {
      const j = await api("GET", `/api/jobs/${id}?offset=${off}`);
      if (j.log) {
        raw += j.log; off = j.next_offset;
        const follow = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 40;
        logEl.innerHTML = cleanLog(raw).split("\n").map(l => {
          const e = esc(l);
          if (/^(>>>|==)/.test(l)) return `<b>${e}</b>`;
          if (/^!!!|Traceback|FAILED|\bError\b/.test(l)) return `<span class="er">${e}</span>`;
          if (/^!!|\bWARN/i.test(l)) return `<span class="wn">${e}</span>`;
          return e;
        }).join("\n");
        if (follow) logEl.scrollTop = logEl.scrollHeight;
      } else if (!raw && j.status !== "running") logEl.textContent = "(no output)";
      $("#jst", d).innerHTML = badge(j.status);
      if (j.status !== "running") { finished = true; $("#jmeta", d).textContent = `Job #${id} · finished`; route(true); return; }
    } catch (e) { if (e.status === 401) return; }
    setTimeout(poll, 1400);
  })();
}
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { const o = $$(".overlay").pop(); if (o) o.close(); else if (drawer) drawer._stop(); }
  if (e.key === "Enter" && e.target.matches && e.target.matches("tr[data-href]")) location.hash = e.target.dataset.href;
});

// ───────────────────────────── shell & routing ─────────────────────────────
const NAV = [["sites", "Sites", "globe"], ["servers", "Servers", "server"], ["apps", "Apps", "box"], ["jobs", "Jobs", "activity"], ["settings", "Settings", "settings"]];
function buildShell() {
  $("#root").innerHTML = `<div class="app">
    <aside class="side"><div class="brand"><div class="mark">${icon("zap")}</div><span>Fleet Manager</span></div>
      <nav class="nav">${NAV.map(([k, l, i]) => `<a href="#/${k}" data-nav="${k}">${icon(i)}<span>${l}</span><em class="count" id="cnt-${k}" hidden></em></a>`).join("")}</nav>
      <div class="grow"></div>
      <div class="me"><div class="av">${esc((S.user || "?")[0])}</div><div class="nm">${esc(S.user)}</div><button data-act="logout" title="Log out" aria-label="Log out">${icon("logout")}</button></div>
    </aside>
    <div class="main"><header class="top"><div class="crumbs" id="crumbs"></div><div class="grow"></div><div class="acts"><span id="pill"></span><span class="acts" id="pageacts"></span></div></header>
    <main class="view" id="view"></main></div></div>`;
}
const crumbHtml = c => (c || []).map(([l, h], i, a) => (i < a.length - 1 ? `<a href="${h}">${esc(l)}</a><span class="sep">/</span>` : `<span class="cur">${esc(l)}</span>`)).join("");
const skeleton = () => `<div class="skel" style="height:28px;width:220px;margin-bottom:18px"></div><div class="skel" style="height:44px;margin-bottom:10px"></div><div class="skel" style="height:260px"></div>`;
function paintPill() {
  const n = S.running || 0, el = $("#pill");
  if (el) el.innerHTML = n ? `<button class="jobpill" data-act="jobs"><i></i>${n} job${n > 1 ? "s" : ""} running</button>` : "";
}
function paintCounts() {
  const set = (k, n) => { const el = $("#cnt-" + k); if (el) { el.hidden = !n; el.textContent = n; } };
  set("sites", S.sites.length); set("servers", S.servers.length);
}
const AUTO = new Set(["sites", "site", "servers", "server", "jobs"]);
let seq = 0;
async function route(silent = false) {
  if (!S.user || !$("#view")) return;
  if (silent && !AUTO.has(S.page)) return;
  const hash = location.hash || "#/sites", my = ++seq;
  let hit = null;
  for (const [re, fn, key] of ROUTES) { const m = hash.match(re); if (m) { hit = [fn, m.slice(1), key]; break; } }
  if (!hit) { location.hash = "#/sites"; return; }
  S.page = hit[2];
  $$("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === hit[2].replace(/^(site|server|newsite)$/, m => ({ site: "sites", server: "servers", newsite: "sites" }[m]))));
  const view = $("#view"), y = window.scrollY;
  if (!silent) view.innerHTML = skeleton();
  try {
    const p = await hit[0](...hit[1]);
    if (my !== seq) return;
    $("#crumbs").innerHTML = crumbHtml(p.crumbs); $("#pageacts").innerHTML = p.actions || "";
    document.title = (p.crumbs.at(-1)[0] || "Fleet Manager") + " · Fleet Manager";
    view.innerHTML = p.html; p.mount && p.mount(view); paintCounts(); paintPill();
    if (silent) window.scrollTo(0, y); else window.scrollTo(0, 0);
  } catch (e) {
    if (my !== seq || e.status === 401) return;
    view.innerHTML = `<div class="note bad">${esc(e.message)}</div><a class="btn" href="#/sites">Back to Sites</a>`;
  }
}
async function tick() {
  if (!S.user || document.hidden) return;
  try {
    const jobs = await api("GET", "/api/jobs"), run = jobs.filter(j => j.status === "running").length, prev = S.running;
    S.jobs = jobs; S.running = run; paintPill();
    if (prev !== undefined && prev !== run) route(true);
  } catch { /* offline: ignore */ }
}

// ───────────────────────────── actions (event delegation) ─────────────────────────────
const ACT = {
  newsite: () => { location.hash = "#/new-site"; },
  jobs: () => { location.hash = "#/jobs"; },
  logout: async () => { await api("POST", "/api/auth/logout"); S.user = null; showAuth(); },
  copy: el => copyText(el.dataset.v),
  newserver: () => serverForm(),
  editserver: el => serverForm(S.servers.find(s => s.id === +el.dataset.id)),
  bootstrap: el => bootstrapDialog(S.servers.find(s => s.id === +el.dataset.id)),
  installapps: el => installAppsDialog(S.servers.find(s => s.id === +el.dataset.id)),
  newapp: () => appForm(),
  editapp: el => appForm(S.apps.find(a => a.name === el.dataset.name)),
  delapp: el => busy(null, async () => {
    if (!await confirmBox("Remove app", `Remove <b>${esc(el.dataset.name)}</b> from the registry? Servers keep their copy.`, "Remove", true)) return;
    await api("DELETE", `/api/apps/${encodeURIComponent(el.dataset.name)}`); route();
  }),
  creds: el => credsDialog(S.sites.find(s => s.id === +el.dataset.id)),
  health: el => busy(el, async () => { S.sites = await api("POST", "/api/sites/health"); toast("Health check complete"); route(true); }),
  forget: el => busy(null, async () => {
    const s = S.sites.find(x => x.id === +el.dataset.id);
    if (!await confirmBox("Remove site", `Remove <b>${esc(s.domain)}</b> from Fleet Manager? The site itself stays on the server and keeps running.`, "Remove", true)) return;
    await api("DELETE", `/api/sites/${s.id}`); location.hash = "#/sites";
  }),
  testssh: el => busy(el, async () => {
    const r = await api("POST", `/api/servers/${el.dataset.id}/test`);
    toast(`SSH works — ${r.os || "connected"}${r.sudo ? "" : " (warning: no passwordless sudo)"}`); route(true);
  }),
  configure: el => busy(null, async () => {
    const s = S.servers.find(x => x.id === +el.dataset.id);
    if (!await confirmBox("Configure server", `This installs MariaDB, Redis, Nginx, Node, bench and ERPNext ${esc(ver(s.version))} on <b>${esc(s.ip)}</b>. It takes 15–30 minutes and you can close the log and keep working.`, "Start setup")) return;
    const r = await api("POST", `/api/servers/${s.id}/configure`); S.running = (S.running || 0) + 1; openJob(r.job_id, `Configuring ${s.name}`); route(true);
  }),
  refresh: el => busy(el, async () => { await api("POST", `/api/servers/${el.dataset.id}/refresh`); toast("Server refreshed"); route(true); }),
  delserver: el => busy(null, async () => {
    const s = S.servers.find(x => x.id === +el.dataset.id);
    if (!await confirmBox("Remove server", `Remove <b>${esc(s.name)}</b> and its ${s.site_count} site record(s) from Fleet Manager? Nothing is deleted on the VPS.`, "Remove", true)) return;
    await api("DELETE", `/api/servers/${s.id}`); location.hash = "#/servers";
  }),
  job: el => openJob(+el.dataset.id, el.dataset.t),
  runjob: el => { const j = S.jobs.find(x => x.status === "running" && x.title.includes(el.dataset.q)); if (j) openJob(j.id, j.title); else { location.hash = "#/jobs"; } },
};
document.addEventListener("click", e => {
  const a = e.target.closest("[data-act]");
  if (a) { e.preventDefault(); const f = ACT[a.dataset.act]; if (f) f(a, e); return; }
  const tr = e.target.closest("tr[data-href]");
  if (tr && !e.target.closest("a,button")) location.hash = tr.dataset.href;
});

// ───────────────────────────── auth ─────────────────────────────
async function showAuth() {
  closeDrawer(); $$(".overlay").forEach(o => o.remove());
  const st = await api("GET", "/api/auth/state");
  if (st.user) { S.user = st.user; return startApp(); }
  $("#root").innerHTML = `<div class="auth"><div class="box"><div class="brand"><div class="mark">${icon("zap")}</div><span>Fleet Manager</span></div>
    <div class="card"><h1>${st.setup_needed ? "Create your account" : "Sign in"}</h1><p>${st.setup_needed ? "First run — choose the administrator login." : "Manage your ERPNext servers and sites."}</p>
    <form id="f"><label class="l">Username</label><input name="username" autocomplete="username" required minlength="3" autofocus>
    <label class="l">Password${st.setup_needed ? ' <span class="faint">(min. 8 characters)</span>' : ""}</label><input name="password" type="password" autocomplete="${st.setup_needed ? "new-password" : "current-password"}" required minlength="8">
    <div style="margin-top:18px"><button class="btn primary block">${st.setup_needed ? "Create account" : "Sign in"}</button></div></form></div></div></div>`;
  $("#f").onsubmit = e => {
    e.preventDefault(); const btn = $("button", e.target);
    busy(btn, async () => { const r = await api("POST", st.setup_needed ? "/api/auth/setup" : "/api/auth/login", Object.fromEntries(new FormData(e.target))); S.user = r.user; startApp(); });
  };
}
let started = false;
function startApp() {
  buildShell();
  if (!started) { started = true; window.addEventListener("hashchange", () => route()); setInterval(tick, 6000); }
  tick(); route();
}

// ───────────────────────────── pages: sites ─────────────────────────────
function siteRow(s) {
  const apps = (s.apps || "").split(",").filter(Boolean);
  return `<tr data-href="#/sites/${s.id}" tabindex="0"><td><div class="cell-main">${esc(s.domain)}</div><div class="cell-sub">${esc(s.company || "No company name yet")}</div></td>
    <td>${badge(s.status)}</td><td class="hide-sm"><div>${esc(s.server_name)}</div><div class="cell-sub mono">${esc(s.ip)}</div></td>
    <td class="hide-sm"><div class="chips">${apps.slice(0, 3).map(a => `<span class="chip">${esc(a)}</span>`).join("")}${apps.length > 3 ? `<span class="chip">+${apps.length - 3}</span>` : ""}</div></td>
    <td class="hide-sm faint">${ago(s.created)}</td></tr>`;
}
function emptyState(ic, title, text, btn) {
  return `<div class="empty"><div class="circle">${icon(ic)}</div><h4>${esc(title)}</h4><p>${text}</p>${btn || ""}</div>`;
}
async function pSites() {
  await load("sites", "servers");
  const ready = S.servers.some(s => s.status === "ready");
  return {
    crumbs: [["Sites"]],
    actions: `<button class="btn primary" data-act="newsite" ${ready ? "" : 'disabled title="Set up a server first"'}>${icon("plus")}New Site</button>`,
    html: `<div class="page-head"><h1>Sites</h1></div><p class="sub">All ERPNext sites across your servers.</p>
      <div class="toolbar"><div class="search">${icon("search")}<input id="q" placeholder="Search sites" value="${esc(S.ui.q)}" autocomplete="off" aria-label="Search sites"></div><div class="seg" id="seg"></div>
      <span class="grow" style="flex:1"></span><button class="btn" data-act="health">${icon("refresh")}Check health</button></div>
      <div class="card tbl" id="list"></div>`,
    mount() {
      const bad = s => s.status === "down" || s.status === "error";
      const draw = () => {
        const q = S.ui.q.trim().toLowerCase(), f = S.ui.f;
        const cnt = { all: S.sites.length, up: S.sites.filter(s => s.status === "up").length, bad: S.sites.filter(bad).length };
        $("#seg").innerHTML = [["all", "All"], ["up", "Active"], ["bad", "Needs attention"]].map(([k, l]) => `<button data-f="${k}" class="${f === k ? "on" : ""}">${l}<span class="n">${cnt[k]}</span></button>`).join("");
        const rows = S.sites.filter(s => (f === "all" || (f === "up" ? s.status === "up" : bad(s))) && (!q || `${s.domain} ${s.company} ${s.server_name} ${s.ip}`.toLowerCase().includes(q)));
        $("#list").innerHTML = !S.sites.length
          ? emptyState("globe", "No sites yet", ready ? "Create your first ERPNext site in a few clicks." : "Add a server and finish its setup first, then you can create sites.",
            ready ? `<button class="btn primary" data-act="newsite">${icon("plus")}New Site</button>` : `<a class="btn primary" href="#/servers">Go to Servers</a>`)
          : !rows.length ? emptyState("search", "No matching sites", "Try a different search or filter.")
            : `<table><thead><tr><th>Site</th><th>Status</th><th class="hide-sm">Server</th><th class="hide-sm">Apps</th><th class="hide-sm">Created</th></tr></thead><tbody>${rows.map(siteRow).join("")}</tbody></table>`;
      };
      draw();
      $("#q").oninput = e => { S.ui.q = e.target.value; draw(); };
      $("#seg").onclick = e => { const b = e.target.closest("[data-f]"); if (b) { S.ui.f = b.dataset.f; draw(); } };
    },
  };
}

async function pSite(id, tab = "overview") {
  await load("sites", "servers", "jobs");
  const s = S.sites.find(x => x.id === +id); if (!s) throw new Error("Site not found");
  const srv = S.servers.find(x => x.id === s.server_id) || {};
  const apps = (s.apps || "").split(",").filter(Boolean);
  const running = S.jobs.find(j => j.status === "running" && j.title.includes(s.domain));
  const tabs = [["overview", "Overview"], ["apps", `Apps (${apps.length + 1})`], ["activity", "Activity"]];
  let body = "";
  if (tab === "apps") {
    const reg = Object.fromEntries(S.apps.map(a => [a.name, a]));
    body = `<div class="card tbl"><table><thead><tr><th>App</th><th>Repository</th><th>Branch</th></tr></thead><tbody>
      <tr><td><div class="cell-main">Frappe Framework</div><div class="cell-sub mono">frappe</div></td><td class="mono faint">github.com/frappe/frappe</td><td class="mono">${esc(ver(srv.version))}</td></tr>
      ${apps.map(n => { const a = reg[n]; return `<tr><td><div class="cell-main">${esc(a ? a.title : n)}</div><div class="cell-sub mono">${esc(n)}</div></td><td class="mono faint">${esc(a ? a.git_url.replace(/^https?:\/\//, "") : "—")}</td><td class="mono">${esc(a ? (a.branch || ver(srv.version)) : "—")}</td></tr>`; }).join("")}</tbody></table></div>`;
  } else if (tab === "activity") {
    const js = S.jobs.filter(j => j.title.includes(s.domain));
    body = `<div class="card tbl">${js.length ? `<table><thead><tr><th>Job</th><th>Status</th><th>Started</th><th></th></tr></thead><tbody>${js.map(j => `<tr><td>${esc(j.title)}</td><td>${badge(j.status)}</td><td class="faint">${ago(j.created)}</td><td style="text-align:right"><button class="btn sm" data-act="job" data-id="${j.id}" data-t="${esc(j.title)}">View log</button></td></tr>`).join("")}</tbody></table>` : emptyState("activity", "No activity", "Jobs for this site will appear here.")}</div>`;
  } else {
    const chk = s.checked_at ? `HTTP ${s.http_code ?? "—"} · checked ${ago(s.checked_at)}` : "Not checked yet";
    body = `${running ? `<div class="note warn" style="display:flex;align-items:center;gap:12px"><span style="flex:1">This site is being set up…</span><button class="btn sm" data-act="runjob" data-q="${esc(s.domain)}">View progress</button></div>` : ""}
      ${s.status === "error" && !running ? `<div class="note bad">This site is marked broken. Check the Activity tab for the last job log, or press <b>Check health</b>.</div>` : ""}
      <div class="cards"><div class="card pad"><h3>Site information</h3><div class="kv">
        <div>Domain</div><div><span class="copy" data-act="copy" data-v="${esc(s.domain)}"><span class="mono">${esc(s.domain)}</span>${icon("copy")}</span></div>
        <div>Company</div><div>${esc(s.company || "—")}</div>
        <div>Health</div><div>${badge(s.status)} <span class="faint" style="margin-left:6px">${esc(chk)}</span></div>
        <div>Server</div><div><a href="#/servers/${s.server_id}" style="text-decoration:underline">${esc(s.server_name)}</a> <span class="mono faint">${esc(s.ip)}</span></div>
        <div>HTTPS</div><div>${s.ssl ? "Enabled on server" : "Not enabled on server"}</div>
        <div>Created</div><div>${ago(s.created)}</div></div></div>
      <div class="card pad"><h3>Quick actions</h3>
        <div class="act-row"><div class="t"><b>Open site</b><span>${esc(siteUrl(s))}</span></div><a class="btn sm" href="${esc(siteUrl(s))}" target="_blank" rel="noopener">${icon("external")}Visit</a></div>
        <div class="act-row"><div class="t"><b>Administrator login</b><span>Username and generated password</span></div><button class="btn sm" data-act="creds" data-id="${s.id}">${icon("key")}Show</button></div>
        <div class="act-row"><div class="t"><b>Check health</b><span>Request the site from this machine</span></div><button class="btn sm" data-act="health">${icon("refresh")}Check</button></div></div></div>
      <div class="card pad"><h3>Remove site</h3><div class="act-row" style="padding-top:0"><div class="t"><b>Remove from Fleet Manager</b><span>Only forgets the record here. The site stays on the server.</span></div><button class="btn danger sm" data-act="forget" data-id="${s.id}">Remove</button></div></div>`;
  }
  return {
    crumbs: [["Sites", "#/sites"], [s.domain]],
    actions: `<a class="btn" href="${esc(siteUrl(s))}" target="_blank" rel="noopener">${icon("external")}Visit site</a>`,
    html: `<div class="page-head"><h1>${esc(s.domain)}</h1>${badge(s.status)}</div><p class="sub">${esc(s.company || "No company name yet")} · ${esc(s.server_name)}</p>
      <nav class="tabs">${tabs.map(([k, l]) => `<a href="#/sites/${s.id}/${k}" class="${tab === k ? "on" : ""}">${l}</a>`).join("")}</nav>${body}`,
  };
}

function credsDialog(s) {
  const d = dialog("Administrator login", `<div class="kv" style="grid-template-columns:100px 1fr"><div>Site</div><div class="mono">${esc(siteUrl(s))}</div><div>Username</div><div class="mono">Administrator</div><div>Password</div><div class="mono" id="pw">Loading…</div></div><div class="hint" style="margin-top:12px">The first login opens ERPNext's setup wizard, where you enter the company details.</div>`,
    `<button class="btn" id="cp" disabled>${icon("copy")}Copy password</button><a class="btn primary" href="${esc(siteUrl(s))}" target="_blank" rel="noopener">${icon("external")}Open site</a>`, { noFocus: true });
  api("GET", `/api/sites/${s.id}/credentials`).then(c => {
    $("#pw", d).textContent = c.password || "(unknown — imported site)";
    if (c.password) { $("#cp", d).disabled = false; $("#cp", d).onclick = () => copyText(c.password); }
  }).catch(e => { $("#pw", d).textContent = e.message; });
}

// ───────────────────────────── new site ─────────────────────────────
async function pNewSite() {
  await load("servers", "apps");
  const rec = await api("GET", "/api/recommend");
  if (!rec.length) return {
    crumbs: [["Sites", "#/sites"], ["New Site"]],
    html: `<div class="card">${emptyState("server", "No server is ready", "You need at least one configured server before creating a site.", `<a class="btn primary" href="#/servers">Go to Servers</a>`)}</div>`,
  };
  const W = { domain: "", company: "", server: (rec.find(r => r.recommended) || rec.find(r => r.ok) || rec[0]).id, apps: new Set(["erpnext"]), dns: false, ssl: false, check: null, n: 0 };
  const closure = sel => {
    const reg = Object.fromEntries(S.apps.map(a => [a.name, a])), out = new Set();
    const add = n => { if (out.has(n) || !reg[n]) return; (reg[n].requires || "").split(",").filter(Boolean).forEach(add); out.add(n); };
    sel.forEach(add); return out;
  };
  const srv = () => S.servers.find(s => s.id === W.server) || {};
  const missing = () => [...closure(W.apps)].filter(n => !(srv().apps || []).includes(n));
  return {
    crumbs: [["Sites", "#/sites"], ["New Site"]],
    html: `<div class="page-head"><h1>New Site</h1></div><p class="sub">Choose a domain, a server and the apps to install.</p>
    <div class="ns"><div>
      <section class="card sec"><h3><span class="n">1</span>Site</h3>
        <label class="l" for="dom">Domain</label><input id="dom" placeholder="client.thesmarterp.com" autocomplete="off" spellcheck="false"><div class="domres" id="domres"></div>
        <label class="l" for="co">Company name <span class="faint">(optional)</span></label><input id="co" placeholder="Shown in the Sites list">
      </section>
      <section class="card sec"><h3><span class="n">2</span>Server</h3><div id="srvs"></div></section>
      <section class="card sec"><h3><span class="n">3</span>Apps</h3><div class="appgrid" id="apps"></div><div id="appnote"></div></section>
      <section class="card sec"><h3><span class="n">4</span>Options</h3><div id="opts"></div></section>
    </div>
    <aside class="card ns-side"><h3 style="margin:0 0 12px;font-size:13px">Summary</h3><dl class="sum" id="sum"></dl>
      <button class="btn primary block" id="go">Create site</button><div class="hint" style="text-align:center;margin-top:8px">Usually takes 5–10 minutes.</div></aside></div>`,
    mount(root) {
      const paintSrv = () => {
        $("#srvs", root).innerHTML = rec.map(r => {
          const m = r.metrics;
          return `<label class="opt ${r.id === W.server ? "sel" : ""} ${r.ok ? "" : "dis"}"><input type="radio" name="srv" value="${r.id}" ${r.id === W.server ? "checked" : ""}>
          <div class="g"><div><b>${esc(r.name)}</b> <span class="mono faint">${esc(r.ip)}</span> ${r.recommended ? '<span class="chip ok">Recommended</span>' : ""} ${r.ok ? "" : '<span class="chip warn">Busy</span>'}</div>
          ${m ? `<div class="met"><div class="mini"><span>CPU ${Math.round(100 * m.load / m.cores)}%</span>${meter(100 * m.load / m.cores)}</div><div class="mini"><span>RAM ${m.mem_pct}%</span>${meter(m.mem_pct)}</div><div class="mini"><span>Disk ${m.disk_pct}%</span>${meter(m.disk_pct)}</div><div class="mini"><span>${r.sites} site${r.sites === 1 ? "" : "s"}</span></div></div>` : `<div class="cell-sub">${esc((r.reasons || []).join(", "))}</div>`}
          ${m && r.reasons.length ? `<div class="cell-sub" style="color:var(--amber)">${esc(r.reasons.join(" · "))}</div>` : ""}</div></label>`;
        }).join("");
      };
      const paintApps = () => {
        const eff = closure(W.apps), on = srv().apps || [];
        $("#apps", root).innerHTML = S.apps.map(a => {
          const dep = eff.has(a.name) && !W.apps.has(a.name);
          return `<label class="opt ${eff.has(a.name) ? "sel" : ""}"><input type="checkbox" value="${esc(a.name)}" ${eff.has(a.name) ? "checked" : ""} ${dep ? "disabled" : ""}>
          <div><b>${esc(a.title || a.name)}</b><small>${dep ? "Required by another app" : on.includes(a.name) ? "Already on server" : "Will be downloaded"}</small></div></label>`;
        }).join("");
        const m = missing();
        $("#appnote", root).innerHTML = m.length ? `<div class="note info">Not installed on <b>${esc(srv().name || "")}</b> yet: ${m.map(esc).join(", ")}. You'll be asked to confirm installing ${m.length > 1 ? "them" : "it"} first (a few extra minutes).</div>` : "";
      };
      const paintOpts = () => {
        const zone = W.check && W.check.zone;
        $("#opts", root).innerHTML = `<label class="check ${zone ? "" : "dis"}"><input type="checkbox" id="dns" ${W.dns && zone ? "checked" : ""} ${zone ? "" : "disabled"}><div><b>Create the DNS A record in cPanel</b><div class="hint">${zone ? `Points ${esc(W.domain || "the domain")} to ${esc(srv().ip || "the server")} in zone ${esc(zone)}.` : "Available when the domain belongs to your connected cPanel account."}</div></div></label>
        <label class="check"><input type="checkbox" id="ssl" ${W.ssl ? "checked" : ""}><div><b>Request a free HTTPS certificate</b><div class="hint">Let's Encrypt on the server. Works only once the domain already points to it; skip it if your provider handles HTTPS.</div></div></label>`;
      };
      const paintSum = () => {
        const eff = [...closure(W.apps)];
        $("#sum", root).innerHTML = `<dt>Domain</dt><dd>${esc(W.domain || "—")}</dd><dt>Server</dt><dd>${esc(srv().name || "—")}</dd><dt>Apps</dt><dd>${eff.length ? esc(eff.join(", ")) : "—"}</dd><dt>DNS</dt><dd>${W.dns && W.check && W.check.zone ? "Auto (cPanel)" : "Manual"}</dd>`;
        $("#go", root).disabled = !(W.check && W.check.ok && W.check.domain === W.domain && eff.length);
      };
      const paintCheck = (loading) => {
        const c = W.check, el = $("#domres", root);
        if (loading) { el.innerHTML = `<span class="inf">Checking…</span>`; return; }
        el.innerHTML = !c ? "" : c.problems.map(p => `<span class="bad">✕ ${esc(p)}</span>`).join("") + c.notes.map(n => `<span class="inf">${esc(n)}</span>`).join("") + (c.ok ? `<span class="ok">✓ Domain can be used</span>` : "");
      };
      paintSrv(); paintApps(); paintOpts(); paintSum();
      let timer = null;
      $("#dom", root).oninput = e => {
        W.domain = e.target.value.trim().toLowerCase(); W.check = null; paintSum(); paintOpts();
        clearTimeout(timer); const my = ++W.n;
        if (W.domain.length < 4 || !W.domain.includes(".")) { paintCheck(); return; }
        paintCheck(true);
        timer = setTimeout(async () => {
          try { const c = await api("POST", "/api/domain/check", { domain: W.domain }); if (my !== W.n) return; W.check = c; W.domain = c.domain; }
          catch (err) { if (my !== W.n) return; W.check = { ok: false, problems: [err.message], notes: [] }; }
          paintCheck(); paintOpts(); paintSum();
        }, 450);
      };
      $("#co", root).oninput = e => { W.company = e.target.value; };
      $(".ns", root).addEventListener("change", e => {
        if (e.target.name === "srv") { W.server = +e.target.value; paintSrv(); paintApps(); paintOpts(); paintSum(); }
        else if (e.target.closest("#apps")) { e.target.checked ? W.apps.add(e.target.value) : W.apps.delete(e.target.value); paintApps(); paintSum(); }
        else if (e.target.id === "dns") { W.dns = e.target.checked; paintSum(); }
        else if (e.target.id === "ssl") W.ssl = e.target.checked;
      });
      $("#go", root).onclick = e => busy(e.currentTarget, async () => {
        const apps = [...W.apps];
        const pre = await api("POST", "/api/sites/precheck", { server_id: W.server, apps });
        const miss = pre.missing_on_server;
        if (miss.length) {
          const names = miss.map(n => (S.apps.find(a => a.name === n) || {}).title || n);
          if (!await confirmBox("Install missing apps?", `<b>${esc(names.join(", "))}</b> ${names.length > 1 ? "are" : "is"} not installed on <b>${esc(srv().name)}</b>. Install ${names.length > 1 ? "them" : "it"} on the server too, then create the site? This downloads from git and builds, which takes a few minutes.`, "Install and create")) return;
        }
        const r = await api("POST", "/api/sites", { domain: W.domain, company: W.company, server_id: W.server, apps, install_missing: miss.length > 0, add_dns: W.dns && !!(W.check && W.check.zone), enable_ssl: W.ssl });
        S.running = (S.running || 0) + 1; location.hash = `#/sites/${r.site_id}`; openJob(r.job_id, `Creating ${W.domain}`);
      });
    },
  };
}

// ───────────────────────────── servers ─────────────────────────────
async function pServers() {
  await load("servers");
  const rows = S.servers.map(s => {
    const m = s.capacity && s.capacity.metrics;
    const mini = (l, p) => `<div class="mini"><span>${l} ${p}%</span>${meter(p)}</div>`;
    return `<tr data-href="#/servers/${s.id}" tabindex="0"><td><div class="cell-main">${esc(s.name)}</div><div class="cell-sub mono">${esc(s.ip)}</div></td><td>${badge(s.status)}</td>
      <td class="hide-sm">${esc(ver(s.version))}</td><td class="hide-sm">${s.site_count}</td>
      <td class="hide-sm">${m ? mini("CPU", Math.round(100 * m.load / m.cores)) : '<span class="faint">—</span>'}</td><td class="hide-sm">${m ? mini("RAM", m.mem_pct) : ""}</td><td class="hide-sm">${m ? mini("Disk", m.disk_pct) : ""}</td></tr>`;
  }).join("");
  return {
    crumbs: [["Servers"]],
    actions: `<button class="btn primary" data-act="newserver">${icon("plus")}New Server</button>`,
    html: `<div class="page-head"><h1>Servers</h1></div><p class="sub">Your VPS machines running ERPNext benches.</p><div class="card tbl">${S.servers.length
      ? `<table><thead><tr><th>Server</th><th>Status</th><th class="hide-sm">Version</th><th class="hide-sm">Sites</th><th class="hide-sm">CPU</th><th class="hide-sm">Memory</th><th class="hide-sm">Disk</th></tr></thead><tbody>${rows}</tbody></table>`
      : emptyState("server", "No servers yet", "Add the VPS you bought, then Fleet Manager prepares it for ERPNext.", `<button class="btn primary" data-act="newserver">${icon("plus")}New Server</button>`)}</div>`,
  };
}

async function pServer(id, tab = "overview") {
  await load("servers", "sites", "apps", "jobs");
  const s = S.servers.find(x => x.id === +id); if (!s) throw new Error("Server not found");
  const sites = S.sites.filter(x => x.server_id === s.id), ready = s.status === "ready";
  const cap = s.capacity, m = cap && cap.metrics;
  const running = S.jobs.find(j => j.status === "running" && j.title.includes(s.name));
  const tabs = ready ? [["overview", "Overview"], ["apps", `Apps (${s.apps.length})`], ["sites", `Sites (${sites.length})`], ["activity", "Activity"]] : [];
  const acts = ready
    ? `<button class="btn" data-act="refresh" data-id="${s.id}">${icon("refresh")}Refresh</button><button class="btn" data-act="installapps" data-id="${s.id}">${icon("plus")}Install apps</button>`
    : "";
  const go = n => `<li class="${n.done ? "done" : n.cur ? "cur" : ""}"><div class="dot">${n.done ? icon("check") : n.i}</div><div class="b"><b>${n.t}</b><p>${n.p}</p>${n.btn || ""}</div></li>`;
  const done2 = s.status !== "new", conf = s.status === "configuring";
  const stepper = ready ? "" : `<div class="card pad" style="margin-bottom:16px"><h3>Set up this server</h3>
    ${s.last_error ? `<div class="note bad"><b>Last attempt failed:</b> ${esc(s.last_error)}</div>` : ""}
    <ul class="steps">${[
      { i: 1, t: "Server added", p: `${esc(s.ssh_user)}@${esc(s.ip)}:${s.ssh_port} · ERPNext ${esc(ver(s.version))}`, done: true },
      { i: 2, t: "Run the bootstrap script", p: "Copy the script to the VPS and run it once as root. It installs SSH prerequisites and authorizes this app.", done: done2, cur: !done2, btn: `<button class="btn sm" data-act="bootstrap" data-id="${s.id}">${icon("download")}Show script</button>` },
      { i: 3, t: "Test the connection", p: "Checks that Fleet Manager can log in over SSH.", done: s.status === "bootstrapped" || conf, btn: `<button class="btn sm" data-act="testssh" data-id="${s.id}">Test SSH</button>` },
      { i: 4, t: "Configure the server", p: conf ? "Setup is running — this takes 15–30 minutes." : "Installs MariaDB, Redis, Nginx, Node and bench with ERPNext.", cur: !conf && s.status !== "new", done: false,
        btn: conf ? `<button class="btn sm primary" data-act="runjob" data-q="${esc(s.name)}">View progress</button>` : `<button class="btn sm primary" data-act="configure" data-id="${s.id}">Configure server</button>` },
    ].map(go).join("")}</ul></div>`;
  let body = "";
  if (!ready) {
    body = "";
  } else if (tab === "apps") {
    const avail = S.apps.filter(a => !s.apps.includes(a.name));
    body = `<div class="card tbl"><table><thead><tr><th>App</th><th>Status</th></tr></thead><tbody>
      <tr><td><div class="cell-main">Frappe Framework</div><div class="cell-sub mono">frappe</div></td><td><span class="chip ok">Installed</span></td></tr>
      ${s.apps.map(n => { const a = S.apps.find(x => x.name === n); return `<tr><td><div class="cell-main">${esc(a ? a.title : n)}</div><div class="cell-sub mono">${esc(n)}</div></td><td><span class="chip ok">Installed</span></td></tr>`; }).join("")}
      ${avail.map(a => `<tr><td><div class="cell-main faint">${esc(a.title || a.name)}</div><div class="cell-sub mono">${esc(a.name)}</div></td><td><span class="chip">Not installed</span></td></tr>`).join("")}</tbody></table></div>`;
  } else if (tab === "sites") {
    body = `<div class="card tbl">${sites.length ? `<table><thead><tr><th>Site</th><th>Status</th><th class="hide-sm">Apps</th></tr></thead><tbody>${sites.map(x => `<tr data-href="#/sites/${x.id}" tabindex="0"><td><div class="cell-main">${esc(x.domain)}</div><div class="cell-sub">${esc(x.company || "—")}</div></td><td>${badge(x.status)}</td><td class="hide-sm faint">${esc((x.apps || "").split(",").filter(Boolean).join(", "))}</td></tr>`).join("")}</tbody></table>` : emptyState("globe", "No sites on this server", "Sites you create here will be listed.", `<a class="btn primary" href="#/new-site">${icon("plus")}New Site</a>`)}</div>`;
  } else if (tab === "activity") {
    const js = S.jobs.filter(j => j.title.includes(s.name));
    body = `<div class="card tbl">${js.length ? `<table><thead><tr><th>Job</th><th>Status</th><th>Started</th><th></th></tr></thead><tbody>${js.map(j => `<tr><td>${esc(j.title)}</td><td>${badge(j.status)}</td><td class="faint">${ago(j.created)}</td><td style="text-align:right"><button class="btn sm" data-act="job" data-id="${j.id}" data-t="${esc(j.title)}">View log</button></td></tr>`).join("")}</tbody></table>` : emptyState("activity", "No activity", "Jobs for this server will appear here.")}</div>`;
  } else {
    const tile = (k, v, p) => `<div class="card tile"><div class="k">${k}</div><div class="v">${v}</div>${p == null ? "" : meter(p)}</div>`;
    body = `${running ? `<div class="note warn" style="display:flex;align-items:center;gap:12px"><span style="flex:1">A job is running on this server.</span><button class="btn sm" data-act="runjob" data-q="${esc(s.name)}">View progress</button></div>` : ""}
      ${cap && !cap.ok ? `<div class="note warn"><b>Busy:</b> ${esc((cap.reasons || []).join(" · "))}. New sites will prefer other servers.</div>` : ""}
      <div class="tiles">${m ? tile("CPU load", `${(100 * m.load / m.cores).toFixed(0)}%`, 100 * m.load / m.cores) + tile("Memory", `${m.mem_pct}%`, m.mem_pct) + tile("Disk", `${m.disk_pct}%`, m.disk_pct) : ""}${tile("Sites", sites.length)}</div>
      <div class="card pad"><h3>Server information</h3><div class="kv"><div>Address</div><div class="mono">${esc(s.ssh_user)}@${esc(s.ip)}:${s.ssh_port}</div><div>ERPNext</div><div>${esc(ver(s.version))}</div><div>System</div><div>${esc(s.os_info || "—")}</div>
        <div>Resources</div><div>${m ? `${m.cores} CPU · ${Math.round(m.mem_total_mb / 1024 * 10) / 10} GB RAM` : "—"}</div><div>Last refresh</div><div>${ago(s.metrics_at)}</div><div>Host key</div><div class="mono faint">${esc((s.host_fingerprint || "—").replace(/(.{2})(?=.)/g, "$1:").slice(0, 47))}</div></div></div>`;
  }
  return {
    crumbs: [["Servers", "#/servers"], [s.name]],
    actions: acts,
    html: `<div class="page-head"><h1>${esc(s.name)}</h1>${badge(s.status)}<span style="flex:1"></span>
      <button class="btn sm" data-act="editserver" data-id="${s.id}">Edit</button><button class="btn sm danger" data-act="delserver" data-id="${s.id}">Remove</button></div>
      <p class="sub mono" style="font-size:13px">${esc(s.ip)}</p>${stepper}
      ${tabs.length ? `<nav class="tabs">${tabs.map(([k, l]) => `<a href="#/servers/${s.id}/${k}" class="${tab === k ? "on" : ""}">${l}</a>`).join("")}</nav>` : ""}${body}`,
  };
}

function serverForm(s) {
  const open = () => {
    const v = S.versions;
    const locked = s && (s.status === "ready" || s.status === "configuring");
    const d = dialog(s ? "Edit server" : "New server", `<form id="f">
      <div class="row2"><div><label class="l">Name</label><input name="name" required value="${esc(s && s.name)}" placeholder="vps-01"></div><div><label class="l">IP address</label><input name="ip" required value="${esc(s && s.ip)}" placeholder="203.0.113.10"></div></div>
      <div class="row2"><div><label class="l">SSH user</label><input name="ssh_user" value="${esc((s && s.ssh_user) || "root")}"></div><div><label class="l">SSH port</label><input name="ssh_port" type="number" min="1" max="65535" value="${(s && s.ssh_port) || 22}"></div></div>
      <div class="row2"><div><label class="l">Log in with</label><select name="auth_type"><option value="password" ${s && s.auth_type === "password" ? "selected" : ""}>Password</option><option value="key" ${s && s.auth_type === "key" ? "selected" : ""}>Private key</option></select></div>
      <div><label class="l">ERPNext version</label><select name="version" ${locked ? "disabled" : ""}>${v.items.map(i => `<option value="${i.id}" ${((s && s.version) || v.default) === i.id ? "selected" : ""}>${esc(i.label)}</option>`).join("")}</select></div></div>
      <label class="l">Password or private key ${s ? '<span class="faint">(blank keeps current)</span>' : ""}</label><textarea name="secret" autocomplete="off" spellcheck="false" rows="1" style="min-height:34px"></textarea>
      <div class="hint">Stored encrypted. For keys, paste the whole key including the BEGIN/END lines (no passphrase).</div></form>`,
      `<button class="btn" data-close>Cancel</button><button class="btn primary" id="save">${s ? "Save" : "Add server"}</button>`);
    const ta = $("[name=secret]", d), sel = $("[name=auth_type]", d);
    const sync = () => { const k = sel.value === "key"; ta.style.minHeight = k ? "150px" : "34px"; ta.style.webkitTextSecurity = k ? "none" : "disc"; ta.style.fontFamily = k ? "ui-monospace,Consolas,monospace" : "inherit"; };
    sel.onchange = sync; sync();
    const submit = () => busy($("#save", d), async () => {
      const f = $("#f", d); if (!f.reportValidity()) return;
      const x = Object.fromEntries(new FormData(f)); x.ssh_port = +x.ssh_port; if (!x.version) x.version = s.version;
      const r = await api(s ? "PUT" : "POST", s ? `/api/servers/${s.id}` : "/api/servers", x);
      d.close(); if (s) route(true); else location.hash = `#/servers/${r.id}`;
    });
    $("#save", d).onclick = submit; $("#f", d).onsubmit = e => { e.preventDefault(); submit(); };
  };
  if (S.versions) open(); else api("GET", "/api/versions").then(r => { S.versions = r; open(); });
}

async function bootstrapDialog(s) {
  const script = await (await fetch(`/api/servers/${s.id}/bootstrap.sh`)).text();
  const d = dialog("Bootstrap script", `<ol class="muted" style="margin:0 0 12px;padding-left:18px;line-height:1.7">
    <li>Save this script on the VPS as <span class="mono">bootstrap.sh</span> — paste it into <span class="mono">nano</span>, or <a href="/api/servers/${s.id}/bootstrap.sh" download style="text-decoration:underline">download it</a> and copy it with <span class="mono">scp</span>.</li>
    <li>Run <span class="mono">sudo bash bootstrap.sh</span> as <b>${esc(s.ssh_user)}</b>.</li><li>Come back here and press <b>Test SSH</b>.</li></ol>
    <textarea readonly class="mono" id="sc" rows="10" style="min-height:200px">${esc(script)}</textarea>`,
    `<button class="btn" id="cp">${icon("copy")}Copy script</button><button class="btn primary" data-close>Done</button>`, { wide: true, noFocus: true });
  $("#cp", d).onclick = () => copyText(script);
}
function installAppsDialog(s) {
  const avail = S.apps.filter(a => !s.apps.includes(a.name));
  const d = dialog(`Install apps on ${s.name}`, `<p class="muted" style="margin:0 0 10px">Apps are downloaded into the server's bench. Sites can then use them.</p>
    <div class="appgrid" style="grid-template-columns:1fr 1fr">${avail.map(a => `<label class="opt"><input type="checkbox" value="${esc(a.name)}"><div><b>${esc(a.title || a.name)}</b><small>${esc(a.name)}</small></div></label>`).join("") || '<span class="faint">Everything is already installed.</span>'}</div>`,
    `<button class="btn" data-close>Cancel</button><button class="btn primary" id="go" ${avail.length ? "" : "disabled"}>Install</button>`);
  $("#go", d).onclick = e => busy(e.currentTarget, async () => {
    const apps = $$("input:checked", d).map(i => i.value); if (!apps.length) return toast("Select at least one app", true);
    const r = await api("POST", `/api/servers/${s.id}/install-apps`, { apps }); d.close(); S.running = (S.running || 0) + 1; openJob(r.job_id, `Installing apps on ${s.name}`);
  });
}

// ───────────────────────────── apps / jobs / settings ─────────────────────────────
async function pApps() {
  await load("apps");
  return {
    crumbs: [["Apps"]], actions: `<button class="btn primary" data-act="newapp">${icon("plus")}New App</button>`,
    html: `<div class="page-head"><h1>Apps</h1></div><p class="sub">Frappe apps you can install on servers and sites. Add your own from any git repository.</p>
    <div class="card tbl"><table><thead><tr><th>App</th><th class="hide-sm">Repository</th><th class="hide-sm">Branch</th><th class="hide-sm">Requires</th><th>Servers</th><th></th></tr></thead><tbody>
    ${S.apps.map(a => `<tr><td><div class="cell-main">${esc(a.title || a.name)} ${a.builtin ? "" : '<span class="chip">Custom</span>'}</div><div class="cell-sub mono">${esc(a.name)}</div></td><td class="hide-sm mono faint">${esc(a.git_url.replace(/^https?:\/\//, ""))}</td>
      <td class="hide-sm mono">${a.branch ? esc(a.branch) : '<span class="faint">server version</span>'}</td><td class="hide-sm mono faint">${esc(a.requires || "—")}</td><td>${a.servers}</td>
      <td style="text-align:right;white-space:nowrap"><button class="btn sm" data-act="editapp" data-name="${esc(a.name)}">Edit</button>${a.builtin ? "" : ` <button class="btn sm danger" data-act="delapp" data-name="${esc(a.name)}">Remove</button>`}</td></tr>`).join("")}</tbody></table></div>
    <p class="hint">“Server version” means the app is fetched on the same branch as the server's ERPNext version (for example version-15).</p>`,
  };
}
function appForm(a) {
  const d = dialog(a ? `Edit ${a.name}` : "New app", `<form id="f">
    <label class="l">Git repository URL</label><input name="git_url" required placeholder="https://github.com/you/your_app" value="${esc(a && a.git_url)}">
    <div class="row2"><div><label class="l">App name <span class="faint">(python module)</span></label><input name="name" required pattern="[a-z][a-z0-9_]+" value="${esc(a && a.name)}" ${a ? "readonly" : ""}></div><div><label class="l">Title</label><input name="title" value="${esc(a && a.title)}"></div></div>
    <div class="row2"><div><label class="l">Branch <span class="faint">(blank = server version)</span></label><input name="branch" value="${esc(a && a.branch)}" placeholder="main"></div><div><label class="l">Requires <span class="faint">(comma separated)</span></label><input name="requires" value="${esc(a && a.requires)}" placeholder="erpnext"></div></div>
    <div class="hint">Private repository? Use an https URL with a deploy token, or add the server's SSH key as a deploy key.</div></form>`,
    `<button class="btn" data-close>Cancel</button><button class="btn primary" id="save">Save</button>`);
  $("[name=git_url]", d).onblur = e => { const n = $("[name=name]", d); if (!a && !n.value) n.value = (e.target.value.replace(/\.git$/, "").split("/").pop() || "").toLowerCase().replace(/[^a-z0-9_]/g, "_"); };
  const submit = () => busy($("#save", d), async () => {
    const f = $("#f", d); if (!f.reportValidity()) return;
    const x = Object.fromEntries(new FormData(f)); x.branch = x.branch || null;
    await api(a ? "PUT" : "POST", a ? `/api/apps/${a.name}` : "/api/apps", x); d.close(); route();
  });
  $("#save", d).onclick = submit; $("#f", d).onsubmit = e => { e.preventDefault(); submit(); };
}

async function pJobs() {
  await load("jobs");
  return {
    crumbs: [["Jobs"]],
    html: `<div class="page-head"><h1>Jobs</h1></div><p class="sub">Background tasks: server setup, site creation and app installs.</p><div class="card tbl">${S.jobs.length
      ? `<table><thead><tr><th>Task</th><th>Status</th><th class="hide-sm">Started</th><th></th></tr></thead><tbody>${S.jobs.map(j => `<tr><td><div class="cell-main">${esc(j.title)}</div><div class="cell-sub">#${j.id} · ${esc(j.kind)}</div></td><td>${badge(j.status)}</td><td class="hide-sm faint">${ago(j.created)}</td><td style="text-align:right"><button class="btn sm" data-act="job" data-id="${j.id}" data-t="${esc(j.title)}">View log</button></td></tr>`).join("")}</tbody></table>`
      : emptyState("activity", "No jobs yet", "Jobs appear here when you set up servers or create sites.")}</div>`,
  };
}

async function pSettings() {
  const [c, k] = await Promise.all([api("GET", "/api/settings/cpanel"), api("GET", "/api/manager-key")]);
  return {
    crumbs: [["Settings"]],
    html: `<div class="page-head"><h1>Settings</h1></div><p class="sub">Connect cPanel for DNS and see the SSH key Fleet Manager uses.</p>
    <div class="card pad" style="margin-bottom:16px"><h3>cPanel</h3><form id="f">
      <div class="row2"><div><label class="l">Host</label><input name="host" required value="${esc(c.host)}" placeholder="cpanel.example.com"></div><div><label class="l">Port</label><input name="port" type="number" value="${c.port || 2083}"></div></div>
      <div class="row2"><div><label class="l">Username</label><input name="user" required value="${esc(c.user)}"></div><div><label class="l">Sign in with</label><select name="auth"><option value="token" ${c.auth !== "password" ? "selected" : ""}>API token</option><option value="password" ${c.auth === "password" ? "selected" : ""}>cPanel password (no 2FA)</option></select></div></div>
      <label class="l">API token or password ${c.has_token ? '<span class="faint">(saved — blank keeps it)</span>' : ""}</label><input name="token" type="password" autocomplete="off">
      <label class="check"><input type="checkbox" name="verify_tls" ${c.verify_tls ? "checked" : ""}><div><b>Verify TLS certificate</b></div></label>
      <div style="display:flex;gap:8px;margin-top:6px"><button class="btn primary" id="save">Save</button><button type="button" class="btn" id="test" ${c.configured ? "" : "disabled"}>Test connection</button></div></form></div>
    <div class="card pad"><h3>Fleet Manager SSH key</h3><p class="muted" style="margin:0 0 10px">The bootstrap script authorizes this public key on each VPS.</p>
      <textarea readonly class="mono" rows="3" style="min-height:70px">${esc(k.public_key)}</textarea><div style="margin-top:8px"><button class="btn sm" data-act="copy" data-v="${esc(k.public_key)}">${icon("copy")}Copy</button></div></div>`,
    mount(root) {
      $("#f", root).onsubmit = e => {
        e.preventDefault(); busy($("#save", root), async () => {
          const x = Object.fromEntries(new FormData(e.target)); x.port = +x.port; x.verify_tls = !!x.verify_tls;
          await api("PUT", "/api/settings/cpanel", x); toast("Saved"); $("#test", root).disabled = false;
        });
      };
      $("#test", root).onclick = e => busy(e.currentTarget, async () => { const r = await api("POST", "/api/settings/cpanel/test"); toast("Connected · " + r.domains.join(", ")); });
    },
  };
}

const ROUTES = [
  [/^#\/sites$/, pSites, "sites"], [/^#\/sites\/(\d+)(?:\/(\w+))?$/, pSite, "site"], [/^#\/new-site$/, pNewSite, "newsite"],
  [/^#\/servers$/, pServers, "servers"], [/^#\/servers\/(\d+)(?:\/(\w+))?$/, pServer, "server"],
  [/^#\/apps$/, pApps, "apps"], [/^#\/jobs$/, pJobs, "jobs"], [/^#\/settings$/, pSettings, "settings"],
];

showAuth();
