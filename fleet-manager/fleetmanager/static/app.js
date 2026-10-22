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
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  clipboard: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M9 14l2 2 4-4"/>',
  trash: '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
  building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
  drive: '<path d="M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11zM6 16h.01M10 16h.01"/>',
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

const S = { user: null, role: "viewer", page: "", sites: [], servers: [], apps: [], jobs: [], customers: [], versions: null, running: undefined, pending: 0, timers: [], ui: { q: "", f: "all" } };
const RANK = { viewer: 1, support: 2, admin: 3 };
const can = r => (RANK[S.role] || 0) >= RANK[r];
const URLS = { sites: "/api/sites", servers: "/api/servers", apps: "/api/apps", jobs: "/api/jobs", customers: "/api/customers" };
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

function logHtml(raw) {
  return cleanLog(raw).split("\n").map(l => {
    const e = esc(l);
    if (/^(>>>|==)/.test(l)) return `<b>${e}</b>`;
    if (/^!!!|Traceback|FAILED|\bError\b/.test(l)) return `<span class="er">${e}</span>`;
    if (/^!!|\bWARN/i.test(l)) return `<span class="wn">${e}</span>`;
    return e;
  }).join("\n");
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
        logEl.innerHTML = logHtml(raw);
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
const NAV = [["sites", "Sites", "globe"], ["servers", "Servers", "server"], ["customers", "Customers", "building"], ["apps", "Apps", "box"], ["jobs", "Jobs", "activity"], ["-"],
  ["monitoring", "Monitoring", "activity"], ["backups", "Backups", "drive", "support"],
  ["approvals", "Approvals", "clipboard", "support"], ["audit", "Audit log", "shield", "admin"], ["settings", "Settings", "settings"]];
function buildShell() {
  $("#root").innerHTML = `<div class="app">
    <aside class="side"><div class="brand"><div class="mark">${icon("zap")}</div><span>Fleet Manager</span></div>
      <nav class="nav">${NAV.filter(n => !n[3] || can(n[3])).map(([k, l, i]) => k === "-" ? '<div class="sep"></div>' : `<a href="#/${k}" data-nav="${k}">${icon(i)}<span>${l}</span><em class="count" id="cnt-${k}" hidden></em></a>`).join("")}</nav>
      <div class="grow"></div>
      <div class="me"><div class="av">${esc((S.user || "?")[0])}</div><div class="nm">${esc(S.user)}<div class="field-note" style="line-height:1.1;text-transform:capitalize">${esc(S.role)}</div></div><button data-act="logout" title="Log out" aria-label="Log out">${icon("logout")}</button></div>
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
  const mo = $("#cnt-monitoring"); if (mo) { mo.hidden = !S.incidentN; mo.textContent = S.incidentN; mo.classList.add("warn"); }
  const ap = $("#cnt-approvals"); if (ap) { ap.hidden = !S.pending; ap.textContent = S.pending; ap.classList.add("warn"); }
}
const AUTO = new Set(["monitoring", "sites", "site", "servers", "server", "jobs", "approvals"]);
const NAVKEY = { site: "sites", newsite: "sites", server: "servers" };
let seq = 0;
async function route(silent = false) {
  if (!S.user || !$("#view")) return;
  if (silent && !AUTO.has(S.page)) return;
  S.timers.forEach(clearInterval); S.timers = [];
  const hash = location.hash || "#/sites", my = ++seq;
  let hit = null;
  for (const [re, fn, key] of ROUTES) { const m = hash.match(re); if (m) { hit = [fn, m.slice(1), key]; break; } }
  if (!hit) { location.hash = "#/sites"; return; }
  S.page = hit[2];
  $$("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === (NAVKEY[hit[2]] || hit[2])));
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
    S.jobs = jobs; S.running = run;
    S.incidentN = (await api("GET", "/api/monitor/summary")).open;
    if (can("admin")) S.pending = (await api("GET", "/api/approvals?status=pending")).length;
    paintPill(); paintCounts();
    if (prev !== undefined && prev !== run) route(true);
  } catch { /* offline: ignore */ }
}

// ───────────────────────────── actions (event delegation) ─────────────────────────────
const ACT = {
  newsite: () => { location.hash = "#/new-site"; },
  jobs: () => { location.hash = "#/jobs"; },
  logout: async () => { await api("POST", "/api/auth/logout"); S.user = null; S.role = "viewer"; showAuth(); },
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
  // ── site operations
  openadmin: el => busy(el, () => openAsAdmin(siteById(el.dataset.id))),
  golivecheck: el => busy(el, async () => { const s = siteById(el.dataset.id); await loadGolive($("#view"), s); }),
  golivemark: el => busy(null, async () => { await api("POST", `/api/sites/${el.dataset.id}/golive`, { provider_done: el.checked }); toast(el.checked ? "Marked as done" : "Reopened"); route(true); }),
  opmaint: el => busy(el, async () => { const on = el.dataset.on === "1"; await api("POST", `/api/sites/${el.dataset.id}/maintenance`, { on }); toast(`Maintenance mode ${on ? "on" : "off"}`); }),
  opcache: el => busy(el, async () => { await api("POST", `/api/sites/${el.dataset.id}/clear-cache`); toast("Cache cleared"); }),
  opbackup: el => busy(el, async () => { const s = siteById(el.dataset.id); const r = await api("POST", `/api/sites/${s.id}/backup`); startJob(r.job_id, `Backup ${s.domain}`); }),
  opmigrate: el => busy(null, async () => {
    const s = siteById(el.dataset.id);
    if (!await confirmBox("Run migrate", `Applies pending updates to <b>${esc(s.domain)}</b>'s database. Take a backup first if unsure.`, "Migrate")) return;
    const r = await api("POST", `/api/sites/${s.id}/migrate`); startJob(r.job_id, `Migrate ${s.domain}`);
  }),
  oprestart: el => busy(null, async () => {
    const srv = S.servers.find(x => x.id === +el.dataset.server);
    if (!await confirmBox("Restart services", `Restarts the web server, workers and nginx on <b>${esc(srv.name)}</b>. <b>Every site on this server</b> is unavailable for a few seconds.`, "Restart")) return;
    await api("POST", `/api/servers/${srv.id}/restart-services`); toast("Services restarted");
  }),
  opreset: el => busy(null, async () => {
    const s = siteById(el.dataset.id);
    if (!await confirmBox("Reset Administrator password", `Generates a new password for <b>${esc(s.domain)}</b>. The old one stops working immediately.`, "Reset password")) return;
    const r = await api("POST", `/api/sites/${s.id}/reset-password`);
    dialog("New Administrator password", `<p class="muted" style="margin:0">Shown once here; it is also saved under <b>Password</b> on the site page.</p><div class="pwbox">${esc(r.password)}</div>`,
      `<button class="btn" id="cp">${icon("copy")}Copy</button><button class="btn primary" data-close>Done</button>`, { noFocus: true }).querySelector("#cp").onclick = () => copyText(r.password);
  }),
  opadddomain: el => {
    const s = siteById(el.dataset.id);
    const d = dialog("Add a domain", `<p class="muted" style="margin:0 0 10px">Serve <b>${esc(s.domain)}</b> on another domain as well. Point its DNS to the server afterwards${s.gateway ? " and add it in the provider panel" : ""}.</p><label class="l">Domain</label><input id="nd" placeholder="erp.customer.com" autocomplete="off">`,
      `<button class="btn" data-close>Cancel</button><button class="btn primary" id="go">Add domain</button>`);
    $("#go", d).onclick = e => busy(e.currentTarget, async () => { await api("POST", `/api/sites/${s.id}/add-domain`, { domain: $("#nd", d).value.trim() }); d.close(); toast("Domain added"); route(true); });
  },
  opsuspend: el => {
    const s = siteById(el.dataset.id);
    if (s.suspended) {
      return busy(null, async () => { if (!await confirmBox("Reactivate site", `Turn maintenance mode off for <b>${esc(s.domain)}</b>?`, "Reactivate")) return; await api("POST", `/api/sites/${s.id}/suspend`, { suspended: false }); toast("Site reactivated"); route(true); });
    }
    const d = dialog("Suspend site", `<p class="muted" style="margin:0 0 10px">Visitors of <b>${esc(s.domain)}</b> will see the maintenance page. Data is kept.</p><label class="l">Reason</label><input id="why" placeholder="e.g. unpaid invoice" autocomplete="off">`,
      `<button class="btn" data-close>Cancel</button><button class="btn danger" id="go">Suspend</button>`);
    $("#go", d).onclick = e => busy(e.currentTarget, async () => { await api("POST", `/api/sites/${s.id}/suspend`, { suspended: true, reason: $("#why", d).value }); d.close(); toast("Site suspended"); route(true); });
  },
  oprename: el => {
    const s = siteById(el.dataset.id);
    const d = dialog("Rename site", `<div class="note warn" style="margin-top:0">A backup is taken first. Afterwards update DNS${s.gateway ? " and the provider panel" : ""} for the new name.</div><label class="l">New domain</label><input id="nd" placeholder="new.example.com" autocomplete="off">`,
      `<button class="btn" data-close>Cancel</button><button class="btn primary" id="go">Rename</button>`);
    $("#go", d).onclick = e => busy(e.currentTarget, async () => { const r = await api("POST", `/api/sites/${s.id}/rename`, { domain: $("#nd", d).value.trim() }); d.close(); startJob(r.job_id, `Rename ${s.domain}`); });
  },
  opdelete: el => deleteDialog(siteById(el.dataset.id)),
  delnote: el => busy(null, async () => { await api("DELETE", `/api/sites/${el.dataset.id}/notes/${el.dataset.n}`); route(true); }),
  // ── backups & monitoring
  incack: el => busy(el, async () => { await api("POST", `/api/incidents/${el.dataset.id}/ack`); toast("Acknowledged"); route(true); }),
  incclose: el => busy(null, async () => { if (!await confirmBox("Close incident", "Mark this problem as handled? It reopens if it happens again.", "Close")) return; await api("POST", `/api/incidents/${el.dataset.id}/close`); route(true); }),
  monrun: el => busy(el, async () => { await api("POST", "/api/monitor/run"); toast("Checks done"); route(true); }),
  bkpolicy: el => busy(null, () => policyDialog(el.dataset.id ? +el.dataset.id : null)),
  restore: el => restoreDialog(siteById(el.dataset.id), JSON.parse(el.dataset.g)),
  opmove: el => moveDialog(siteById(el.dataset.id)),
  opuploaddb: el => uploadDbDialog(siteById(el.dataset.id)),
  emptyapp: el => busy(null, async () => {
    const s = siteById(el.dataset.id), name = emptyAppName(s.domain);
    if (!await confirmBox("Create & install empty app", `Creates a new empty app named <b class="mono">${esc(name)}</b> on <b>${esc(s.server_name)}</b> and installs it on <b>${esc(s.domain)}</b>. A backup of the site is taken first.`, "Create & install")) return;
    const r = await api("POST", `/api/sites/${s.id}/empty-app`); startJob(r.job_id, `Create empty app ${r.app}`);
  }),
  // ── customers, team, approvals
  newcustomer: () => customerForm(),
  editcustomer: el => customerForm(S.customers.find(c => c.id === +el.dataset.id)),
  delcustomer: el => busy(null, async () => {
    const c = S.customers.find(x => x.id === +el.dataset.id);
    if (!await confirmBox("Delete customer", `Delete <b>${esc(c.name)}</b>? Their sites stay, but lose the customer link.`, "Delete", true)) return;
    await api("DELETE", `/api/customers/${c.id}`); route(true);
  }),
  adduser: () => userForm(),
  resetpw: el => userForm(el.dataset.u),
  toggleuser: el => busy(el, async () => { await api("PUT", `/api/team/${encodeURIComponent(el.dataset.u)}`, { disabled: el.dataset.off === "1" }); route(true); }),
  deluser: el => busy(null, async () => {
    if (!await confirmBox("Delete user", `Delete <b>${esc(el.dataset.u)}</b>? Their past actions stay in the audit log.`, "Delete", true)) return;
    await api("DELETE", `/api/team/${encodeURIComponent(el.dataset.u)}`); route(true);
  }),
  approve: el => busy(null, async () => {
    const rs = el.dataset.a === "restore_site";
    if (!await confirmBox(rs ? "Approve restore" : "Approve deletion", rs ? `Replace the data of <b>${esc(el.dataset.d)}</b> with the requested backup? A safety backup of the current state is taken first.` : `Delete <b>${esc(el.dataset.d)}</b> as requested? A backup is taken first if the requester asked for it.`, rs ? "Approve and restore" : "Approve and delete", true)) return;
    const r = await api("POST", `/api/approvals/${el.dataset.id}/decide`, { approve: true }); startJob(r.job_id, `${rs ? "Restore" : "Delete site"} ${el.dataset.d}`); route(true);
  }),
  reject: el => busy(el, async () => { await api("POST", `/api/approvals/${el.dataset.id}/decide`, { approve: false }); toast("Request rejected"); S.pending = Math.max(0, S.pending - 1); route(true); }),
};
document.addEventListener("click", e => {
  const a = e.target.closest("[data-act]");
  if (a) { if (a.tagName !== "INPUT") e.preventDefault(); const f = ACT[a.dataset.act]; if (f) f(a, e); return; }
  const tr = e.target.closest("tr[data-href]");
  if (tr && !e.target.closest("a,button")) location.hash = tr.dataset.href;
});

// ───────────────────────────── auth ─────────────────────────────
async function showAuth() {
  closeDrawer(); $$(".overlay").forEach(o => o.remove());
  const st = await api("GET", "/api/auth/state");
  if (st.user) { S.user = st.user; S.role = st.role || "viewer"; return startApp(); }
  $("#root").innerHTML = `<div class="auth"><div class="box"><div class="brand"><div class="mark">${icon("zap")}</div><span>Fleet Manager</span></div>
    <div class="card"><h1>${st.setup_needed ? "Create your account" : "Sign in"}</h1><p>${st.setup_needed ? "First run — choose the administrator login." : "Manage your ERPNext servers and sites."}</p>
    <form id="f"><label class="l">Username</label><input name="username" autocomplete="username" required minlength="3" autofocus>
    <label class="l">Password${st.setup_needed ? ' <span class="faint">(min. 8 characters)</span>' : ""}</label><input name="password" type="password" autocomplete="${st.setup_needed ? "new-password" : "current-password"}" required minlength="8">
    <div style="margin-top:18px"><button class="btn primary block">${st.setup_needed ? "Create account" : "Sign in"}</button></div></form></div></div></div>`;
  $("#f").onsubmit = e => {
    e.preventDefault(); const btn = $("button", e.target);
    busy(btn, async () => { const r = await api("POST", st.setup_needed ? "/api/auth/setup" : "/api/auth/login", Object.fromEntries(new FormData(e.target))); S.user = r.user; S.role = r.role || "viewer"; startApp(); });
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
  const flags = (s.suspended ? ' <span class="chip warn">Suspended</span>' : "") + (s.status === "up" && s.public_ok === 0 ? ' <span class="chip warn" title="Not reachable from the internet yet">Not public</span>' : "");
  return `<tr data-href="#/sites/${s.id}" tabindex="0"><td><div class="cell-main">${esc(s.domain)}</div><div class="cell-sub">${esc([...new Set([s.company, s.customer_name].filter(Boolean))].join(" · ") || "No company name yet")}</div></td>
    <td>${badge(s.status)}${flags}</td><td class="hide-sm"><div>${esc(s.server_name)}</div><div class="cell-sub mono">${esc(s.ip)}</div></td>
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
    actions: can("support") ? `<button class="btn primary" data-act="newsite" ${ready ? "" : 'disabled title="Set up a server first"'}>${icon("plus")}New Site</button>` : "",
    html: `<div class="page-head"><h1>Sites</h1></div><p class="sub">All ERPNext sites across your servers.</p>
      <div class="toolbar"><div class="search">${icon("search")}<input id="q" placeholder="Search sites" value="${esc(S.ui.q)}" autocomplete="off" aria-label="Search sites"></div><div class="seg" id="seg"></div>
      <span class="grow" style="flex:1"></span>${can("support") ? `<button class="btn" data-act="health">${icon("refresh")}Check health</button>` : ""}</div>
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
            ready && can("support") ? `<button class="btn primary" data-act="newsite">${icon("plus")}New Site</button>` : can("admin") ? `<a class="btn primary" href="#/servers">Go to Servers</a>` : "")
          : !rows.length ? emptyState("search", "No matching sites", "Try a different search or filter.")
            : `<table><thead><tr><th>Site</th><th>Status</th><th class="hide-sm">Server</th><th class="hide-sm">Apps</th><th class="hide-sm">Created</th></tr></thead><tbody>${rows.map(siteRow).join("")}</tbody></table>`;
      };
      draw();
      $("#q").oninput = e => { S.ui.q = e.target.value; draw(); };
      $("#seg").onclick = e => { const b = e.target.closest("[data-f]"); if (b) { S.ui.f = b.dataset.f; draw(); } };
    },
  };
}

const fmtBytes = n => n > 1e9 ? (n / 1e9).toFixed(2) + " GB" : n > 1e6 ? (n / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1e3)) + " KB";
const startJob = (id, title) => { S.running = (S.running || 0) + 1; openJob(id, title); };
const siteById = id => S.sites.find(x => x.id === +id);
const actRow = (t, sub, btn) => `<div class="act-row"><div class="t"><b>${t}</b><span>${sub}</span></div>${btn}</div>`;

async function pSite(id, tab = "overview") {
  await load("sites", "servers", "jobs", "customers", "apps");
  const s = siteById(id); if (!s) throw new Error("Site not found");
  const srv = S.servers.find(x => x.id === s.server_id) || {};
  const apps = (s.apps || "").split(",").filter(Boolean);
  const running = S.jobs.find(j => j.status === "running" && j.title.includes(s.domain));
  const tabs = [["overview", "Overview"], ...(can("support") ? [["ops", "Operations"], ["backups", "Backups"], ["logs", "Logs"]] : []),
    ["notes", "Notes"], ["apps", `Apps (${apps.filter(n => n !== "frappe").length + 1})`], ["activity", "Activity"]];
  if (!tabs.some(t => t[0] === tab)) tab = "overview";
  const ctx = { s, srv, apps, running };
  const v = ({ overview: siteOverview, ops: siteOps, backups: siteBackups, logs: siteLogs, notes: siteNotes, apps: siteApps, activity: siteActivity })[tab](ctx);
  return {
    crumbs: [["Sites", "#/sites"], [s.domain]],
    actions: `${can("support") ? `<button class="btn" data-act="openadmin" data-id="${s.id}">${icon("key")}Open as Administrator</button>` : ""}<a class="btn" href="${esc(siteUrl(s))}" target="_blank" rel="noopener">${icon("external")}Visit site</a>`,
    html: `<div class="page-head"><h1>${esc(s.domain)}</h1>${badge(s.status)}${s.suspended ? '<span class="chip warn">Suspended</span>' : ""}</div>
      <p class="sub">${esc([...new Set([s.company, s.customer_name].filter(Boolean))].join(" · ") || "No company name yet")} · ${esc(s.server_name)}</p>
      <nav class="tabs">${tabs.map(([k, l]) => `<a href="#/sites/${s.id}/${k}" class="${tab === k ? "on" : ""}">${l}</a>`).join("")}</nav>${v.html}`,
    mount: v.mount,
  };
}

function siteOverview({ s, srv, running }) {
  const chk = s.checked_at ? `HTTP ${s.http_code ?? "—"} · checked ${ago(s.checked_at)}` : "Not checked yet";
  const custSel = can("support")
    ? `<select class="inl" id="custsel"><option value="">— none —</option>${S.customers.map(c => `<option value="${c.id}" ${c.id === s.customer_id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select>`
    : esc(s.customer_name || "—");
  return {
    html: `${running ? `<div class="note warn" style="display:flex;align-items:center;gap:12px"><span style="flex:1">This site is being set up…</span><button class="btn sm" data-act="runjob" data-q="${esc(s.domain)}">View progress</button></div>` : ""}
      ${s.suspended ? `<div class="note warn"><b>Suspended.</b> Visitors see the maintenance page. Reactivate it from the Operations tab.</div>` : ""}
      ${s.status === "error" && !running ? `<div class="note bad">This site is marked broken. See the Activity and Logs tabs, or press <b>Check health</b>.</div>` : ""}
      <div id="golive"></div><div id="uptime"></div>
      <div class="cards"><div class="card pad"><h3>Site information</h3><div class="kv">
        <div>Domain</div><div><span class="copy" data-act="copy" data-v="${esc(s.domain)}"><span class="mono">${esc(s.domain)}</span>${icon("copy")}</span></div>
        <div>Company</div><div>${esc(s.company || "—")}</div>
        <div>Customer</div><div>${custSel}</div>
        <div>Health</div><div>${badge(s.status)} <span class="faint" style="margin-left:6px">${esc(chk)}</span></div>
        <div>Server</div><div><a href="#/servers/${s.server_id}" style="text-decoration:underline">${esc(s.server_name)}</a> <span class="mono faint">${esc(s.ip)}</span></div>
        ${s.aliases ? `<div>Extra domains</div><div class="mono">${esc(s.aliases.split(",").join(", "))}</div>` : ""}
        <div>HTTPS</div><div>${s.ssl ? "Enabled on server" : s.gateway ? "Handled by provider gateway" : "Not enabled on server"}</div>
        <div>Created</div><div>${ago(s.created)}</div></div></div>
      <div class="card pad"><h3>Quick actions</h3>
        ${actRow("Open site", esc(siteUrl(s)), `<a class="btn sm" href="${esc(siteUrl(s))}" target="_blank" rel="noopener">${icon("external")}Visit</a>`)}
        ${can("support") ? actRow("Administrator login", "Open signed in, or view the password", `<div class="btnrow"><button class="btn sm" data-act="openadmin" data-id="${s.id}">Open</button><button class="btn sm" data-act="creds" data-id="${s.id}">${icon("key")}Password</button></div>`) : ""}
        ${can("support") ? actRow("Check health", "Request the site from this machine", `<button class="btn sm" data-act="health">${icon("refresh")}Check</button>`) : ""}</div></div>`,
    mount(root) {
      loadGolive(root, s); loadUptime(root, s);
      const sel = $("#custsel", root);
      if (sel) sel.onchange = () => busy(null, async () => { await api("PUT", `/api/sites/${s.id}/customer`, { customer_id: sel.value ? +sel.value : null }); toast("Customer updated"); route(true); });
    },
  };
}

async function loadGolive(root, s) {
  const box = $("#golive", root); if (!box || s.status === "creating") return;
  box.innerHTML = `<div class="card pad golive" style="margin-bottom:16px"><h3>Go-live checklist</h3><div class="faint">Checking DNS and public access…</div></div>`;
  let g; try { g = await api("GET", `/api/sites/${s.id}/golive`); } catch { box.innerHTML = ""; return; }
  if (!box.isConnected) return;
  const st = ok => `<div class="st ${ok === true ? "ok" : ok === false ? "no" : ""}">${icon(ok === true ? "check" : ok === false ? "alert" : "globe")}</div>`;
  const cp = (l, v) => `<div class="copyrow"><span class="faint">${l}</span><code>${esc(v)}</code><button class="btn sm ghost" data-act="copy" data-v="${esc(v)}" aria-label="Copy ${l}">${icon("copy")}</button></div>`;
  const rows = [
    `<div class="row">${st(g.dns.ok)}<div class="b"><b>DNS points to the server</b><p>${g.dns.ok ? `${esc(s.domain)} resolves to ${esc(g.dns.expected)}.` : `Add an A record <span class="mono">${esc(s.domain)} → ${esc(g.dns.expected)}</span>${g.dns.ips.length ? `. Right now it resolves to ${esc(g.dns.ips.join(", "))}.` : ". Right now it doesn't resolve at all."}`}</p></div></div>`,
    g.gateway ? `<div class="row">${st(g.provider_done)}<div class="b"><b>Add the domain in your provider's panel</b>
      <p>This server sits behind your provider's gateway, so it must be told to send this domain to your VPS:</p>${cp("Domain", s.domain)}${cp("Inner IP", g.inner_ip || "(shown in the provider panel)")}${cp("Port", "80")}
      <div class="btnrow" style="margin-top:6px">${g.gateway_url ? `<a class="btn sm" href="${esc(g.gateway_url)}" target="_blank" rel="noopener">${icon("external")}Open provider panel</a>` : ""}</div>
      <label class="check" style="padding:8px 0 0"><input type="checkbox" data-act="golivemark" data-id="${s.id}" ${g.provider_done ? "checked" : ""} ${can("support") ? "" : "disabled"}><div><b>I added it in the provider panel</b></div></label></div></div>` : "",
    `<div class="row">${st(g.public.ok)}<div class="b"><b>Reachable from the internet</b><p>${g.public.ok ? "ERPNext answers on its public address." : `Not yet — ${esc(g.public.detail || "no answer")}.`}</p>
      <button class="btn sm" data-act="golivecheck" data-id="${s.id}">${icon("refresh")}Check again</button></div></div>`,
    `<div class="row">${st(null)}<div class="b"><b>HTTPS</b><p>${g.gateway ? "Turn on the certificate for this domain in the provider panel." : s.ssl ? "A certificate is installed on the server." : "Not enabled yet. Request a free certificate once DNS works."}</p></div></div>`,
  ].join("");
  box.innerHTML = `<div class="card pad golive" style="margin-bottom:16px"><h3 style="display:flex;align-items:center;gap:10px">Go-live checklist ${g.live ? '<span class="badge green"><i></i>Live</span>' : '<span class="badge amber"><i></i>Not public yet</span>'}</h3>${rows}</div>`;
}

function siteOps({ s }) {
  const id = s.id, b = (act, label, cls = "", extra = "") => `<button class="btn sm ${cls}" data-act="${act}" data-id="${id}" ${extra}>${label}</button>`;
  return {
    html: `<div class="cards"><div class="card pad"><h3>Maintenance</h3>
        ${actRow("Maintenance mode", "Shows a maintenance page to visitors", `<div class="btnrow">${b("opmaint", "Turn on", "", 'data-on="1"')}${b("opmaint", "Turn off", "", 'data-on="0"')}</div>`)}
        ${actRow("Clear cache", "Fixes stale pages and settings", b("opcache", "Clear"))}
        ${actRow("Run migrate", "Applies app updates to this site's database", b("opmigrate", "Migrate"))}
        ${actRow("Restart server services", `Restarts web, workers and nginx for <b>all sites</b> on ${esc(s.server_name)}`, `<button class="btn sm" data-act="oprestart" data-server="${s.server_id}">Restart</button>`)}</div>
      <div class="card pad"><h3>Access &amp; data</h3>
        ${actRow("Back up now", "Database and files; download from Backups", b("opbackup", "Back up"))}
        ${can("admin") ? actRow("Upload database", "Replace this site's data with a .sql or .sql.gz file", b("opuploaddb", "Upload…")) : ""}
        ${actRow("Reset Administrator password", "Generates a new password", b("opreset", "Reset…"))}
        ${actRow("Add a domain", "Serve this site on another domain too", b("opadddomain", "Add…"))}
        ${actRow(s.suspended ? "Reactivate site" : "Suspend site", s.suspended ? "Turns maintenance mode off" : "For unpaid or ended accounts: maintenance page on, with a note", b("opsuspend", s.suspended ? "Reactivate" : "Suspend…"))}</div></div>
      <div class="card pad dangerzone"><h3>Danger zone</h3>
        ${can("admin") ? actRow("Move to another server", "Copies the site to a different server of the same ERPNext version", b("opmove", "Move…")) : ""}
        ${can("admin") ? actRow("Rename site", "Changes the site's domain. A backup is taken first.", b("oprename", "Rename…")) : ""}
        ${actRow("Delete site", can("admin") ? "Removes the site and database from the server" : "Needs an administrator's approval", b("opdelete", can("admin") ? "Delete…" : "Request deletion…", "danger"))}
        ${can("admin") ? actRow("Remove from Fleet Manager", "Only forgets the record here. The site stays on the server.", b("forget", "Remove", "danger")) : ""}</div>`,
  };
}

function siteBackups({ s }) {
  return {
    html: `<div class="toolbar"><div style="flex:1" class="muted" id="bkinfo">Backups of this site.</div>${can("admin") ? `<button class="btn" data-act="bkpolicy" data-id="${s.id}">Schedule…</button>` : ""}<button class="btn primary" data-act="opbackup" data-id="${s.id}">${icon("plus")}Back up now</button></div><div class="card tbl" id="bk"><div class="empty faint">Loading…</div></div>
      <div class="card tbl" id="bkruns" style="margin-top:16px"></div>`,
    async mount(root) {
      const box = $("#bk", root);
      const [items, off, runs, pol] = await Promise.all([
        api("GET", `/api/sites/${s.id}/backups`).catch(() => []),
        api("GET", `/api/sites/${s.id}/offsite`).catch(() => null),
        api("GET", `/api/sites/${s.id}/backup-runs`).catch(() => []),
        api("GET", `/api/sites/${s.id}/backup-policy`).catch(() => null)]);
      if (!box.isConnected) return;
      if (pol) $("#bkinfo", root).textContent = `Schedule: ${policyText(pol)}${pol.enabled ? ` · keep ${pol.keep} on server${pol.offsite ? `, ${pol.keep_offsite} offsite` : ""}` : ""} (${pol.source === "site" ? "custom" : "default"})`;
      const key = n => n.slice(0, 15), groups = {};
      items.forEach(i => { const g = groups[key(i.name)] = groups[key(i.name)] || { id: key(i.name), files: [], server: true, offsite: false }; g.files.push(i); });
      (off || []).forEach(i => { const g = groups[key(i.name)] = groups[key(i.name)] || { id: key(i.name), files: [], server: false, offsite: false }; g.offsite = true; });
      const label = k => { const m = k.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/); return m ? new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`).toLocaleString() : k; };
      const list = Object.values(groups).sort((x, y) => y.id.localeCompare(x.id));
      if (!list.length) box.innerHTML = emptyState("drive", "No backups yet", "Press Back up now to create the first one.");
      else box.innerHTML = `<table><thead><tr><th>Backup</th><th>Where</th><th class="hide-sm">Files</th><th></th></tr></thead><tbody>${list.map(g => { g.label = label(g.id); return `<tr><td><div class="cell-main">${esc(g.label)}</div></td>
        <td>${g.server ? '<span class="chip">Server</span> ' : ""}${g.offsite ? '<span class="chip info">Offsite</span>' : ""}</td>
        <td class="hide-sm">${g.files.map(f => `<div class="copyrow"><a class="btn sm" href="/api/sites/${s.id}/backups/${encodeURIComponent(f.name)}" download>${icon("download")}${esc(f.name.replace(/^\d{8}_\d{6}-/, ""))}</a><span class="faint">${fmtBytes(f.size)}</span></div>`).join("") || '<span class="faint">only offsite</span>'}</td>
        <td style="text-align:right;white-space:nowrap">${can("support") ? `<button class="btn sm" data-act="restore" data-id="${s.id}" data-g="${esc(JSON.stringify({ id: g.id, label: g.label, server: g.server, offsite: g.offsite }))}">${can("admin") ? "Restore…" : "Request restore…"}</button>` : ""}</td></tr>`; }).join("")}</tbody></table>`;
      if (off === null) box.insertAdjacentHTML("afterend", `<p class="hint">Offsite copies could not be listed (not configured or unreachable).</p>`);
      $("#bkruns", root).innerHTML = runs.length ? `<table><thead><tr><th>Recent runs</th><th>Result</th><th class="hide-sm">Size</th><th>When</th></tr></thead><tbody>${runs.slice(0, 10).map(r => `<tr><td class="faint">${esc(r.trigger)}</td><td>${runChip(r)} ${offChip(r)}${r.status === "failed" ? `<div class="cell-sub">${esc(r.message)}</div>` : ""}</td><td class="hide-sm faint">${r.size_bytes ? fmtBytes(r.size_bytes) : "—"}</td><td class="faint">${ago(r.started)}</td></tr>`).join("")}</tbody></table>` : "";
    },
  };
}

function siteLogs({ s }) {
  return {
    html: `<div class="logbar"><select id="lsrc" aria-label="Log"></select><select id="llines" aria-label="Lines"><option>100</option><option selected>300</option><option>1000</option></select>
      <div class="search">${icon("search")}<input id="lq" placeholder="Filter lines" autocomplete="off"></div>
      <button class="btn" id="lref">${icon("refresh")}Refresh</button><label><input type="checkbox" id="lauto"> Auto-refresh</label></div>
      <pre class="log inline" id="ltxt">Loading…</pre>`,
    async mount(root) {
      const src = $("#lsrc", root), txt = $("#ltxt", root); let tm = null, busyNow = false;
      (await api("GET", "/api/log-sources")).forEach(o => src.insertAdjacentHTML("beforeend", `<option value="${o.id}">${esc(o.label)}</option>`));
      const fetchLog = async () => {
        if (busyNow || !txt.isConnected) return; busyNow = true;
        try {
          const r = await api("GET", `/api/sites/${s.id}/logs?source=${src.value}&lines=${$("#llines", root).value}&q=${encodeURIComponent($("#lq", root).value)}`);
          const follow = txt.scrollTop + txt.clientHeight >= txt.scrollHeight - 40;
          txt.innerHTML = logHtml(r.text || "(empty)"); if (follow || !txt.dataset.once) txt.scrollTop = txt.scrollHeight; txt.dataset.once = "1";
        } catch (e) { txt.textContent = e.message; } finally { busyNow = false; }
      };
      fetchLog();
      src.onchange = () => { txt.dataset.once = ""; fetchLog(); }; $("#llines", root).onchange = fetchLog; $("#lref", root).onclick = fetchLog;
      let dt; $("#lq", root).oninput = () => { clearTimeout(dt); dt = setTimeout(fetchLog, 350); };
      $("#lauto", root).onchange = e => { clearInterval(tm); if (e.target.checked) { tm = setInterval(fetchLog, 4000); S.timers.push(tm); } };
    },
  };
}

function siteNotes({ s }) {
  const draw = (root, notes) => {
    $("#nl", root).innerHTML = notes.length ? notes.map(n => `<li><div class="av">${esc((n.user || "?")[0])}</div><div><div class="tx">${esc(n.text)}</div><div class="mt">${esc(n.user)} · ${ago(n.ts)}${can("admin") ? ` · <a href="#" data-act="delnote" data-id="${s.id}" data-n="${n.id}" style="text-decoration:underline">delete</a>` : ""}</div></div></li>`).join("") : `<li class="faint">No notes yet.</li>`;
  };
  return {
    html: `<div class="card pad">${can("support") ? `<textarea id="nt" placeholder="Add a note for your team — customer calls, changes made, things to remember…" rows="3"></textarea><div style="margin-top:8px"><button class="btn primary" id="nadd">Add note</button></div>` : ""}<ul class="timeline" id="nl"></ul></div>`,
    async mount(root) {
      draw(root, await api("GET", `/api/sites/${s.id}/notes`));
      const add = $("#nadd", root);
      if (add) add.onclick = () => busy(add, async () => { const t = $("#nt", root).value.trim(); if (!t) return; draw(root, await api("POST", `/api/sites/${s.id}/notes`, { text: t })); $("#nt", root).value = ""; });
    },
  };
}

function siteApps({ s, srv, apps }) {
  const reg = Object.fromEntries(S.apps.map(a => [a.name, a]));
  const names = apps.filter(n => n !== "frappe");
  const staticRows = `<tr><td><div class="cell-main">Frappe Framework</div><div class="cell-sub mono">frappe</div></td><td class="mono">${esc(ver(srv.version))}</td><td></td></tr>
      ${names.map(n => { const a = reg[n]; return `<tr><td><div class="cell-main">${esc(a ? a.title : n)}</div><div class="cell-sub mono">${esc(n)}</div></td><td class="mono">${esc(a ? (a.branch || ver(srv.version)) : "—")}</td><td></td></tr>`; }).join("")}`;
  if (!can("support")) return { html: `<div class="card tbl"><table><thead><tr><th>App</th><th>Branch</th><th></th></tr></thead><tbody>${staticRows}</tbody></table></div>` };
  return {
    html: `<div class="toolbar"><div style="flex:1" class="muted" id="appinfo">Apps installed on this site.</div><button class="btn" id="appupd" disabled>${icon("refresh")}Update selected</button><button class="btn" id="appempty" data-act="emptyapp" data-id="${s.id}">Create &amp; install empty app</button><button class="btn primary" id="appadd">${icon("plus")}Install app</button></div>
      <div class="card tbl" id="appbox"><table><thead><tr><th style="width:36px"></th><th>App</th><th>Version</th><th>Status</th></tr></thead><tbody>${staticRows.replace(/<td><div/g, "<td></td><td><div").replace(/<td class="mono">/g, '<td class="mono">')}</tbody></table></div>
      <p class="hint">Updating pulls the newest code of an app for <b>every site on ${esc(s.server_name)}</b> (they share it) and then migrates this site. A backup of this site is taken first. Other sites pick up the update at their next migrate.</p>`,
    async mount(root) {
      let info;
      try { info = await api("GET", `/api/sites/${s.id}/apps`); } catch (e) { $("#appinfo", root).textContent = e.message; return; }
      if (!$("#appbox", root)) return;
      const rows = info.installed.filter(a => a.name !== "frappe").concat(info.installed.filter(a => a.name === "frappe"));
      $("#appbox", root).innerHTML = `<table><thead><tr><th style="width:36px"></th><th>App</th><th>Version</th><th>Status</th></tr></thead><tbody>${rows.map(a => `<tr><td><input type="checkbox" class="appck" value="${esc(a.name)}" aria-label="Select ${esc(a.title)}" ${a.behind ? "checked" : ""}></td>
        <td><div class="cell-main">${esc(a.title)}</div><div class="cell-sub mono">${esc(a.name)}</div></td><td class="mono">${esc(a.version || "—")}<div class="cell-sub">${esc(a.branch || "")} ${esc(a.commit || "")}</div></td>
        <td>${a.behind ? `<span class="chip warn">${a.behind} update${a.behind > 1 ? "s" : ""} available</span>` : '<span class="chip ok">Up to date</span>'}</td></tr>`).join("")}</tbody></table>`;
      const n = info.installed.filter(a => a.behind).length;
      $("#appinfo", root).textContent = n ? `${n} app${n > 1 ? "s have" : " has"} updates available.` : "Everything is up to date.";
      const upd = $("#appupd", root), cks = () => $$(".appck", root).filter(c => c.checked).map(c => c.value);
      const sync = () => { upd.disabled = !cks().length; }; $$(".appck", root).forEach(c => c.onchange = sync); sync();
      upd.onclick = async () => {
        const sel = cks();
        if (!await confirmBox("Update apps", `Update <b>${esc(sel.join(", "))}</b>? A backup of ${esc(s.domain)} is taken first. The code is shared, so <b>every site on ${esc(s.server_name)}</b> gets the new version and may briefly restart.`, "Update")) return;
        busy(upd, async () => { const r = await api("POST", `/api/sites/${s.id}/update-apps`, { apps: sel }); startJob(r.job_id, `Update apps on ${s.domain}`); });
      };
      $("#appadd", root).onclick = () => installAppDialog(s, info.available);
    },
  };
}
const EMPTY_RESERVED = new Set(["frappe", "erpnext", "hrms", "payments", "lending", "healthcare", "education", "webshop", "crm", "helpdesk", "insights", "builder", "print_designer", "test", "tests"]);
function emptyAppName(domain) {
  let n = domain.split(".")[0].toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "site";
  if (!/^[a-z]/.test(n)) n = "app_" + n;
  if (EMPTY_RESERVED.has(n)) n += "_app";
  return n.slice(0, 60);
}
function uploadDbDialog(s) {
  const d = dialog("Upload database", `<div class="note warn" style="margin-top:0">This <b>replaces all data</b> of ${esc(s.domain)} with the contents of the file. A safety backup is taken first, and the Administrator password becomes the one stored in that database.</div>
    <label class="l">Database file <span class="faint">(.sql or .sql.gz)</span></label><input type="file" id="fl" accept=".sql,.gz">
    <label class="l">Type <b>${esc(s.domain)}</b> to confirm</label><input id="cf" autocomplete="off" spellcheck="false">
    <div class="meter" id="pg" hidden style="margin-top:14px"><i style="width:0"></i></div><div class="hint" id="pgt"></div>`,
    `<button class="btn" data-close>Cancel</button><button class="btn danger" id="go" disabled>Upload and replace</button>`, { noFocus: true });
  const ok = () => { const f = $("#fl", d).files[0]; $("#go", d).disabled = !(f && /\.(sql|sql\.gz)$/i.test(f.name) && $("#cf", d).value.trim().toLowerCase() === s.domain); };
  $("#fl", d).onchange = ok; $("#cf", d).oninput = ok;
  $("#go", d).onclick = e => {
    const btn = e.currentTarget, f = $("#fl", d).files[0]; btn.disabled = true; $("#fl", d).disabled = true; $("#cf", d).disabled = true; $("#pg", d).hidden = false;
    const x = new XMLHttpRequest();
    x.open("PUT", `/api/sites/${s.id}/upload-db?filename=${encodeURIComponent(f.name)}&confirm=${encodeURIComponent($("#cf", d).value.trim())}`);
    x.upload.onprogress = ev => { if (ev.lengthComputable) { $("#pg i", d).style.width = (100 * ev.loaded / ev.total) + "%"; $("#pgt", d).textContent = `Uploading… ${Math.round(ev.loaded / 1048576)} of ${Math.round(ev.total / 1048576) || 1} MB`; } };
    x.onload = () => {
      let r = {}; try { r = JSON.parse(x.responseText); } catch { /* ignore */ }
      if (x.status === 200) { d.close(); startJob(r.job_id, `Upload database to ${s.domain}`); return; }
      toast(typeof r.detail === "string" ? r.detail : "Upload failed (" + x.status + ")", true); d.close();
    };
    x.onerror = () => { toast("Upload failed: connection lost", true); d.close(); };
    x.send(f);
  };
}
function installAppDialog(s, avail) {
  if (!avail.length) { dialog("Install app", `<p class="muted" style="margin:0">Every app in the registry is already installed on this site. Add more under <a href="#/apps" style="text-decoration:underline" data-close>Apps</a>.</p>`, `<button class="btn primary" data-close>OK</button>`, { noFocus: true }); return; }
  const d = dialog("Install app", `<p class="muted" style="margin:0 0 8px">A backup of <b>${esc(s.domain)}</b> is taken first. Apps not yet on the server are downloaded there (this can take several minutes).</p>
    ${avail.map(a => `<label class="check"><input type="checkbox" value="${esc(a.name)}"><div><b>${esc(a.title)}</b> <span class="faint mono">${esc(a.name)}</span><div class="hint">${a.on_server ? "Already on the server" : "Will be downloaded to the server"}${a.requires ? ` · needs ${esc(a.requires)}` : ""}</div></div></label>`).join("")}`,
    `<button class="btn" data-close>Cancel</button><button class="btn primary" id="go" disabled>Install</button>`, { noFocus: true });
  const sel = () => $$("input:checked", d).map(c => c.value);
  d.addEventListener("change", () => { $("#go", d).disabled = !sel().length; });
  $("#go", d).onclick = e => busy(e.currentTarget, async () => { const r = await api("POST", `/api/sites/${s.id}/install-apps`, { apps: sel() }); d.close(); startJob(r.job_id, `Install apps on ${s.domain}`); });
}
function siteActivity({ s }) {
  const js = S.jobs.filter(j => j.title.includes(s.domain));
  return {
    html: `<div class="card tbl">${js.length ? `<table><thead><tr><th>Job</th><th>Status</th><th class="hide-sm">By</th><th>Started</th><th></th></tr></thead><tbody>${js.map(j => `<tr><td>${esc(j.title)}</td><td>${badge(j.status)}</td><td class="hide-sm faint">${esc(j.user || "—")}</td><td class="faint">${ago(j.created)}</td><td style="text-align:right"><button class="btn sm" data-act="job" data-id="${j.id}" data-t="${esc(j.title)}">View log</button></td></tr>`).join("")}</tbody></table>` : emptyState("activity", "No activity", "Jobs for this site will appear here.")}</div>`,
  };
}

async function openAsAdmin(s) {
  const c = await api("GET", `/api/sites/${s.id}/credentials`);
  if (!c.password) { toast("The password is unknown for this site. Reset it in Operations first.", true); return; }
  const w = window.open("about:blank", "fm_login_" + s.id); if (!w) { toast("Allow pop-ups for this page, then try again.", true); return; }
  try { w.document.write("<p style='font:15px system-ui;padding:24px'>Signing in…</p>"); } catch { /* ignore */ }
  const f = document.createElement("form"); f.method = "POST"; f.action = siteUrl(s) + "/api/method/login"; f.target = w.name; f.style.display = "none";
  [["usr", "Administrator"], ["pwd", c.password]].forEach(([n, v]) => { const i = document.createElement("input"); i.type = "hidden"; i.name = n; i.value = v; f.appendChild(i); });
  document.body.appendChild(f); f.submit(); f.remove();
  setTimeout(() => { try { w.location.href = siteUrl(s) + "/app"; } catch { /* ignore */ } }, 1600);
  toast("Opening the site… if you see a login page, the password changed. Use Reset password.");
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
  await load("servers", "apps", "customers");
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
        <label class="l" for="cust">Customer <span class="faint">(optional)</span></label><select id="cust"><option value="">— none —</option>${S.customers.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</select>
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
        const r = await api("POST", "/api/sites", { domain: W.domain, company: W.company, server_id: W.server, apps, install_missing: miss.length > 0, add_dns: W.dns && !!(W.check && W.check.zone), enable_ssl: W.ssl, customer_id: $("#cust", root).value ? +$("#cust", root).value : null });
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
    actions: can("admin") ? `<button class="btn primary" data-act="newserver">${icon("plus")}New Server</button>` : "",
    html: `<div class="page-head"><h1>Servers</h1></div><p class="sub">Your VPS machines running ERPNext benches.</p><div class="card tbl">${S.servers.length
      ? `<table><thead><tr><th>Server</th><th>Status</th><th class="hide-sm">Version</th><th class="hide-sm">Sites</th><th class="hide-sm">CPU</th><th class="hide-sm">Memory</th><th class="hide-sm">Disk</th></tr></thead><tbody>${rows}</tbody></table>`
      : emptyState("server", "No servers yet", "Add the VPS you bought, then Fleet Manager prepares it for ERPNext.", can("admin") ? `<button class="btn primary" data-act="newserver">${icon("plus")}New Server</button>` : "")}</div>`,
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
    ? (can("support") ? `<button class="btn" data-act="refresh" data-id="${s.id}">${icon("refresh")}Refresh</button><button class="btn" data-act="installapps" data-id="${s.id}">${icon("plus")}Install apps</button>` : "")
    : "";
  const go = n => `<li class="${n.done ? "done" : n.cur ? "cur" : ""}"><div class="dot">${n.done ? icon("check") : n.i}</div><div class="b"><b>${n.t}</b><p>${n.p}</p>${n.btn || ""}</div></li>`;
  const done2 = s.status !== "new", conf = s.status === "configuring";
  const stepper = ready ? "" : `<div class="card pad" style="margin-bottom:16px"><h3>Set up this server</h3>
    ${s.last_error ? `<div class="note bad"><b>Last attempt failed:</b> ${esc(s.last_error)}</div>` : ""}
    <ul class="steps">${[
      { i: 1, t: "Server added", p: `${esc(s.ssh_user)}@${esc(s.ip)}:${s.ssh_port} · ERPNext ${esc(ver(s.version))}`, done: true },
      { i: 2, t: "Run the bootstrap script", p: "Copy the script to the VPS and run it once as root. It installs SSH prerequisites and authorizes this app.", done: done2, cur: !done2, btn: can("admin") ? `<button class="btn sm" data-act="bootstrap" data-id="${s.id}">${icon("download")}Show script</button>` : '<span class="faint">Ask an administrator</span>' },
      { i: 3, t: "Test the connection", p: "Checks that Fleet Manager can log in over SSH.", done: s.status === "bootstrapped" || conf, btn: can("support") ? `<button class="btn sm" data-act="testssh" data-id="${s.id}">Test SSH</button>` : "" },
      { i: 4, t: "Configure the server", p: conf ? "Setup is running — this takes 15–30 minutes." : "Installs MariaDB, Redis, Nginx, Node and bench with ERPNext.", cur: !conf && s.status !== "new", done: false,
        btn: conf ? `<button class="btn sm primary" data-act="runjob" data-q="${esc(s.name)}">View progress</button>` : can("admin") ? `<button class="btn sm primary" data-act="configure" data-id="${s.id}">Configure server</button>` : '<span class="faint">Ask an administrator</span>' },
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
      ${can("support") ? `<div class="toolbar" style="margin-bottom:12px"><button class="btn sm" data-act="oprestart" data-server="${s.id}">Restart web &amp; workers</button></div>` : ""}
      <div class="tiles">${m ? tile("CPU load", `${(100 * m.load / m.cores).toFixed(0)}%`, 100 * m.load / m.cores) + tile("Memory", `${m.mem_pct}%`, m.mem_pct) + tile("Disk", `${m.disk_pct}%`, m.disk_pct) : ""}${tile("Sites", sites.length)}</div>
      <div class="card pad"><h3>Server information</h3><div class="kv"><div>Address</div><div class="mono">${esc(s.ssh_user)}@${esc(s.ip)}:${s.ssh_port}</div><div>ERPNext</div><div>${esc(ver(s.version))}</div><div>System</div><div>${esc(s.os_info || "—")}</div>
        <div>Resources</div><div>${m ? `${m.cores} CPU · ${Math.round(m.mem_total_mb / 1024 * 10) / 10} GB RAM` : "—"}</div>
        <div>Network</div><div>${s.gateway ? `Behind provider gateway${s.inner_ip ? ` · inner IP <span class="mono">${esc(s.inner_ip)}</span>` : ""}${s.gateway_url ? ` · <a href="${esc(s.gateway_url)}" target="_blank" rel="noopener" style="text-decoration:underline">provider panel</a>` : ""}` : "Public IP on the server"}</div><div>Last refresh</div><div>${ago(s.metrics_at)}</div><div>Host key</div><div class="mono faint">${esc((s.host_fingerprint || "—").replace(/(.{2})(?=.)/g, "$1:").slice(0, 47))}</div></div></div>`;
  }
  return {
    crumbs: [["Servers", "#/servers"], [s.name]],
    actions: acts,
    html: `<div class="page-head"><h1>${esc(s.name)}</h1>${badge(s.status)}<span style="flex:1"></span>
      ${can("admin") ? `<button class="btn sm" data-act="editserver" data-id="${s.id}">Edit</button><button class="btn sm danger" data-act="delserver" data-id="${s.id}">Remove</button>` : ""}</div>
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
      <label class="check" style="padding-bottom:0"><input type="checkbox" name="gateway" ${s && s.gateway ? "checked" : ""}><div><b>Behind a provider gateway</b><div class="hint">The VPS has a private address and the provider routes web traffic to it, so each domain must also be added in the provider's panel. Adds a go-live checklist to every site.</div></div></label>
      <label class="l">Provider panel link <span class="faint">(optional)</span></label><input name="gateway_url" value="${esc(s && s.gateway_url)}" placeholder="https://panel.provider.com/vps/123">
      <label class="l">Password or private key ${s ? '<span class="faint">(blank keeps current)</span>' : ""}</label><textarea name="secret" autocomplete="off" spellcheck="false" rows="1" style="min-height:34px"></textarea>
      <div class="hint">Stored encrypted. For keys, paste the whole key including the BEGIN/END lines (no passphrase).</div></form>`,
      `<button class="btn" data-close>Cancel</button><button class="btn primary" id="save">${s ? "Save" : "Add server"}</button>`);
    const ta = $("[name=secret]", d), sel = $("[name=auth_type]", d);
    const sync = () => { const k = sel.value === "key"; ta.style.minHeight = k ? "150px" : "34px"; ta.style.webkitTextSecurity = k ? "none" : "disc"; ta.style.fontFamily = k ? "ui-monospace,Consolas,monospace" : "inherit"; };
    sel.onchange = sync; sync();
    const submit = () => busy($("#save", d), async () => {
      const f = $("#f", d); if (!f.reportValidity()) return;
      const x = Object.fromEntries(new FormData(f)); x.ssh_port = +x.ssh_port; x.gateway = !!x.gateway; x.gateway_url = x.gateway_url || ""; if (!x.version) x.version = s.version;
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
    crumbs: [["Apps"]], actions: can("admin") ? `<button class="btn primary" data-act="newapp">${icon("plus")}New App</button>` : "",
    html: `<div class="page-head"><h1>Apps</h1></div><p class="sub">Frappe apps you can install on servers and sites. Add your own from any git repository.</p>
    <div class="card tbl"><table><thead><tr><th>App</th><th class="hide-sm">Repository</th><th class="hide-sm">Branch</th><th class="hide-sm">Requires</th><th>Servers</th><th></th></tr></thead><tbody>
    ${S.apps.map(a => `<tr><td><div class="cell-main">${esc(a.title || a.name)} ${a.builtin ? "" : '<span class="chip">Custom</span>'}</div><div class="cell-sub mono">${esc(a.name)}</div></td><td class="hide-sm mono faint">${esc(a.git_url.replace(/^https?:\/\//, ""))}</td>
      <td class="hide-sm mono">${a.branch ? esc(a.branch) : '<span class="faint">server version</span>'}</td><td class="hide-sm mono faint">${esc(a.requires || "—")}</td><td>${a.servers}</td>
      <td style="text-align:right;white-space:nowrap">${can("admin") ? `<button class="btn sm" data-act="editapp" data-name="${esc(a.name)}">Edit</button>${a.builtin ? "" : ` <button class="btn sm danger" data-act="delapp" data-name="${esc(a.name)}">Remove</button>`}` : ""}</td></tr>`).join("")}</tbody></table></div>
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
      ? `<table><thead><tr><th>Task</th><th>Status</th><th class="hide-sm">By</th><th class="hide-sm">Started</th><th></th></tr></thead><tbody>${S.jobs.map(j => `<tr><td><div class="cell-main">${esc(j.title)}</div><div class="cell-sub">#${j.id} · ${esc(j.kind)}</div></td><td>${badge(j.status)}</td><td class="hide-sm">${esc(j.user || "—")}</td><td class="hide-sm faint">${ago(j.created)}</td><td style="text-align:right"><button class="btn sm" data-act="job" data-id="${j.id}" data-t="${esc(j.title)}">View log</button></td></tr>`).join("")}</tbody></table>`
      : emptyState("activity", "No jobs yet", "Jobs appear here when you set up servers or create sites.")}</div>`,
  };
}

// ───────────────────────────── deletion, customers, team ─────────────────────────────
function deleteDialog(s) {
  const admin = can("admin");
  const d = dialog(admin ? "Delete site" : "Request site deletion",
    `<div class="note bad" style="margin-top:0">${admin ? "This removes the site and its database from the server." : "Deleting needs an administrator's approval. Your request is saved and an admin will review it."}</div>
    <label class="l">Reason</label><textarea id="why" rows="2" placeholder="Why is this site being deleted?"></textarea>
    <label class="l">Type <b>${esc(s.domain)}</b> to confirm</label><input id="cf" autocomplete="off" spellcheck="false">
    <label class="check"><input type="checkbox" id="bk" checked><div><b>Back up first</b><div class="hint">Recommended. If the backup fails nothing is deleted. Site files stay in "archived_sites" on the server.</div></div></label>`,
    `<button class="btn" data-close>Cancel</button><button class="btn danger" id="go" disabled>${admin ? "Delete site" : "Send request"}</button>`, { noFocus: true });
  const ok = () => { $("#go", d).disabled = !($("#why", d).value.trim().length >= 3 && $("#cf", d).value.trim().toLowerCase() === s.domain); };
  $("#why", d).oninput = ok; $("#cf", d).oninput = ok;
  $("#go", d).onclick = e => busy(e.currentTarget, async () => {
    const r = await api("POST", `/api/sites/${s.id}/delete`, { reason: $("#why", d).value.trim(), confirm: $("#cf", d).value.trim(), backup_first: $("#bk", d).checked });
    d.close();
    if (r.pending) { toast("Request sent. An administrator will review it."); S.page = ""; route(); return; }
    startJob(r.job_id, `Delete site ${s.domain}`); location.hash = "#/sites";
  });
}

function customerForm(c) {
  const d = dialog(c ? "Edit customer" : "New customer", `<form id="f">
    <label class="l">Name</label><input name="name" required value="${esc(c && c.name)}" placeholder="Acme Traders">
    <div class="row2"><div><label class="l">Contact person</label><input name="contact" value="${esc(c && c.contact)}"></div><div><label class="l">Phone</label><input name="phone" value="${esc(c && c.phone)}"></div></div>
    <div class="row2"><div><label class="l">Email</label><input name="email" type="text" value="${esc(c && c.email)}"></div><div><label class="l">Plan</label><input name="plan" value="${esc(c && c.plan)}" placeholder="e.g. Pro, monthly"></div></div>
    <label class="l">Renews on</label><input name="renews_on" type="date" value="${esc(c && c.renews_on)}">
    <label class="l">Notes</label><textarea name="notes" rows="2">${esc(c && c.notes)}</textarea></form>`,
    `<button class="btn" data-close>Cancel</button><button class="btn primary" id="save">Save</button>`);
  const submit = () => busy($("#save", d), async () => {
    const f = $("#f", d); if (!f.reportValidity()) return;
    await api(c ? "PUT" : "POST", c ? `/api/customers/${c.id}` : "/api/customers", Object.fromEntries(new FormData(f))); d.close(); route(true); S.page === "customers" && route();
  });
  $("#save", d).onclick = submit; $("#f", d).onsubmit = e => { e.preventDefault(); submit(); };
}

const ROLE_TXT = { viewer: "Read-only", support: "Day-to-day operations: create sites, backups, logs, notes, customers", admin: "Everything, including servers, apps, team, deletions and settings" };
function userForm(existing) {
  const d = dialog(existing ? `Reset password for ${existing}` : "Add team member",
    existing ? `<label class="l">New password</label><input id="pw" type="password" autocomplete="new-password"><div class="hint">At least 8 characters. Ask them to change it after signing in (Settings → Account).</div>`
      : `<label class="l">Username</label><input id="un" autocomplete="off" spellcheck="false" placeholder="e.g. sara"><label class="l">Password</label><input id="pw" type="password" autocomplete="new-password">
        <label class="l">Role</label><select id="rl">${["support", "viewer", "admin"].map(r => `<option value="${r}">${r[0].toUpperCase() + r.slice(1)}</option>`).join("")}</select><div class="hint" id="rh">${esc(ROLE_TXT.support)}</div>`,
    `<button class="btn" data-close>Cancel</button><button class="btn primary" id="go">${existing ? "Reset password" : "Add user"}</button>`);
  const rl = $("#rl", d); if (rl) rl.onchange = () => { $("#rh", d).textContent = ROLE_TXT[rl.value]; };
  $("#go", d).onclick = e => busy(e.currentTarget, async () => {
    if (existing) await api("PUT", `/api/team/${encodeURIComponent(existing)}`, { password: $("#pw", d).value });
    else await api("POST", "/api/team", { username: $("#un", d).value.trim(), password: $("#pw", d).value, role: rl.value });
    d.close(); toast(existing ? "Password reset" : "User added"); route();
  });
}

async function pCustomers() {
  await load("customers");
  const chip = c => c.renewal === "overdue" ? `<span class="chip bad">Overdue ${-c.days_left} d</span>` : c.renewal === "soon" ? `<span class="chip warn">Renews in ${c.days_left} d</span>` : c.renewal === "ok" ? `<span class="faint">${esc(c.renews_on)}</span>` : `<span class="faint">—</span>`;
  const due = S.customers.filter(c => c.renewal === "overdue" || c.renewal === "soon").length;
  return {
    crumbs: [["Customers"]], actions: can("support") ? `<button class="btn primary" data-act="newcustomer">${icon("plus")}New Customer</button>` : "",
    html: `<div class="page-head"><h1>Customers</h1></div><p class="sub">The people and companies behind your sites, with plans and renewal dates.</p>
      ${due ? `<div class="note warn">${icon("alert")} ${due} renewal${due > 1 ? "s" : ""} due within 14 days or overdue.</div>` : ""}
      <div class="card tbl">${S.customers.length ? `<table><thead><tr><th>Customer</th><th class="hide-sm">Contact</th><th>Plan</th><th>Renewal</th><th>Sites</th><th></th></tr></thead><tbody>${S.customers.map(c => `<tr><td><div class="cell-main">${esc(c.name)}</div><div class="cell-sub">${esc(c.contact || "")}</div></td>
        <td class="hide-sm"><div>${esc(c.email || "—")}</div><div class="cell-sub">${esc(c.phone || "")}</div></td><td>${esc(c.plan || "—")}</td><td>${chip(c)}</td><td>${c.sites}</td>
        <td style="text-align:right;white-space:nowrap">${can("support") ? `<button class="btn sm" data-act="editcustomer" data-id="${c.id}">Edit</button>` : ""}${can("admin") ? ` <button class="btn sm danger" data-act="delcustomer" data-id="${c.id}">Delete</button>` : ""}</td></tr>`).join("")}</tbody></table>`
      : emptyState("building", "No customers yet", "Add the companies you host, then link their sites.", can("support") ? `<button class="btn primary" data-act="newcustomer">${icon("plus")}New Customer</button>` : "")}</div>`,
  };
}

async function pApprovals() {
  const rows = await api("GET", "/api/approvals");
  S.pending = rows.filter(r => r.status === "pending").length;
  const st = r => r.status === "pending" ? '<span class="badge amber"><i></i>Waiting</span>' : r.status === "approved" ? '<span class="badge green"><i></i>Approved</span>' : '<span class="badge"><i></i>Rejected</span>';
  return {
    crumbs: [["Approvals"]],
    html: `<div class="page-head"><h1>Approvals</h1></div><p class="sub">${can("admin") ? "Dangerous actions requested by support staff wait here for your decision." : "Your requests for actions that need an administrator."}</p>
      <div class="card tbl">${rows.length ? `<table><thead><tr><th>Request</th><th class="hide-sm">By</th><th class="hide-sm">Reason</th><th>Status</th><th></th></tr></thead><tbody>${rows.map(r => `<tr><td><div class="cell-main">${r.action === "restore_site" ? "Restore" : "Delete"} ${esc(r.site_domain)}</div>${r.action === "restore_site" ? `<div class="cell-sub">backup ${esc((JSON.parse(r.params || "{}")).group || "")} from ${esc((JSON.parse(r.params || "{}")).source || "")}</div>` : ""}<div class="cell-sub">${ago(r.ts)}</div></td><td class="hide-sm">${esc(r.requested_by)}</td><td class="hide-sm">${esc(r.reason || "—")}</td><td>${st(r)}${r.decided_by ? `<div class="cell-sub">by ${esc(r.decided_by)}</div>` : ""}</td>
        <td style="text-align:right;white-space:nowrap">${r.status === "pending" && can("admin") ? `<button class="btn sm danger" data-act="approve" data-id="${r.id}" data-d="${esc(r.site_domain)}" data-a="${esc(r.action)}">Approve…</button> <button class="btn sm" data-act="reject" data-id="${r.id}">Reject</button>` : ""}</td></tr>`).join("")}</tbody></table>` : emptyState("clipboard", "Nothing waiting", "Requests that need an administrator will appear here.")}</div>`,
  };
}

async function pAudit() {
  let limit = 100, q = "", who = "";
  return {
    crumbs: [["Audit log"]],
    html: `<div class="page-head"><h1>Audit log</h1></div><p class="sub">Who did what, and when. Passwords are never recorded.</p>
      <div class="toolbar"><div class="search">${icon("search")}<input id="aq" placeholder="Search actions, sites, details" autocomplete="off"></div><select id="au" style="width:auto;min-width:150px" aria-label="User"><option value="">All users</option></select></div>
      <div class="card tbl" id="atbl"><div class="empty faint">Loading…</div></div><div style="text-align:center;margin-top:12px" id="amore"></div>`,
    mount(root) {
      const tbl = $("#atbl", root);
      const users = new Set();
      const load = async () => {
        const rows = await api("GET", `/api/audit?limit=${limit}&q=${encodeURIComponent(q)}&user=${encodeURIComponent(who)}`);
        rows.forEach(r => users.add(r.user));
        const sel = $("#au", root); if (sel.options.length <= 1) [...users].sort().forEach(u => sel.insertAdjacentHTML("beforeend", `<option>${esc(u)}</option>`));
        tbl.innerHTML = rows.length ? `<table><thead><tr><th>When</th><th>User</th><th>Action</th><th>Target</th><th class="hide-sm">Details</th><th class="hide-sm">IP</th></tr></thead><tbody>${rows.map(r => `<tr><td class="faint" title="${esc(r.ts)} UTC" style="white-space:nowrap">${ago(r.ts)}</td><td>${esc(r.user)} ${r.role ? `<span class="rolechip ${esc(r.role)}">${esc(r.role)}</span>` : ""}</td><td>${esc(r.action.replace(/_/g, " "))}</td><td class="mono">${esc(r.target)}</td><td class="hide-sm muted">${esc(r.detail)}</td><td class="hide-sm mono faint">${esc(r.ip)}</td></tr>`).join("")}</tbody></table>` : emptyState("shield", "Nothing found", "No entries match.");
        $("#amore", root).innerHTML = rows.length >= limit && limit < 500 ? `<button class="btn" id="more">Load more</button>` : "";
        const m = $("#more", root); if (m) m.onclick = () => { limit += 100; load(); };
      };
      load();
      let t; $("#aq", root).oninput = e => { clearTimeout(t); t = setTimeout(() => { q = e.target.value; limit = 100; load(); }, 300); };
      $("#au", root).onchange = e => { who = e.target.value; limit = 100; load(); };
    },
  };
}

async function pSettings(tab = "account") {
  const tabs = [["account", "Account"], ...(can("admin") ? [["team", "Team"], ["integrations", "Integrations"], ["storage", "Backup storage"], ["alerts", "Alerts"]] : [])];
  if (!tabs.some(t => t[0] === tab)) tab = "account";
  let body = { html: "" };
  if (tab === "account") {
    body = {
      html: `<div class="cards"><div class="card pad"><h3>Your account</h3><div class="kv"><div>Username</div><div>${esc(S.user)}</div><div>Role</div><div><span class="rolechip ${esc(S.role)}">${esc(S.role)}</span> <span class="faint">${esc(ROLE_TXT[S.role] || "")}</span></div></div></div>
        <div class="card pad"><h3>Change password</h3><form id="pf"><label class="l">Current password</label><input name="current" type="password" autocomplete="current-password" required>
        <label class="l">New password <span class="faint">(min. 8 characters)</span></label><input name="new" type="password" autocomplete="new-password" required minlength="8">
        <div style="margin-top:14px"><button class="btn primary" id="psave">Update password</button></div></form></div></div>`,
      mount(root) { $("#pf", root).onsubmit = e => { e.preventDefault(); busy($("#psave", root), async () => { await api("POST", "/api/auth/password", Object.fromEntries(new FormData(e.target))); e.target.reset(); toast("Password updated"); }); }; },
    };
  } else if (tab === "team") {
    const users = await api("GET", "/api/team");
    body = {
      html: `<div class="toolbar"><div style="flex:1" class="muted">People who can sign in to Fleet Manager.</div><button class="btn primary" data-act="adduser">${icon("plus")}Add user</button></div>
        <div class="card tbl"><table><thead><tr><th>User</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody>${users.map(u => { const me = u.username === S.user; return `<tr><td><div class="cell-main">${esc(u.username)} ${me ? '<span class="chip">You</span>' : ""}</div></td>
          <td><select class="inl" data-role="${esc(u.username)}" ${me ? "disabled" : ""}>${["viewer", "support", "admin"].map(r => `<option value="${r}" ${u.role === r ? "selected" : ""}>${r[0].toUpperCase() + r.slice(1)}</option>`).join("")}</select></td>
          <td>${u.disabled ? '<span class="badge"><i></i>Disabled</span>' : '<span class="badge green"><i></i>Active</span>'}</td>
          <td style="text-align:right;white-space:nowrap"><button class="btn sm" data-act="resetpw" data-u="${esc(u.username)}">Reset password</button>${me ? "" : ` <button class="btn sm" data-act="toggleuser" data-u="${esc(u.username)}" data-off="${u.disabled ? 0 : 1}">${u.disabled ? "Enable" : "Disable"}</button> <button class="btn sm danger" data-act="deluser" data-u="${esc(u.username)}">Delete</button>`}</td></tr>`; }).join("")}</tbody></table></div>
        <p class="hint">${Object.entries(ROLE_TXT).map(([k, v]) => `<b style="text-transform:capitalize">${k}</b>: ${esc(v)}`).join(" · ")}</p>`,
      mount(root) { $$("[data-role]", root).forEach(sel => { sel.onchange = () => busy(null, async () => { await api("PUT", `/api/team/${encodeURIComponent(sel.dataset.role)}`, { role: sel.value }); toast("Role updated"); route(); }); }); },
    };
  } else if (tab === "storage") {
    body = await setStorage();
  } else if (tab === "alerts") {
    body = await setAlerts();
  } else {
    const [c, k] = await Promise.all([api("GET", "/api/settings/cpanel"), api("GET", "/api/manager-key")]);
    body = {
      html: `<div class="card pad" style="margin-bottom:16px"><h3>cPanel</h3><form id="f">
        <div class="row2"><div><label class="l">Host</label><input name="host" required value="${esc(c.host)}" placeholder="cpanel.example.com"></div><div><label class="l">Port</label><input name="port" type="number" value="${c.port || 2083}"></div></div>
        <div class="row2"><div><label class="l">Username</label><input name="user" required value="${esc(c.user)}"></div><div><label class="l">Sign in with</label><select name="auth"><option value="token" ${c.auth !== "password" ? "selected" : ""}>API token</option><option value="password" ${c.auth === "password" ? "selected" : ""}>cPanel password (no 2FA)</option></select></div></div>
        <label class="l">API token or password ${c.has_token ? '<span class="faint">(saved — blank keeps it)</span>' : ""}</label><input name="token" type="password" autocomplete="off">
        <label class="check"><input type="checkbox" name="verify_tls" ${c.verify_tls ? "checked" : ""}><div><b>Verify TLS certificate</b></div></label>
        <div style="display:flex;gap:8px;margin-top:6px"><button class="btn primary" id="save">Save</button><button type="button" class="btn" id="test" ${c.configured ? "" : "disabled"}>Test connection</button></div></form></div>
      <div class="card pad"><h3>Fleet Manager SSH key</h3><p class="muted" style="margin:0 0 10px">The bootstrap script authorizes this public key on each VPS.</p>
        <textarea readonly class="mono" rows="3" style="min-height:70px">${esc(k.public_key)}</textarea><div style="margin-top:8px"><button class="btn sm" data-act="copy" data-v="${esc(k.public_key)}">${icon("copy")}Copy</button></div></div>`,
      mount(root) {
        $("#f", root).onsubmit = e => { e.preventDefault(); busy($("#save", root), async () => { const x = Object.fromEntries(new FormData(e.target)); x.port = +x.port; x.verify_tls = !!x.verify_tls; await api("PUT", "/api/settings/cpanel", x); toast("Saved"); $("#test", root).disabled = false; }); };
        $("#test", root).onclick = e => busy(e.currentTarget, async () => { const r = await api("POST", "/api/settings/cpanel/test"); toast("Connected · " + r.domains.join(", ")); });
      },
    };
  }
  return {
    crumbs: [["Settings"]],
    html: `<div class="page-head"><h1>Settings</h1></div><nav class="tabs">${tabs.map(([k, l]) => `<a href="#/settings/${k}" class="${tab === k ? "on" : ""}">${l}</a>`).join("")}</nav>${body.html}`,
    mount: body.mount,
  };
}

// ───────────────────────────── monitoring ─────────────────────────────
const barsHtml = a => `<div class="bars" role="img" aria-label="Last 24 hours">${a.map(s => `<i class="${s}"></i>`).join("")}</div>`;
const pct = v => v == null ? "—" : (v >= 99.995 ? "100%" : v.toFixed(2) + "%");
const sevBadge = s => s === "crit" ? '<span class="badge red"><i></i>Critical</span>' : '<span class="badge amber"><i></i>Warning</span>';
const incLink = i => i.target_type === "site" ? `#/sites/${i.target_id}` : `#/servers/${i.target_id}`;

function incidentRow(i, canAct) {
  return `<div class="inc ${i.severity}"><div class="b"><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${sevBadge(i.severity)}<b>${esc(i.title)}</b><a href="${incLink(i)}" style="text-decoration:underline" class="muted">${esc(i.target_name)}</a></div>
    <div class="muted" style="margin-top:4px;white-space:pre-wrap">${esc(i.detail || "")}</div>
    <div class="cell-sub">Opened ${ago(i.opened_at)}${i.acked_by ? ` · acknowledged by ${esc(i.acked_by)}` : ""}${i.status === "resolved" ? ` · resolved ${ago(i.resolved_at)}${i.resolved_by && i.resolved_by !== "auto" ? ` by ${esc(i.resolved_by)}` : ""}` : ""}</div></div>
    ${canAct && i.status === "open" && can("support") ? `<div class="btnrow">${i.acked_by ? "" : `<button class="btn sm" data-act="incack" data-id="${i.id}">Acknowledge</button>`}<button class="btn sm" data-act="incclose" data-id="${i.id}">Close</button></div>` : ""}</div>`;
}

async function pMonitoring() {
  const [sum, open, done] = await Promise.all([api("GET", "/api/monitor/summary"), api("GET", "/api/incidents?status=open"), api("GET", "/api/incidents?status=resolved&limit=10")]);
  S.incidents = open;
  const upN = sum.sites.filter(s => s.status === "up").length;
  const worst = sum.sites.map(s => s.uptime24).filter(v => v != null);
  const tile = (k, v, sub) => `<div class="card tile"><div class="k">${k}</div><div class="v">${v}</div><div class="cell-sub">${sub || ""}</div></div>`;
  return {
    crumbs: [["Monitoring"]],
    actions: can("support") ? `<button class="btn" data-act="monrun">${icon("refresh")}Check now</button>` : "",
    html: `<div class="page-head"><h1>Monitoring</h1></div><p class="sub">Uptime, server health and open problems. Checks run every minute while Fleet Manager is running.</p>
      <div class="tiles">${tile("Sites up", `${upN}<span class="faint" style="font-size:15px"> / ${sum.sites.length}</span>`, sum.sites.length - upN ? `${sum.sites.length - upN} down` : "all responding")}
        ${tile("Open incidents", sum.open, sum.critical ? `${sum.critical} critical` : sum.open ? "warnings only" : "all clear")}
        ${tile("Worst uptime (24 h)", worst.length ? pct(Math.min(...worst)) : "—", "across all sites")}
        ${tile("Servers", sum.servers.length, "being watched")}</div>
      <div class="card pad" style="margin-bottom:16px"><h3>Open incidents</h3>${open.length ? open.map(i => incidentRow(i, true)).join("") : `<div class="muted">${icon("check")} Nothing needs attention.</div>`}</div>
      <div class="card tbl" style="margin-bottom:16px"><table><thead><tr><th>Site</th><th class="hide-sm">Last 24 hours</th><th>Uptime 24 h</th><th class="hide-sm">7 d</th><th class="hide-sm">30 d</th><th class="hide-sm">Speed</th><th class="hide-sm">HTTPS expires</th></tr></thead><tbody>
      ${sum.sites.length ? sum.sites.map(s => `<tr data-href="#/sites/${s.id}" tabindex="0"><td><div class="cell-main">${esc(s.domain)}</div><div class="cell-sub">${esc(s.server_name)}${s.suspended ? " · suspended" : ""}</div></td><td class="hide-sm" style="min-width:200px">${barsHtml(s.bars)}</td>
        <td>${badge(s.status)} <b style="margin-left:4px">${pct(s.uptime24)}</b></td><td class="hide-sm">${pct(s.uptime7)}</td><td class="hide-sm">${pct(s.uptime30)}</td><td class="hide-sm faint">${s.ms != null ? s.ms + " ms" : "—"}</td><td class="hide-sm faint">${esc(s.ssl_expires || "—")}</td></tr>`).join("") : `<tr><td colspan="7">${emptyState("globe", "No sites to watch", "Sites you create appear here automatically.")}</td></tr>`}</tbody></table></div>
      <div class="card tbl" style="margin-bottom:16px"><table><thead><tr><th>Server</th><th>CPU</th><th>Memory</th><th>Disk</th><th class="hide-sm">Memory trend</th><th class="hide-sm">Updated</th></tr></thead><tbody>
      ${sum.servers.map(v => { const cpu = v.cores ? Math.round(100 * v.load / v.cores) : 0; const mini = p => `<div class="mini"><span>${p ?? "—"}%</span>${meter(p || 0)}</div>`;
        return `<tr data-href="#/servers/${v.id}" tabindex="0"><td class="cell-main">${esc(v.name)}</td><td><div class="mini"><span>${cpu}%</span>${meter(cpu)}</div></td><td>${mini(v.mem_pct)}</td><td>${mini(v.disk_pct)}</td><td class="hide-sm">${sparkHtml(v.mem_spark)}</td><td class="hide-sm faint">${ago(v.metrics_at)}</td></tr>`; }).join("") || `<tr><td colspan="6" class="faint" style="padding:20px">No ready servers.</td></tr>`}</tbody></table></div>
      ${done.length ? `<div class="card pad"><h3>Recently resolved</h3>${done.map(i => incidentRow(i, false)).join("")}</div>` : ""}`,
  };
}
const sparkHtml = a => { if (!a || a.length < 2) return '<span class="faint">collecting…</span>'; const w = 120, h = 28, pts = a.map((v, i) => `${(i / (a.length - 1) * w).toFixed(1)},${(h - (Math.min(100, v) / 100) * h).toFixed(1)}`).join(" "); return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".7"/></svg>`; };

async function loadUptime(root, s) {
  const box = $("#uptime", root); if (!box) return;
  let u; try { u = await api("GET", `/api/sites/${s.id}/uptime`); } catch { return; }
  if (!box.isConnected) return;
  const cell = (k, v) => `<div><div class="faint" style="font-size:12.5px">${k}</div><div style="font-size:18px;font-weight:600">${pct(v)}</div></div>`;
  box.innerHTML = `<div class="card pad" style="margin-bottom:16px"><h3 style="display:flex;align-items:center"><span style="flex:1">Uptime</span><a href="#/monitoring" class="muted" style="font-weight:400;text-decoration:underline">Monitoring</a></h3>
    ${barsHtml(u.bars)}<div class="btnrow" style="gap:28px;margin:12px 0 0">${cell("24 hours", u.uptime24)}${cell("7 days", u.uptime7)}${cell("30 days", u.uptime30)}${u.ssl_expires ? cell("HTTPS expires", null).replace("—", esc(u.ssl_expires)) : ""}</div>
    ${u.incidents.length ? `<div style="margin-top:14px">${u.incidents.slice(0, 3).map(i => incidentRow(i, true)).join("")}</div>` : ""}</div>`;
}

// ───────────────────────────── backups ─────────────────────────────
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const pad2 = n => String(n).padStart(2, "0");
const policyText = p => !p.enabled ? "Off" : p.frequency === "daily" ? `Daily at ${pad2(p.hour)}:00` : p.frequency === "weekly" ? `${DAYS[p.weekday]}s at ${pad2(p.hour)}:00` : `Every ${p.interval_hours} h`;
const runChip = r => !r ? '<span class="faint">never</span>' : r.status === "ok" ? `<span class="chip ok">OK</span>` : r.status === "failed" ? `<span class="chip bad" title="${esc(r.message)}">Failed</span>` : '<span class="chip warn">Running</span>';
const offChip = r => !r || !r.offsite_status ? "" : r.offsite_status === "ok" ? '<span class="chip info" title="Copied to offsite storage">Offsite ✓</span>' : r.offsite_status.startsWith("skipped") ? '<span class="chip">Offsite skipped</span>' : `<span class="chip bad" title="${esc(r.offsite_status)}">Offsite failed</span>`;

async function pBackups() {
  const o = await api("GET", "/api/backups");
  S.bk = o;
  const dest = o.destination;
  const failed = o.sites.filter(s => s.last && s.last.status === "failed").length;
  return {
    crumbs: [["Backups"]], actions: "",
    html: `<div class="page-head"><h1>Backups</h1></div><p class="sub">Automatic backups, retention and offsite copies for every site.</p>
      ${failed ? `<div class="note bad">${icon("alert")} ${failed} site${failed > 1 ? "s have" : " has"} a failed latest backup.</div>` : ""}
      <div class="cards"><div class="card pad"><h3>Default schedule</h3><div style="font-size:18px;font-weight:600">${esc(policyText(o.default))}</div>
        <p class="muted" style="margin:6px 0 12px">Keep the newest ${o.default.keep} backups on the server${o.default.offsite ? `, and ${o.default.keep_offsite} offsite` : ""}. Applies to every site without its own schedule.</p>
        ${can("admin") ? `<button class="btn sm" data-act="bkpolicy" data-id="">Change…</button>` : ""}</div>
        <div class="card pad"><h3>Offsite storage</h3>${dest.configured ? `<div style="font-size:18px;font-weight:600">${dest.type === "s3" ? "S3-compatible" : "SFTP"} <span class="faint" style="font-weight:400;font-size:14px">${esc(dest.type === "s3" ? dest.path : dest.host + ":" + dest.path)}</span></div><p class="muted" style="margin:6px 0 12px">Copies go straight from each server to the storage.</p>` : `<div style="font-size:16px;font-weight:600">Not configured</div><p class="muted" style="margin:6px 0 12px">A copy outside the server protects you if the VPS itself is lost.</p>`}
        ${can("admin") ? `<a class="btn sm" href="#/settings/storage">${dest.configured ? "Manage" : "Set up"}</a>` : ""}</div></div>
      <div class="card tbl" style="margin-bottom:16px"><table><thead><tr><th>Site</th><th>Last backup</th><th class="hide-sm">Schedule</th><th class="hide-sm">Next run</th><th></th></tr></thead><tbody>
      ${o.sites.length ? o.sites.map(s => `<tr><td><a href="#/sites/${s.id}/backups"><div class="cell-main">${esc(s.domain)}</div></a><div class="cell-sub">${esc(s.server_name)}</div></td>
        <td>${runChip(s.last)} ${offChip(s.last)}<div class="cell-sub">${s.last_ok ? `last good ${ago(s.last_ok.started)}${s.last_ok.size_bytes ? " · " + fmtBytes(s.last_ok.size_bytes) : ""}` : "no good backup yet"}</div></td>
        <td class="hide-sm">${esc(policyText(s.policy))}<div class="cell-sub">${s.policy.source === "site" ? "custom" : "default"}</div></td>
        <td class="hide-sm faint">${s.next_run ? (new Date(s.next_run) <= new Date() ? "due now" : new Date(s.next_run).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" })) : "—"}</td>
        <td style="text-align:right;white-space:nowrap"><button class="btn sm" data-act="opbackup" data-id="${s.id}">Back up now</button>${can("admin") ? ` <button class="btn sm" data-act="bkpolicy" data-id="${s.id}">Schedule…</button>` : ""}</td></tr>`).join("")
        : `<tr><td colspan="5">${emptyState("drive", "No sites yet", "Backups start automatically once a site exists.")}</td></tr>`}</tbody></table></div>
      <div class="card tbl"><table><thead><tr><th>Recent runs</th><th>Result</th><th class="hide-sm">Size</th><th class="hide-sm">Trigger</th><th>When</th></tr></thead><tbody>
      ${o.runs.length ? o.runs.map(r => `<tr><td>${esc(r.domain)}</td><td>${runChip(r)} ${offChip(r)}${r.status === "failed" ? `<div class="cell-sub" style="max-width:360px">${esc(r.message)}</div>` : ""}</td><td class="hide-sm faint">${r.size_bytes ? fmtBytes(r.size_bytes) : "—"}</td><td class="hide-sm faint">${esc(r.trigger)}</td><td class="faint">${ago(r.started)}</td></tr>`).join("") : `<tr><td colspan="5" class="faint" style="padding:20px">No backups have run yet.</td></tr>`}</tbody></table></div>
      <p class="hint">Schedule times use the clock of the computer running Fleet Manager (${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}). Backups only run while Fleet Manager is running.</p>`,
  };
}

async function policyDialog(siteId) {
  const site = siteId ? siteById(siteId) : null;
  const p = siteId ? await api("GET", `/api/sites/${siteId}/backup-policy`) : S.bk.default;
  const d = dialog(site ? `Backup schedule — ${site.domain}` : "Default backup schedule", `<form id="f">
    <label class="check" style="padding-top:0"><input type="checkbox" name="enabled" ${p.enabled ? "checked" : ""}><div><b>Automatic backups</b></div></label>
    <div class="row2"><div><label class="l">Repeat</label><select name="frequency"><option value="daily" ${p.frequency === "daily" ? "selected" : ""}>Every day</option><option value="weekly" ${p.frequency === "weekly" ? "selected" : ""}>Every week</option><option value="hours" ${p.frequency === "hours" ? "selected" : ""}>Every few hours</option></select></div>
      <div id="r-hour"><label class="l">At</label><select name="hour">${[...Array(24).keys()].map(h => `<option value="${h}" ${p.hour === h ? "selected" : ""}>${pad2(h)}:00</option>`).join("")}</select></div>
      <div id="r-int" hidden><label class="l">Every (hours)</label><input name="interval_hours" type="number" min="1" max="168" value="${p.interval_hours}"></div></div>
    <div id="r-day" ${p.frequency === "weekly" ? "" : "hidden"}><label class="l">Day</label><select name="weekday">${DAYS.map((n, i) => `<option value="${i}" ${p.weekday === i ? "selected" : ""}>${n}</option>`).join("")}</select></div>
    <div class="row2"><div><label class="l">Keep on server</label><input name="keep" type="number" min="1" max="60" value="${p.keep}"></div><div><label class="l">Keep offsite</label><input name="keep_offsite" type="number" min="1" max="365" value="${p.keep_offsite}"></div></div>
    <label class="check"><input type="checkbox" name="offsite" ${p.offsite ? "checked" : ""}><div><b>Also copy offsite</b><div class="hint">Needs offsite storage in Settings → Storage.</div></div></label></form>`,
    `${site && p.source === "site" ? `<button class="btn" id="inh" style="margin-right:auto">Use default</button>` : ""}<button class="btn" data-close>Cancel</button><button class="btn primary" id="save">Save</button>`);
  const f = $("#f", d), sync = () => { const v = f.frequency.value; $("#r-day", d).hidden = v !== "weekly"; $("#r-int", d).hidden = v !== "hours"; $("#r-hour", d).hidden = v === "hours"; };
  f.frequency.onchange = sync; sync();
  $("#save", d).onclick = e => busy(e.currentTarget, async () => {
    const x = { enabled: f.enabled.checked, frequency: f.frequency.value, hour: +f.hour.value, weekday: +f.weekday.value, interval_hours: +f.interval_hours.value, keep: +f.keep.value, keep_offsite: +f.keep_offsite.value, offsite: f.offsite.checked };
    await api("PUT", siteId ? `/api/sites/${siteId}/backup-policy` : "/api/backups/policy", x); d.close(); toast("Schedule saved"); route();
  });
  const inh = $("#inh", d); if (inh) inh.onclick = () => busy(inh, async () => { await api("DELETE", `/api/sites/${siteId}/backup-policy`); d.close(); toast("Using the default schedule"); route(); });
}

function restoreDialog(s, g) {
  const admin = can("admin"), both = g.server && g.offsite;
  const d = dialog(admin ? "Restore backup" : "Request a restore", `<div class="note warn" style="margin-top:0">This <b>replaces the current data</b> of ${esc(s.domain)} with the backup from <b>${esc(g.label)}</b>. A safety backup of the current state is taken first. ${admin ? "" : "An administrator must approve this request."}</div>
    ${both ? `<label class="l">Restore from</label><select id="src"><option value="server">The server</option><option value="offsite">Offsite storage</option></select>` : `<input type="hidden" id="src" value="${g.server ? "server" : "offsite"}">`}
    <label class="l">Reason</label><textarea id="why" rows="2" placeholder="Why is this restore needed?"></textarea>
    <label class="l">Type <b>${esc(s.domain)}</b> to confirm</label><input id="cf" autocomplete="off" spellcheck="false">`,
    `<button class="btn" data-close>Cancel</button><button class="btn danger" id="go" disabled>${admin ? "Restore" : "Send request"}</button>`, { noFocus: true });
  const ok = () => { $("#go", d).disabled = !($("#why", d).value.trim().length >= 3 && $("#cf", d).value.trim().toLowerCase() === s.domain); };
  $("#why", d).oninput = ok; $("#cf", d).oninput = ok;
  $("#go", d).onclick = e => busy(e.currentTarget, async () => {
    const r = await api("POST", `/api/sites/${s.id}/restore`, { group: g.id, source: $("#src", d).value, reason: $("#why", d).value.trim(), confirm: $("#cf", d).value.trim() });
    d.close();
    if (r.pending) { toast("Request sent. An administrator will review it."); return; }
    startJob(r.job_id, `Restore ${s.domain}`);
  });
}

function moveDialog(s) {
  const targets = S.servers.filter(v => v.status === "ready" && v.id !== s.server_id && v.version === (S.servers.find(x => x.id === s.server_id) || {}).version);
  const d = dialog("Move to another server", targets.length ? `<div class="note warn" style="margin-top:0">The site is backed up, copied to the new server (through this computer) and restored there. The original stays untouched on <b>${esc(s.server_name)}</b>. Afterwards point DNS${s.gateway ? " and the provider panel" : ""} to the new server.</div>
    <label class="l">New server</label><select id="tg">${targets.map(v => `<option value="${v.id}">${esc(v.name)} — ${esc(v.ip)}</option>`).join("")}</select>
    <label class="l">Type <b>${esc(s.domain)}</b> to confirm</label><input id="cf" autocomplete="off" spellcheck="false">` : `<p class="muted">No other ready server runs the same ERPNext version (${esc(ver((S.servers.find(x => x.id === s.server_id) || {}).version))}).</p>`,
    targets.length ? `<button class="btn" data-close>Cancel</button><button class="btn primary" id="go" disabled>Start move</button>` : `<button class="btn primary" data-close>OK</button>`, { noFocus: !targets.length });
  if (!targets.length) return;
  $("#cf", d).oninput = () => { $("#go", d).disabled = $("#cf", d).value.trim().toLowerCase() !== s.domain; };
  $("#go", d).onclick = e => busy(e.currentTarget, async () => { const r = await api("POST", `/api/sites/${s.id}/move`, { server_id: +$("#tg", d).value, confirm: $("#cf", d).value.trim() }); d.close(); startJob(r.job_id, `Move ${s.domain}`); });
}

// ───────────────────────────── settings: storage, alerts ─────────────────────────────
async function setStorage() {
  const d = await api("GET", "/api/backups/destination");
  const t = d.type || "s3", v = k => esc(d[k] ?? "");
  return {
    html: `<div class="card pad" style="max-width:720px"><h3>Offsite backup storage</h3>
      <p class="muted" style="margin:0 0 12px">Each server uploads its backups straight to this storage, so a copy survives even if the VPS is lost. Works with any S3-compatible service (AWS S3, Backblaze B2, Wasabi, Cloudflare R2, MinIO …) or an SFTP server.</p>
      <form id="f"><label class="l">Type</label><select name="type"><option value="s3" ${t === "s3" ? "selected" : ""}>S3-compatible</option><option value="sftp" ${t === "sftp" ? "selected" : ""}>SFTP server</option></select>
      <div id="s3"><div class="row2"><div><label class="l">Provider</label><select name="provider">${["AWS", "Backblaze", "Wasabi", "Cloudflare", "Minio", "Other"].map(p => `<option ${d.provider === p ? "selected" : ""}>${p}</option>`).join("")}</select></div><div><label class="l">Region <span class="faint">(optional)</span></label><input name="region" value="${v("region")}" placeholder="us-east-1"></div></div>
        <label class="l">Endpoint <span class="faint">(blank for AWS)</span></label><input name="endpoint" value="${v("endpoint")}" placeholder="https://s3.eu-central-003.backblazeb2.com">
        <div class="row2"><div><label class="l">Access key</label><input name="access_key" value="${v("access_key")}" autocomplete="off"></div><div><label class="l">Secret key ${d.has_secret ? '<span class="faint">(saved — blank keeps it)</span>' : ""}</label><input name="secret_key" type="password" autocomplete="new-password"></div></div>
        <label class="l">Bucket and folder</label><input name="path_s3" value="${t === "s3" ? v("path") : ""}" placeholder="my-bucket/fleet-backups"></div>
      <div id="sf"><div class="row2"><div><label class="l">Host</label><input name="host" value="${v("host")}" placeholder="backup.example.com"></div><div><label class="l">Port</label><input name="port" type="number" value="${d.port || 22}"></div></div>
        <div class="row2"><div><label class="l">User</label><input name="user" value="${v("user")}" autocomplete="off"></div><div><label class="l">Password ${d.has_secret ? '<span class="faint">(saved — blank keeps it)</span>' : ""}</label><input name="password" type="password" autocomplete="new-password"></div></div>
        <label class="l">Folder</label><input name="path_sf" value="${t === "sftp" ? v("path") : ""}" placeholder="/backups/fleet"></div>
      <div style="display:flex;gap:8px;margin-top:14px"><button class="btn primary" id="save">Save</button><button type="button" class="btn" id="test" ${d.configured ? "" : "disabled"}>Test</button>${d.configured ? '<button type="button" class="btn danger" id="rm" style="margin-left:auto">Remove</button>' : ""}</div></form>
      <p class="hint">“Test” uploads and deletes a tiny file from a ready server. The first offsite copy installs <span class="mono">rclone</span> on that server automatically.</p></div>`,
    mount(root) {
      const f = $("#f", root), sync = () => { $("#s3", root).hidden = f.type.value !== "s3"; $("#sf", root).hidden = f.type.value !== "sftp"; };
      f.type.onchange = sync; sync();
      f.onsubmit = e => { e.preventDefault(); busy($("#save", root), async () => {
        const x = Object.fromEntries(new FormData(f)), s3 = x.type === "s3";
        const body = { type: x.type, path: (s3 ? x.path_s3 : x.path_sf).trim(), provider: x.provider, endpoint: x.endpoint.trim(), region: x.region.trim(), access_key: x.access_key.trim(), secret_key: x.secret_key, host: x.host.trim(), port: +x.port || 22, user: x.user.trim(), password: x.password };
        await api("PUT", "/api/backups/destination", body); toast("Saved"); route();
      }); };
      $("#test", root).onclick = e => busy(e.currentTarget, async () => { const r = await api("POST", "/api/backups/destination/test"); toast(`Works — tested from ${r.server}`); });
      const rm = $("#rm", root); if (rm) rm.onclick = () => busy(null, async () => { if (!await confirmBox("Remove offsite storage", "Existing copies stay where they are, but new backups will no longer be copied offsite.", "Remove", true)) return; await api("DELETE", "/api/backups/destination"); route(); });
    },
  };
}

async function setAlerts() {
  const [n, m] = await Promise.all([api("GET", "/api/notify"), api("GET", "/api/monitor/settings")]);
  const tg = n.telegram, em = n.email, wh = n.webhook;
  const num = (k, l, h) => `<div><label class="l">${l}</label><input name="${k}" type="number" step="any" value="${m[k]}">${h ? `<div class="hint">${h}</div>` : ""}</div>`;
  return {
    html: `<div class="cards"><div class="card pad"><h3>Where alerts go</h3><form id="nf">
        <label class="check" style="padding-top:0"><input type="checkbox" name="tg_on" ${tg.enabled ? "checked" : ""}><div><b>Telegram</b><div class="hint">Create a bot with @BotFather, add it to your team chat, then paste its token and the chat id.</div></div></label>
        <div class="row2"><div><label class="l">Bot token ${tg.has_token ? '<span class="faint">(saved)</span>' : ""}</label><input name="tg_token" type="password" autocomplete="new-password"></div><div><label class="l">Chat id</label><input name="tg_chat" value="${esc(tg.chat_id)}" autocomplete="off"></div></div>
        <label class="check"><input type="checkbox" name="em_on" ${em.enabled ? "checked" : ""}><div><b>Email (SMTP)</b></div></label>
        <div class="row2"><div><label class="l">SMTP host</label><input name="em_host" value="${esc(em.host)}" placeholder="smtp.gmail.com"></div><div><label class="l">Port</label><input name="em_port" type="number" value="${em.port || 587}"></div></div>
        <div class="row2"><div><label class="l">User</label><input name="em_user" value="${esc(em.user)}" autocomplete="off"></div><div><label class="l">Password ${em.has_password ? '<span class="faint">(saved)</span>' : ""}</label><input name="em_pass" type="password" autocomplete="new-password"></div></div>
        <div class="row2"><div><label class="l">From</label><input name="em_from" value="${esc(em.from)}" placeholder="alerts@yourdomain.com"></div><div><label class="l">Send to</label><input name="em_to" value="${esc(em.to)}" placeholder="team@yourdomain.com, …"></div></div>
        <label class="check"><input type="checkbox" name="webhook_on" ${wh.enabled ? "checked" : ""}><div><b>Webhook</b><div class="hint">Any URL that accepts a JSON POST — Slack, Discord, Teams, or a WhatsApp gateway.</div></div></label>
        <label class="l">URL ${wh.has_url ? '<span class="faint">(saved)</span>' : ""}</label><input name="wh_url" type="password" autocomplete="off" placeholder="https://hooks.slack.com/…">
        <div style="display:flex;gap:8px;margin-top:14px"><button class="btn primary" id="nsave">Save</button><button type="button" class="btn" id="ntest">Send test alert</button></div></form></div>
      <div class="card pad"><h3>What counts as a problem</h3><form id="mf">
        <label class="check" style="padding-top:0"><input type="checkbox" name="enabled" ${m.enabled ? "checked" : ""}><div><b>Monitoring on</b><div class="hint">Checks every site each minute and every server every 5 minutes.</div></div></label>
        <div class="row2">${num("down_after", "Failed checks before “down”")}${num("recover_after", "Good checks before “recovered”")}</div>
        <div class="row2">${num("disk_warn", "Disk warning %")}${num("disk_crit", "Disk critical %")}</div>
        <div class="row2">${num("mem_warn", "Memory warning %")}${num("cpu_warn", "CPU load per core")}</div>
        <div class="row2">${num("ssl_warn_days", "HTTPS expiry warning (days)")}${num("ssl_crit_days", "HTTPS expiry critical (days)")}</div>
        ${num("remind_minutes", "Remind about open incidents every (min)")}
        <label class="check"><input type="checkbox" name="autoheal" ${m.autoheal ? "checked" : ""}><div><b>Auto-heal</b><div class="hint">When a site is down but its server is fine, restart that server's services once per incident.</div></div></label>
        <div style="margin-top:10px"><button class="btn primary" id="msave">Save</button></div></form></div></div>`,
    mount(root) {
      $("#nf", root).onsubmit = e => { e.preventDefault(); busy($("#nsave", root), async () => {
        const x = Object.fromEntries(new FormData(e.target));
        await api("PUT", "/api/notify", { telegram: { enabled: !!x.tg_on, token: x.tg_token, chat_id: x.tg_chat.trim() },
          email: { enabled: !!x.em_on, host: x.em_host.trim(), port: +x.em_port || 587, user: x.em_user.trim(), password: x.em_pass, from: x.em_from.trim(), to: x.em_to.trim() },
          webhook: { enabled: !!x.webhook_on, url: x.wh_url } });
        toast("Saved"); route();
      }); };
      $("#ntest", root).onclick = e => busy(e.currentTarget, async () => {
        const r = await api("POST", "/api/notify/test"), bad = Object.entries(r).filter(([, v]) => v !== "ok");
        if (bad.length) toast(bad.map(([k, v]) => `${k}: ${v}`).join(" · "), true); else toast("Test alert sent to " + Object.keys(r).join(", "));
      });
      $("#mf", root).onsubmit = e => { e.preventDefault(); busy($("#msave", root), async () => {
        const x = Object.fromEntries(new FormData(e.target)), b = { enabled: !!x.enabled, autoheal: !!x.autoheal };
        ["down_after", "recover_after", "disk_warn", "disk_crit", "mem_warn", "cpu_warn", "ssl_warn_days", "ssl_crit_days", "remind_minutes"].forEach(k => { b[k] = +x[k]; });
        await api("PUT", "/api/monitor/settings", b); toast("Saved");
      }); };
    },
  };
}

const ROUTES = [
  [/^#\/sites$/, pSites, "sites"], [/^#\/sites\/(\d+)(?:\/(\w+))?$/, pSite, "site"], [/^#\/new-site$/, pNewSite, "newsite"],
  [/^#\/servers$/, pServers, "servers"], [/^#\/servers\/(\d+)(?:\/(\w+))?$/, pServer, "server"],
  [/^#\/customers$/, pCustomers, "customers"], [/^#\/approvals$/, pApprovals, "approvals"], [/^#\/audit$/, pAudit, "audit"],
  [/^#\/monitoring$/, pMonitoring, "monitoring"], [/^#\/backups$/, pBackups, "backups"], [/^#\/apps$/, pApps, "apps"], [/^#\/jobs$/, pJobs, "jobs"], [/^#\/settings(?:\/(\w+))?$/, pSettings, "settings"],
];

showAuth();
