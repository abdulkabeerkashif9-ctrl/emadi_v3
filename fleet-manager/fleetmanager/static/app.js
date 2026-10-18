"use strict";
const $app = document.getElementById("app");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const S = { user: null, page: "sites", servers: [], apps: [], sites: [], versions: null };

async function api(method, url, body) {
  const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  let data = null; try { data = await r.json(); } catch { /* text */ }
  if (r.status === 401 && S.user) { S.user = null; render(); }
  if (!r.ok) {
    const d = data && data.detail;
    const e = new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : "Request failed (" + r.status + ")");
    e.status = r.status; e.detail = d; throw e;
  }
  return data;
}
function toast(msg, err) {
  const t = document.getElementById("toast"), d = document.createElement("div");
  d.textContent = msg; if (err) d.className = "err"; t.appendChild(d); setTimeout(() => d.remove(), err ? 6000 : 3000);
}
const guard = fn => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message, true); } };
const $ = (sel, root = document) => root.querySelector(sel);

function modal(html, onMount) {
  const bg = document.createElement("div"); bg.className = "modalbg";
  bg.innerHTML = `<div class="modal">${html}</div>`;
  document.body.appendChild(bg);
  bg.close = () => bg.remove();
  bg.addEventListener("mousedown", e => { if (e.target === bg && !bg.dataset.lock) bg.close(); });
  onMount && onMount(bg);
  return bg;
}
const pill = (t, cls) => `<span class="pill ${cls || ""}">${esc(t)}</span>`;
const statusPill = s => pill(s, { up: "ok", ready: "ok", done: "ok", down: "bad", error: "bad", failed: "bad", creating: "warn", configuring: "warn", running: "warn" }[s]);
const meter = (label, pct) => `<div class="muted" style="font-size:12px;margin-top:6px">${label} <b>${pct}%</b></div><div class="meter ${pct > 90 ? "hi" : pct > 70 ? "mid" : ""}"><i style="width:${Math.min(pct, 100)}%"></i></div>`;

// ------------------------------------------------------------------ data
async function loadAll() {
  [S.servers, S.apps, S.sites] = await Promise.all([api("GET", "/api/servers"), api("GET", "/api/apps"), api("GET", "/api/sites")]);
  S.versions = S.versions || await api("GET", "/api/versions");
}

// ------------------------------------------------------------------ shell
async function render() {
  if (!S.user) return renderLogin();
  const nav = [["sites", "Sites"], ["servers", "Servers"], ["apps", "Apps"], ["jobs", "Jobs"], ["settings", "Settings"]];
  $app.innerHTML = `<header><h1>ERP Fleet Manager</h1>${nav.map(([k, l]) => `<a data-p="${k}" class="${S.page === k ? "on" : ""}">${l}</a>`).join("")}
    <span class="sp"></span><span class="muted">${esc(S.user)}</span><a id="logout">Log out</a></header><main id="main">Loading…</main>`;
  $app.querySelectorAll("[data-p]").forEach(a => a.onclick = () => { S.page = a.dataset.p; render(); });
  $("#logout").onclick = guard(async () => { await api("POST", "/api/auth/logout"); S.user = null; render(); });
  try { await loadAll(); await ({ sites: pageSites, servers: pageServers, apps: pageApps, jobs: pageJobs, settings: pageSettings }[S.page])($("#main")); }
  catch (e) { if (S.user) $("#main").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
}

async function renderLogin() {
  const st = await api("GET", "/api/auth/state");
  if (st.user) { S.user = st.user; return render(); }
  $app.innerHTML = `<div class="login card"><h2 style="margin-top:0">ERP Fleet Manager</h2>
    <p class="muted">${st.setup_needed ? "First run: create the administrator account." : "Sign in to continue."}</p>
    <form id="f"><label>Username</label><input name="username" autocomplete="username" required minlength="3">
    <label>Password ${st.setup_needed ? '<span class="hint">(min 8 characters)</span>' : ""}</label><input name="password" type="password" autocomplete="current-password" required minlength="8">
    <div style="margin-top:16px"><button style="width:100%">${st.setup_needed ? "Create account" : "Sign in"}</button></div></form></div>`;
  $("#f").onsubmit = guard(async e => {
    e.preventDefault(); const fd = Object.fromEntries(new FormData(e.target));
    const r = await api("POST", st.setup_needed ? "/api/auth/setup" : "/api/auth/login", fd);
    S.user = r.user; render();
  });
}

// ------------------------------------------------------------------ sites
async function pageSites(m) {
  const ready = S.servers.filter(s => s.status === "ready").length;
  m.innerHTML = `<div class="bar"><h2>Sites</h2><button class="ghost" id="chk">Check health</button><button id="new" ${ready ? "" : "disabled title='Add and configure a server first'"}>+ New site</button></div>
  <div class="card tablewrap">${S.sites.length ? `<table><tr><th>Status</th><th>Domain</th><th>Company</th><th>Server IP</th><th>Server</th><th>Apps</th><th></th></tr>
  ${S.sites.map(s => `<tr><td>${statusPill(s.status)}${s.http_code ? ` <span class="muted mono">${s.http_code}</span>` : ""}</td>
   <td><a href="${s.ssl ? "https" : "http"}://${esc(s.domain)}" target="_blank" rel="noopener"><b>${esc(s.domain)}</b></a></td>
   <td>${esc(s.company) || '<span class="muted">—</span>'}</td><td class="mono">${esc(s.ip)}</td><td>${esc(s.server_name)}</td>
   <td class="muted">${esc((s.apps || "").split(",").filter(Boolean).join(", "))}</td>
   <td style="white-space:nowrap"><button class="ghost sm" data-cred="${s.id}">Login</button> <button class="ghost sm" data-del="${s.id}" title="Forget (does not delete from server)">✕</button></td></tr>`).join("")}</table>`
    : `<div class="empty">No sites yet.${ready ? " Click <b>New site</b>." : " Add a server on the <b>Servers</b> page, then configure it."}</div>`}</div>`;
  $("#chk").onclick = guard(async () => { toast("Checking…"); S.sites = await api("POST", "/api/sites/health"); render(); });
  $("#new").onclick = () => newSiteWizard();
  m.querySelectorAll("[data-cred]").forEach(b => b.onclick = guard(async () => {
    const c = await api("GET", `/api/sites/${b.dataset.cred}/credentials`);
    modal(`<h3>Site login</h3><p>User: <b class="mono">${esc(c.username)}</b></p><p>Password: <b class="mono">${esc(c.password || "(unknown - site was imported)")}</b></p><div class="actions"><button class="ghost" id="x">Close</button></div>`, bg => $("#x", bg).onclick = bg.close);
  }));
  m.querySelectorAll("[data-del]").forEach(b => b.onclick = guard(async () => {
    if (!confirm("Remove this site from Fleet Manager?\nThe site itself stays on the server.")) return;
    await api("DELETE", `/api/sites/${b.dataset.del}`); render();
  }));
}

function newSiteWizard() {
  const W = { step: 1, domain: "", company: "", check: null, rec: [], server: null, apps: new Set(["erpnext"]), dns: false, ssl: false, missing: [] };
  const bg = modal("", null);
  const body = bg.firstChild;
  const draw = () => {
    if (W.step === 1) {
      body.innerHTML = `<h3>New site — 1/3 Domain</h3><label>Domain</label><input id="dom" placeholder="client.thesmarterp.com" value="${esc(W.domain)}">
      <label>Company name <span class="hint">(shown in the dashboard)</span></label><input id="co" value="${esc(W.company)}">
      <div id="res"></div><div class="actions"><button class="ghost" id="cancel">Cancel</button><button id="check">Check domain</button><button id="next" ${W.check?.ok ? "" : "disabled"}>Next</button></div>`;
      if (W.check) showCheck();
      $("#cancel", body).onclick = bg.close;
      $("#check", body).onclick = guard(async () => {
        W.domain = $("#dom", body).value; W.company = $("#co", body).value;
        $("#res", body).innerHTML = '<div class="note">Checking…</div>';
        W.check = await api("POST", "/api/domain/check", { domain: W.domain }); W.domain = W.check.domain; showCheck();
        $("#next", body).disabled = !W.check.ok;
      });
      $("#next", body).onclick = guard(async () => { W.company = $("#co", body).value; W.rec = await api("GET", "/api/recommend"); W.server = (W.rec.find(r => r.recommended) || W.rec.find(r => r.ok) || W.rec[0] || {}).id; W.step = 2; draw(); });
    } else if (W.step === 2) {
      body.innerHTML = `<h3>New site — 2/3 Server</h3><p class="muted">Servers ranked by free capacity. The recommendation is the least loaded one; you can pick any.</p>
      ${W.rec.length ? W.rec.map(r => `<label class="srvopt ${r.id === W.server ? "sel" : ""} ${r.ok ? "" : "dis"}" style="font-weight:400"><input type="radio" name="srv" value="${r.id}" ${r.id === W.server ? "checked" : ""}>
        <div style="flex:1"><b>${esc(r.name)}</b> <span class="mono muted">${esc(r.ip)}</span> ${r.recommended ? pill("Recommended", "ok") : ""} ${r.ok ? "" : pill("Busy", "warn")}
        <div class="muted" style="font-size:12.5px">${r.known ? `${r.sites} sites · load ${r.metrics.load}/${r.metrics.cores} cores · RAM ${r.metrics.mem_pct}% · disk ${r.metrics.disk_pct}%` : esc(r.reasons.join(", "))}${r.reasons.length && r.known ? " — " + esc(r.reasons.join(", ")) : ""}</div></div></label>`).join("")
        : '<div class="note warn">No configured servers available.</div>'}
      <div class="actions"><button class="ghost" id="back">Back</button><button id="next" ${W.server ? "" : "disabled"}>Next</button></div>`;
      body.querySelectorAll("[name=srv]").forEach(i => i.onchange = () => { W.server = +i.value; draw(); });
      $("#back", body).onclick = () => { W.step = 1; draw(); };
      $("#next", body).onclick = () => { W.step = 3; draw(); };
    } else if (W.step === 3) {
      const srv = S.servers.find(s => s.id === W.server);
      body.innerHTML = `<h3>New site — 3/3 Applications</h3><div class="apps">${S.apps.map(a => `<label><input type="checkbox" value="${esc(a.name)}" ${W.apps.has(a.name) ? "checked" : ""}> <span>${esc(a.title || a.name)}${srv.apps.includes(a.name) ? ' <span class="pill ok">on server</span>' : ""}</span></label>`).join("")}</div>
      <label style="font-weight:500"><input type="checkbox" id="dns" style="width:auto" ${W.dns ? "checked" : ""} ${W.check.zone ? "" : "disabled"}> Create DNS A record → ${esc(srv.ip)} in cPanel ${W.check.zone ? `<span class="hint">(zone ${esc(W.check.zone)})</span>` : '<span class="hint">(domain not in cPanel)</span>'}</label>
      <label style="font-weight:500"><input type="checkbox" id="ssl" style="width:auto" ${W.ssl ? "checked" : ""}> Request free HTTPS certificate <span class="hint">(only works once DNS points to the server)</span></label>
      <div id="miss"></div><div class="actions"><button class="ghost" id="back">Back</button><button id="go">Create site</button></div>`;
      $("#back", body).onclick = () => { collect(); W.step = 2; draw(); };
      $("#go", body).onclick = guard(async () => {
        collect(); if (!W.apps.size) return toast("Select at least one app", true);
        const pre = await api("POST", "/api/sites/precheck", { server_id: W.server, apps: [...W.apps] });
        if (pre.missing_on_server.length && !W.confirmInstall) {
          const names = pre.missing_on_server.map(n => S.apps.find(a => a.name === n)?.title || n);
          $("#miss", body).innerHTML = `<div class="note warn"><b>Not installed on this server:</b> ${esc(names.join(", "))}.<br>Do you want to install ${names.length > 1 ? "them" : "it"} on the server too? (downloads from git and builds — can take several minutes)
            <div style="margin-top:8px"><button id="yes">Yes, install and create site</button> <button class="ghost" id="no">No, change selection</button></div></div>`;
          $("#yes", body).onclick = () => { W.confirmInstall = true; $("#go", body).click(); };
          $("#no", body).onclick = () => $("#miss", body).innerHTML = "";
          return;
        }
        const r = await api("POST", "/api/sites", { domain: W.domain, company: W.company, server_id: W.server, apps: [...W.apps], install_missing: !!W.confirmInstall, add_dns: W.dns, enable_ssl: W.ssl });
        bg.close(); watchJob(r.job_id, "Creating " + W.domain, () => { S.page = "sites"; render(); });
      });
    }
  };
  const collect = () => { W.apps = new Set([...body.querySelectorAll(".apps input:checked")].map(i => i.value)); W.dns = $("#dns", body).checked; W.ssl = $("#ssl", body).checked; };
  const showCheck = () => {
    const c = W.check;
    $("#res", body).innerHTML = c.problems.map(p => `<div class="note bad">✖ ${esc(p)}</div>`).join("") + c.notes.map(n => `<div class="note">ℹ ${esc(n)}</div>`).join("") + (c.ok ? '<div class="note ok">✔ Domain can be used</div>' : "");
  };
  draw();
}

// ------------------------------------------------------------------ job viewer
function watchJob(id, title, onDone) {
  let off = 0, stop = false;
  const bg = modal(`<h3>${esc(title)} <span id="st"></span></h3><div class="log" id="log"></div><div class="actions"><button class="ghost" id="close">Run in background</button></div>`);
  bg.dataset.lock = "1";
  const log = $("#log", bg);
  $("#close", bg).onclick = () => { stop = true; bg.close(); onDone && onDone(); };
  (async function poll() {
    if (stop) return;
    try {
      const j = await api("GET", `/api/jobs/${id}?offset=${off}`);
      if (j.log) { const atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 30; log.textContent += j.log; if (atEnd) log.scrollTop = log.scrollHeight; }
      off = j.next_offset; $("#st", bg).innerHTML = statusPill(j.status);
      if (j.status !== "running") { $("#close", bg).textContent = "Close"; $("#close", bg).onclick = () => { bg.close(); onDone && onDone(); }; return; }
    } catch (e) { if (e.status === 401) return; }
    setTimeout(poll, 1500);
  })();
}

// ------------------------------------------------------------------ servers
async function pageServers(m) {
  m.innerHTML = `<div class="bar"><h2>Servers (VPS)</h2><button id="add">+ Add VPS</button></div>
  <div class="grid">${S.servers.map(s => {
    const c = s.capacity, mt = c && c.metrics;
    return `<div class="card"><div style="display:flex;justify-content:space-between"><div><b>${esc(s.name)}</b><div class="mono muted">${esc(s.ssh_user)}@${esc(s.ip)}:${s.ssh_port}</div></div>${statusPill(s.status)}</div>
    <div class="muted" style="margin-top:6px">ERPNext ${esc(s.version.replace("version-", "v"))} · ${s.site_count} site(s)${s.os_info ? " · " + esc(s.os_info) : ""}</div>
    ${mt ? meter("CPU load " + mt.load + " / " + mt.cores + " cores", Math.round(100 * mt.load / mt.cores)) + meter("RAM", mt.mem_pct) + meter("Disk", mt.disk_pct) : ""}
    ${s.apps.length ? `<div class="muted" style="margin-top:8px;font-size:12.5px">Apps: ${esc(s.apps.join(", "))}</div>` : ""}
    ${s.last_error ? `<div class="note bad">${esc(s.last_error)}</div>` : ""}
    <div style="margin-top:12px;display:flex;gap:6px;flex-wrap:wrap">
      ${s.status === "new" || s.status === "bootstrapped" || s.status === "error" ? `<button class="ghost sm" data-a="boot" data-id="${s.id}">1 · Bootstrap file</button><button class="ghost sm" data-a="test" data-id="${s.id}">Test SSH</button><button class="sm" data-a="conf" data-id="${s.id}">2 · Configure server</button>` : ""}
      ${s.status === "ready" ? `<button class="ghost sm" data-a="ref" data-id="${s.id}">Refresh</button><button class="ghost sm" data-a="apps" data-id="${s.id}">Install apps</button>` : ""}
      ${s.status === "configuring" ? `<button class="sm" data-a="jobs" data-id="${s.id}">View progress</button>` : ""}
      <button class="ghost sm" data-a="edit" data-id="${s.id}">Edit</button><button class="ghost sm" data-a="del" data-id="${s.id}">Remove</button></div></div>`;
  }).join("") || '<div class="card empty" style="grid-column:1/-1">No servers yet. Click <b>Add VPS</b>.</div>'}</div>`;
  $("#add").onclick = () => serverForm();
  m.querySelectorAll("[data-a]").forEach(b => b.onclick = guard(async () => {
    const id = +b.dataset.id, s = S.servers.find(x => x.id === id);
    ({
      boot: () => bootstrapDialog(s), edit: () => serverForm(s),
      test: async () => { b.disabled = true; const r = await api("POST", `/api/servers/${id}/test`); toast(`SSH OK — ${r.os}${r.sudo ? "" : " (user has no passwordless sudo!)"}`); render(); },
      conf: async () => { if (!confirm(`Configure ${s.name}? This installs MariaDB, Redis, Nginx, Node, bench and ERPNext ${s.version} on ${s.ip}. Takes 15-30 minutes.`)) return; const r = await api("POST", `/api/servers/${id}/configure`); watchJob(r.job_id, "Configuring " + s.name, render); },
      jobs: () => { S.page = "jobs"; render(); },
      ref: async () => { b.disabled = true; await api("POST", `/api/servers/${id}/refresh`); toast("Refreshed"); render(); },
      apps: () => installAppsDialog(s),
      del: async () => { if (confirm(`Remove ${s.name} and its ${s.site_count} site record(s) from Fleet Manager?\nNothing is deleted on the VPS.`)) { await api("DELETE", `/api/servers/${id}`); render(); } },
    })[b.dataset.a]();
  }));
}

function serverForm(s) {
  const v = S.versions;
  const bg = modal(`<h3>${s ? "Edit" : "Add"} VPS</h3><form id="f">
   <div class="row"><div><label>Name</label><input name="name" required value="${esc(s?.name)}" placeholder="vps-01"></div><div><label>IP address</label><input name="ip" required value="${esc(s?.ip)}"></div></div>
   <div class="row"><div><label>SSH user</label><input name="ssh_user" value="${esc(s?.ssh_user || "root")}"></div><div><label>SSH port</label><input name="ssh_port" type="number" value="${s?.ssh_port || 22}"></div></div>
   <div class="row"><div><label>Login with</label><select name="auth_type"><option value="password" ${s?.auth_type === "password" ? "selected" : ""}>Password</option><option value="key" ${s?.auth_type === "key" ? "selected" : ""}>Private key</option></select></div>
   <div><label>ERPNext version</label><select name="version" ${s && (s.status === "ready" || s.status === "configuring") ? "disabled" : ""}>${v.items.map(i => `<option value="${i.id}" ${(s?.version || v.default) === i.id ? "selected" : ""}>${i.label}</option>`).join("")}</select></div></div>
   <label>Password / private key <span class="hint">${s ? "(leave blank to keep current)" : "(stored encrypted; paste the full key incl. BEGIN/END lines; passphrase-protected keys unsupported)"}</span></label>
   <textarea name="secret" autocomplete="off"></textarea>
   <div class="actions"><button type="button" class="ghost" id="cancel">Cancel</button><button>Save</button></div></form>`);
  $("#cancel", bg).onclick = bg.close;
  const ta = $("[name=secret]", bg), sel = $("[name=auth_type]", bg);
  const sync = () => { ta.style.minHeight = sel.value === "key" ? "160px" : "40px"; ta.style.webkitTextSecurity = sel.value === "key" ? "none" : "disc"; ta.rows = sel.value === "key" ? 8 : 1; };
  sel.onchange = sync; sync();
  $("#f", bg).onsubmit = guard(async e => {
    e.preventDefault(); const d = Object.fromEntries(new FormData(e.target)); d.ssh_port = +d.ssh_port;
    if (s && !d.version) d.version = s.version;
    await api(s ? "PUT" : "POST", s ? `/api/servers/${s.id}` : "/api/servers", d); bg.close(); render();
  });
}

async function bootstrapDialog(s) {
  const script = await (await fetch(`/api/servers/${s.id}/bootstrap.sh`)).text();
  const bg = modal(`<h3>Bootstrap ${esc(s.name)}</h3><p>Run this <b>once</b> on the new VPS as root. It installs SSH/sudo prerequisites and authorises Fleet Manager's key.</p>
   <ol><li>SSH into the VPS (<span class="mono">${esc(s.ssh_user)}@${esc(s.ip)}</span>)</li><li>Save the script below as <span class="mono">bootstrap.sh</span> (or <a href="/api/servers/${s.id}/bootstrap.sh" download>download it</a> and upload)</li><li>Run <span class="mono">sudo bash bootstrap.sh</span></li><li>Come back here, press <b>Test SSH</b>, then <b>Configure server</b></li></ol>
   <textarea readonly style="min-height:220px" id="sc">${esc(script)}</textarea><div class="actions"><button class="ghost" id="copy">Copy</button><button id="x">Close</button></div>`);
  $("#x", bg).onclick = bg.close;
  $("#copy", bg).onclick = () => { $("#sc", bg).select(); navigator.clipboard?.writeText(script); toast("Copied"); };
}

function installAppsDialog(s) {
  const bg = modal(`<h3>Install apps on ${esc(s.name)}</h3><p class="muted">Apps are downloaded into the server's bench (not installed on any site).</p>
   <div class="apps">${S.apps.filter(a => !s.apps.includes(a.name)).map(a => `<label><input type="checkbox" value="${esc(a.name)}"> ${esc(a.title || a.name)}</label>`).join("") || '<span class="muted">Everything is already installed.</span>'}</div>
   <div class="actions"><button class="ghost" id="x">Cancel</button><button id="go">Install</button></div>`);
  $("#x", bg).onclick = bg.close;
  $("#go", bg).onclick = guard(async () => {
    const apps = [...bg.querySelectorAll("input:checked")].map(i => i.value); if (!apps.length) return;
    const r = await api("POST", `/api/servers/${s.id}/install-apps`, { apps }); bg.close(); watchJob(r.job_id, "Installing apps on " + s.name, render);
  });
}

// ------------------------------------------------------------------ apps
async function pageApps(m) {
  m.innerHTML = `<div class="bar"><h2>Applications</h2><button id="add">+ New app</button></div>
  <div class="card tablewrap"><table><tr><th>App</th><th>Git repository</th><th>Branch</th><th>Requires</th><th>On servers</th><th></th></tr>
  ${S.apps.map(a => `<tr><td><b>${esc(a.title || a.name)}</b><div class="mono muted">${esc(a.name)}</div></td><td class="mono">${esc(a.git_url)}</td>
   <td class="mono">${a.branch ? esc(a.branch) : '<span class="muted">server version</span>'}</td><td class="mono">${esc(a.requires) || "—"}</td><td>${a.servers}</td>
   <td style="white-space:nowrap"><button class="ghost sm" data-e="${esc(a.name)}">Edit</button> ${a.builtin ? "" : `<button class="ghost sm" data-d="${esc(a.name)}">✕</button>`}</td></tr>`).join("")}</table></div>
  <p class="muted">Branch “server version” means the app is fetched on the same branch as the server's ERPNext version (e.g. version-15). Verify branches exist upstream for the version you use.</p>`;
  $("#add").onclick = () => appForm();
  m.querySelectorAll("[data-e]").forEach(b => b.onclick = () => appForm(S.apps.find(a => a.name === b.dataset.e)));
  m.querySelectorAll("[data-d]").forEach(b => b.onclick = guard(async () => { if (confirm("Remove this app from the registry?")) { await api("DELETE", `/api/apps/${b.dataset.d}`); render(); } }));
}
function appForm(a) {
  const bg = modal(`<h3>${a ? "Edit" : "New"} app</h3><form id="f">
   <label>Git repository URL</label><input name="git_url" required placeholder="https://github.com/you/your_app" value="${esc(a?.git_url)}">
   <div class="row"><div><label>App name <span class="hint">(python module, e.g. my_app)</span></label><input name="name" required pattern="[a-z][a-z0-9_]+" value="${esc(a?.name)}" ${a ? "readonly" : ""}></div><div><label>Display title</label><input name="title" value="${esc(a?.title)}"></div></div>
   <div class="row"><div><label>Branch <span class="hint">(blank = server's version branch)</span></label><input name="branch" value="${esc(a?.branch)}" placeholder="main"></div><div><label>Requires <span class="hint">(comma separated)</span></label><input name="requires" value="${esc(a?.requires)}" placeholder="erpnext"></div></div>
   <div class="note">Private repos: use an https URL with a deploy token, or add the server's SSH key as a deploy key and use git@… URL.</div>
   <div class="actions"><button type="button" class="ghost" id="cancel">Cancel</button><button>Save</button></div></form>`);
  $("#cancel", bg).onclick = bg.close;
  $("[name=git_url]", bg).onblur = e => { const n = $("[name=name]", bg); if (!a && !n.value) { const g = e.target.value.replace(/\.git$/, "").split("/").pop() || ""; n.value = g.toLowerCase().replace(/[^a-z0-9_]/g, "_"); } };
  $("#f", bg).onsubmit = guard(async e => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.target)); d.branch = d.branch || null; await api(a ? "PUT" : "POST", a ? `/api/apps/${a.name}` : "/api/apps", d); bg.close(); render(); });
}

// ------------------------------------------------------------------ jobs
async function pageJobs(m) {
  const js = await api("GET", "/api/jobs");
  m.innerHTML = `<div class="bar"><h2>Jobs</h2></div><div class="card tablewrap">${js.length ? `<table><tr><th>#</th><th>Task</th><th>Status</th><th>Started</th><th></th></tr>${js.map(j => `<tr><td>${j.id}</td><td>${esc(j.title)}</td><td>${statusPill(j.status)}</td><td class="muted">${esc(j.created)} UTC</td><td><button class="ghost sm" data-j="${j.id}" data-t="${esc(j.title)}">Log</button></td></tr>`).join("")}</table>` : '<div class="empty">No jobs yet.</div>'}</div>`;
  m.querySelectorAll("[data-j]").forEach(b => b.onclick = () => watchJob(+b.dataset.j, b.dataset.t, render));
}

// ------------------------------------------------------------------ settings
async function pageSettings(m) {
  const c = await api("GET", "/api/settings/cpanel"), k = await api("GET", "/api/manager-key");
  m.innerHTML = `<div class="bar"><h2>Settings</h2></div>
  <div class="card"><h3 style="margin-top:0">cPanel (thesmarterp.com)</h3><p class="muted">Used to check domains and create DNS records. Create an API token in cPanel → Security → Manage API Tokens.</p>
   <form id="f"><div class="row"><div><label>cPanel host</label><input name="host" required value="${esc(c.host)}" placeholder="thesmarterp.com or server hostname"></div><div><label>Port</label><input name="port" type="number" value="${c.port || 2083}"></div></div>
   <div class="row"><div><label>cPanel username</label><input name="user" required value="${esc(c.user)}"></div><div><label>API token ${c.has_token ? '<span class="hint">(saved — leave blank to keep)</span>' : ""}</label><input name="token" type="password" autocomplete="off"></div></div>
   <label style="font-weight:500"><input type="checkbox" name="verify_tls" style="width:auto" ${c.verify_tls ? "checked" : ""}> Verify TLS certificate</label>
   <div style="margin-top:14px;display:flex;gap:8px"><button>Save</button><button type="button" class="ghost" id="test" ${c.configured ? "" : "disabled"}>Test connection</button></div></form></div>
  <div class="card"><h3 style="margin-top:0">Fleet Manager SSH key</h3><p class="muted">The bootstrap script authorises this public key on each VPS.</p><textarea readonly style="min-height:70px">${esc(k.public_key)}</textarea></div>`;
  $("#f").onsubmit = guard(async e => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.target)); d.port = +d.port; d.verify_tls = !!d.verify_tls; await api("PUT", "/api/settings/cpanel", d); toast("Saved"); render(); });
  $("#test").onclick = guard(async () => { const r = await api("POST", "/api/settings/cpanel/test"); toast("Connected. Domains: " + r.domains.join(", ")); });
}

render();
