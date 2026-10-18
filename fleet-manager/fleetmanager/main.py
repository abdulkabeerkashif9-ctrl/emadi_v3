import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, cpanel, db, domains, jobs, provision, security, ssh

STATIC = Path(__file__).parent / "static"
_fails = {}  # ip -> (count, first_ts) for login throttling


def _health_loop():
    while True:
        time.sleep(300)
        for s in db.q("SELECT id FROM servers WHERE status='ready'"):
            try:
                provision.refresh_server(s["id"])
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app):
    db.init()
    ssh.manager_public_key()
    if not os.environ.get("FLEET_NO_BACKGROUND"):
        threading.Thread(target=_health_loop, daemon=True).start()
    yield


app = FastAPI(title="ERP Fleet Manager", lifespan=lifespan)


# ------------------------------------------------------------------ auth
def user(request: Request):
    u = security.read_token(request.cookies.get("fm_session", ""))
    if not u or not db.q1("SELECT 1 FROM users WHERE username=?", (u,)):
        raise HTTPException(401, "Not logged in")
    return u


class Creds(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=200)


def _login(resp: Response, request: Request, username):
    resp.set_cookie("fm_session", security.make_token(username), httponly=True, samesite="strict",
                    secure=request.url.scheme == "https", max_age=config.SESSION_HOURS * 3600)


@app.get("/api/auth/state")
def auth_state(request: Request):
    u = security.read_token(request.cookies.get("fm_session", ""))
    return {"setup_needed": db.q1("SELECT COUNT(*) n FROM users")["n"] == 0, "user": u}


@app.post("/api/auth/setup")
def auth_setup(c: Creds, request: Request, resp: Response):
    if db.q1("SELECT COUNT(*) n FROM users")["n"]:
        raise HTTPException(403, "Already set up")
    db.x("INSERT INTO users(username,pw_hash) VALUES(?,?)", (c.username, security.hash_pw(c.password)))
    _login(resp, request, c.username)
    return {"user": c.username}


@app.post("/api/auth/login")
def auth_login(c: Creds, request: Request, resp: Response):
    key = request.client.host if request.client else "?"
    n, ts = _fails.get(key, (0, time.time()))
    if time.time() - ts > 600:
        n, ts = 0, time.time()
    if n >= 8:
        raise HTTPException(429, "Too many attempts, try again in a few minutes")
    row = db.q1("SELECT * FROM users WHERE username=?", (c.username,))
    if not row or not security.check_pw(c.password, row["pw_hash"]):
        _fails[key] = (n + 1, ts)
        raise HTTPException(401, "Wrong username or password")
    _fails.pop(key, None)
    _login(resp, request, c.username)
    return {"user": c.username}


@app.post("/api/auth/logout")
def auth_logout(resp: Response):
    resp.delete_cookie("fm_session")
    return {}


# ------------------------------------------------------------------ servers
class ServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    ip: str = Field(min_length=3, max_length=255)
    ssh_port: int = 22
    ssh_user: str = "root"
    auth_type: str = Field(pattern="^(password|key)$")
    secret: str = ""          # password or private key; blank on edit = keep
    version: str = config.DEFAULT_VERSION


def _server_out(s):
    cap = provision.server_capacity(s) if s["status"] == "ready" else None
    apps = [r["app_name"] for r in db.q("SELECT app_name FROM server_apps WHERE server_id=? ORDER BY 1", (s["id"],))]
    n = db.q1("SELECT COUNT(*) n FROM sites WHERE server_id=?", (s["id"],))["n"]
    return {k: s[k] for k in ("id", "name", "ip", "ssh_port", "ssh_user", "auth_type", "version", "status",
                              "os_info", "metrics_at", "last_error", "host_fingerprint")} | {
        "capacity": cap, "apps": apps, "site_count": n}


def _get_server(sid):
    s = db.q1("SELECT * FROM servers WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404, "Server not found")
    return s


def _validate_server(b: ServerIn):
    if b.version not in config.VERSIONS:
        raise HTTPException(400, "Unknown ERPNext version")
    if not (1 <= b.ssh_port <= 65535):
        raise HTTPException(400, "Bad SSH port")


@app.get("/api/versions")
def versions(_=Depends(user)):
    return {"default": config.DEFAULT_VERSION, "items": [{"id": k, "label": v["label"]} for k, v in config.VERSIONS.items()]}


@app.get("/api/servers")
def servers(_=Depends(user)):
    return [_server_out(s) for s in db.q("SELECT * FROM servers ORDER BY id")]


@app.post("/api/servers")
def server_create(b: ServerIn, _=Depends(user)):
    _validate_server(b)
    if not b.secret:
        raise HTTPException(400, "Password or private key required")
    sid = db.x("INSERT INTO servers(name,ip,ssh_port,ssh_user,auth_type,secret_enc,version) VALUES(?,?,?,?,?,?,?)",
               (b.name, b.ip.strip(), b.ssh_port, b.ssh_user.strip(), b.auth_type, security.encrypt(b.secret), b.version))
    return _server_out(_get_server(sid))


@app.put("/api/servers/{sid}")
def server_update(sid: int, b: ServerIn, _=Depends(user)):
    old = _get_server(sid)
    _validate_server(b)
    if old["status"] in ("ready", "configuring") and b.version != old["version"]:
        raise HTTPException(400, "Cannot change ERPNext version of a configured server")
    secret = security.encrypt(b.secret) if b.secret else old["secret_enc"]
    fp = old["host_fingerprint"] if b.ip.strip() == old["ip"] else None  # new IP => new host key
    db.x("UPDATE servers SET name=?,ip=?,ssh_port=?,ssh_user=?,auth_type=?,secret_enc=?,version=?,host_fingerprint=? WHERE id=?",
         (b.name, b.ip.strip(), b.ssh_port, b.ssh_user.strip(), b.auth_type, secret, b.version, fp, sid))
    return _server_out(_get_server(sid))


@app.delete("/api/servers/{sid}")
def server_delete(sid: int, _=Depends(user)):
    s = _get_server(sid)
    if s["status"] == "configuring":
        raise HTTPException(409, "Server is being configured")
    db.x("DELETE FROM sites WHERE server_id=?", (sid,))
    db.x("DELETE FROM server_apps WHERE server_id=?", (sid,))
    db.x("DELETE FROM servers WHERE id=?", (sid,))
    return {}  # only forgets it here; the VPS itself is untouched


@app.get("/api/servers/{sid}/bootstrap.sh", response_class=PlainTextResponse)
def server_bootstrap(sid: int, _=Depends(user)):
    return PlainTextResponse(provision.bootstrap_script(_get_server(sid)),
                             headers={"Content-Disposition": "attachment; filename=bootstrap.sh"})


@app.post("/api/servers/{sid}/test")
def server_test(sid: int, _=Depends(user)):
    s = _get_server(sid)
    try:
        with ssh.Runner(s) as r:
            code, out = r.run(". /etc/os-release; echo $PRETTY_NAME; id -un; "
                              "(sudo -n true 2>/dev/null && echo SUDO_OK || echo SUDO_NO)", stream=False)
        lines = out.strip().splitlines()
        sudo_ok = s["ssh_user"] == "root" or "SUDO_OK" in lines or s["auth_type"] == "password"
        if s["status"] == "new":
            db.x("UPDATE servers SET status='bootstrapped' WHERE id=?", (sid,))
        return {"ok": True, "os": lines[0] if lines else "", "sudo": sudo_ok,
                "fingerprint": _get_server(sid)["host_fingerprint"]}
    except ssh.SSHError as e:
        raise HTTPException(400, str(e))


@app.post("/api/servers/{sid}/configure")
def server_configure(sid: int, _=Depends(user)):
    s = _get_server(sid)
    if s["status"] == "configuring":
        raise HTTPException(409, "Already configuring")
    if s["status"] == "ready":
        raise HTTPException(409, "Already configured. Use Refresh.")
    db.x("UPDATE servers SET status='configuring' WHERE id=?", (sid,))
    return {"job_id": jobs.start("configure", f"Configure server {s['name']}", lambda log: provision.configure_server(sid, log))}


@app.post("/api/servers/{sid}/refresh")
def server_refresh(sid: int, _=Depends(user)):
    s = _get_server(sid)
    if s["status"] not in ("ready", "error", "bootstrapped"):
        raise HTTPException(409, "Server is not configured yet")
    try:
        provision.refresh_server(sid)
    except ssh.SSHError as e:
        raise HTTPException(400, str(e))
    return _server_out(_get_server(sid))


class AppNames(BaseModel):
    apps: list[str]


@app.post("/api/servers/{sid}/install-apps")
def server_install_apps(sid: int, b: AppNames, _=Depends(user)):
    s = _get_server(sid)
    if s["status"] != "ready":
        raise HTTPException(409, "Server is not ready")
    try:
        names = provision.order_apps(b.apps)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"job_id": jobs.start("apps", f"Install apps on {s['name']}: {', '.join(names)}",
                                 lambda log: provision.install_apps_on_server(sid, names, log))}


# ------------------------------------------------------------------ apps registry
class AppIn(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,60}$")   # python module name of the app
    title: str = ""
    git_url: str = Field(min_length=8)
    branch: str | None = None
    requires: str = ""


def _check_git_url(u):
    if not (u.startswith("https://") or u.startswith("git@") or u.startswith("ssh://")) or any(c in u for c in " ;|&$`'\"\n"):
        raise HTTPException(400, "Git URL must be https://..., git@... or ssh://... with no spaces/special characters")


@app.get("/api/apps")
def apps_list(_=Depends(user)):
    return db.q("SELECT a.*, (SELECT COUNT(*) FROM server_apps sa WHERE sa.app_name=a.name) AS servers FROM apps a ORDER BY builtin DESC, name")


@app.post("/api/apps")
def apps_create(b: AppIn, _=Depends(user)):
    _check_git_url(b.git_url)
    if db.q1("SELECT 1 FROM apps WHERE name=?", (b.name,)):
        raise HTTPException(409, "App already exists")
    if b.branch and any(c in b.branch for c in " ;|&$`'\"\n"):
        raise HTTPException(400, "Bad branch name")
    db.x("INSERT INTO apps(name,title,git_url,branch,requires) VALUES(?,?,?,?,?)",
         (b.name, b.title or b.name, b.git_url.strip(), (b.branch or None), b.requires.replace(" ", "")))
    return db.q1("SELECT * FROM apps WHERE name=?", (b.name,))


@app.put("/api/apps/{name}")
def apps_update(name: str, b: AppIn, _=Depends(user)):
    _check_git_url(b.git_url)
    if not db.q1("SELECT 1 FROM apps WHERE name=?", (name,)):
        raise HTTPException(404, "No such app")
    if b.branch and any(c in b.branch for c in " ;|&$`'\"\n"):
        raise HTTPException(400, "Bad branch name")
    db.x("UPDATE apps SET title=?, git_url=?, branch=?, requires=? WHERE name=?",
         (b.title or name, b.git_url.strip(), b.branch or None, b.requires.replace(" ", ""), name))
    return db.q1("SELECT * FROM apps WHERE name=?", (name,))


@app.delete("/api/apps/{name}")
def apps_delete(name: str, _=Depends(user)):
    a = db.q1("SELECT * FROM apps WHERE name=?", (name,))
    if not a:
        raise HTTPException(404, "No such app")
    if a["builtin"]:
        raise HTTPException(400, "Built-in apps cannot be removed")
    db.x("DELETE FROM apps WHERE name=?", (name,))
    return {}


# ------------------------------------------------------------------ sites
def _site_out(r):
    return {k: r[k] for k in ("id", "domain", "company", "apps", "status", "http_code", "checked_at", "ssl",
                              "server_id", "server_name", "ip", "created")}


@app.get("/api/sites")
def sites(_=Depends(user)):
    return [_site_out(r) for r in db.q(
        "SELECT s.*, v.name AS server_name, v.ip AS ip FROM sites s JOIN servers v ON v.id=s.server_id ORDER BY s.domain")]


@app.post("/api/sites/health")
def sites_health(_=Depends(user)):
    for s in db.q("SELECT id FROM servers WHERE status='ready'"):
        provision.check_sites(s["id"])
    return sites()


@app.get("/api/sites/{sid}/credentials")
def site_credentials(sid: int, _=Depends(user)):
    r = db.q1("SELECT * FROM sites WHERE id=?", (sid,))
    if not r:
        raise HTTPException(404)
    return {"username": "Administrator", "password": security.decrypt(r["admin_pw_enc"]) if r["admin_pw_enc"] else None}


@app.delete("/api/sites/{sid}")
def site_forget(sid: int, _=Depends(user)):
    db.x("DELETE FROM sites WHERE id=?", (sid,))
    return {}  # forgets the record only; the site stays on the VPS


class DomainIn(BaseModel):
    domain: str


@app.post("/api/domain/check")
def domain_check(b: DomainIn, _=Depends(user)):
    return domains.check(b.domain)


@app.get("/api/recommend")
def recommend(_=Depends(user)):
    return provision.recommend()


class PrecheckIn(BaseModel):
    server_id: int
    apps: list[str]


@app.post("/api/sites/precheck")
def site_precheck(b: PrecheckIn, _=Depends(user)):
    _get_server(b.server_id)
    try:
        order = provision.order_apps(b.apps)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"install_order": order, "missing_on_server": provision.missing_on_server(b.server_id, b.apps)}


class SiteIn(BaseModel):
    domain: str
    company: str = ""
    server_id: int
    apps: list[str] = ["erpnext"]
    install_missing: bool = False
    add_dns: bool = False
    enable_ssl: bool = False


@app.post("/api/sites")
def site_create(b: SiteIn, _=Depends(user)):
    s = _get_server(b.server_id)
    if s["status"] != "ready":
        raise HTTPException(409, "Server is not ready")
    chk = domains.check(b.domain)
    if not chk["ok"]:
        raise HTTPException(400, "; ".join(chk["problems"]))
    if b.add_dns and not chk["zone"]:
        raise HTTPException(400, "Domain is not in the connected cPanel account, cannot create DNS record")
    try:
        order = provision.order_apps(b.apps)
    except ValueError as e:
        raise HTTPException(400, str(e))
    missing = provision.missing_on_server(b.server_id, b.apps)
    if missing and not b.install_missing:
        raise HTTPException(409, {"missing_on_server": missing})
    pw = security.gen_password()
    sid = db.x("INSERT INTO sites(server_id,domain,company,apps,admin_pw_enc,status) VALUES(?,?,?,?,?,'creating')",
               (b.server_id, chk["domain"], b.company.strip(), ",".join(order), security.encrypt(pw)))
    job = jobs.start("site", f"Create site {chk['domain']} on {s['name']}",
                     lambda log: provision.create_site(sid, log, b.install_missing, b.add_dns, b.enable_ssl))
    return {"site_id": sid, "job_id": job}


# ------------------------------------------------------------------ jobs
@app.get("/api/jobs")
def jobs_list(_=Depends(user)):
    return db.q("SELECT id,kind,title,status,created,finished FROM jobs ORDER BY id DESC LIMIT 50")


@app.get("/api/jobs/{jid}")
def job_get(jid: int, offset: int = 0, _=Depends(user)):
    j = db.q1("SELECT * FROM jobs WHERE id=?", (jid,))
    if not j:
        raise HTTPException(404)
    log = j.pop("log")
    return j | {"log": log[offset:], "next_offset": len(log)}


# ------------------------------------------------------------------ settings
class CPanelIn(BaseModel):
    host: str
    port: int = 2083
    user: str
    token: str = ""
    verify_tls: bool = True


@app.get("/api/settings/cpanel")
def cpanel_get(_=Depends(user)):
    c = cpanel.get_settings()
    return {"configured": bool(c), "host": c and c["host"], "port": c and c["port"], "user": c and c["user"],
            "verify_tls": c["verify_tls"] if c else True, "has_token": bool(c and c["token"])}


@app.put("/api/settings/cpanel")
def cpanel_put(b: CPanelIn, _=Depends(user)):
    cpanel.save_settings(b.host.strip(), b.port, b.user.strip(), b.token.strip(), b.verify_tls)
    return cpanel_get()


@app.post("/api/settings/cpanel/test")
def cpanel_test(_=Depends(user)):
    try:
        cpanel.test()
        return {"ok": True, "domains": cpanel.managed_domains()}
    except cpanel.CPanelError as e:
        raise HTTPException(400, str(e))


@app.get("/api/manager-key")
def manager_key(_=Depends(user)):
    return {"public_key": ssh.manager_public_key()}


# ------------------------------------------------------------------ UI
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
