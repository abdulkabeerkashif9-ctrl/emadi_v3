"""Support operations, go-live checklist, customers & notes, team management, audit log, approvals."""
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import db, jobs, ops, security, ssh
from .access import ROLE_HELP, ROLES, audit, need, user

router = APIRouter(prefix="/api")


def _site(sid, allow_creating=False):
    s = db.q1("SELECT s.*, v.name AS server_name, v.ip AS ip, v.gateway AS gateway, v.gateway_url AS gateway_url, v.metrics AS metrics "
              "FROM sites s JOIN servers v ON v.id=s.server_id WHERE s.id=?", (sid,))
    if not s:
        raise HTTPException(404, "Site not found")
    if s["status"] == "creating" and not allow_creating:
        raise HTTPException(409, "The site is still being created")
    return s


def _run(fn, *a):
    try:
        return fn(*a)
    except (ops.OpError, ssh.SSHError) as e:
        raise HTTPException(400, str(e))


# ───────────────────────────── go-live checklist ─────────────────────────────
@router.get("/sites/{sid}/golive")
def golive_get(sid: int, _=Depends(user)):
    s = _site(sid)
    return ops.golive(s, s)


class GoLiveIn(BaseModel):
    provider_done: bool


@router.post("/sites/{sid}/golive")
def golive_set(sid: int, b: GoLiveIn, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    db.x("UPDATE sites SET golive_provider=? WHERE id=?", (int(b.provider_done), sid))
    audit(u, "site_golive_provider", s["domain"], "done" if b.provider_done else "reopened", request)
    return {"provider_done": b.provider_done}


# ───────────────────────────── quick operations ─────────────────────────────
class OnIn(BaseModel):
    on: bool


@router.post("/sites/{sid}/maintenance")
def site_maintenance(sid: int, b: OnIn, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    _run(ops.maintenance, sid, b.on)
    audit(u, "site_maintenance_on" if b.on else "site_maintenance_off", s["domain"], "", request)
    return {"maintenance": b.on}


@router.post("/sites/{sid}/clear-cache")
def site_clear_cache(sid: int, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    _run(ops.clear_cache, sid)
    audit(u, "site_clear_cache", s["domain"], "", request)
    return {}


@router.post("/sites/{sid}/reset-password")
def site_reset_password(sid: int, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    pw = _run(ops.reset_admin_password, sid)
    audit(u, "site_reset_admin_password", s["domain"], "", request)
    return {"password": pw}


@router.post("/servers/{server_id}/restart-services")
def server_restart_services(server_id: int, request: Request, u=Depends(need("support"))):
    srv = db.q1("SELECT name FROM servers WHERE id=?", (server_id,))
    if not srv:
        raise HTTPException(404, "Server not found")
    out = _run(ops.restart_services, server_id)
    audit(u, "server_restart_services", srv["name"], "", request)
    return {"output": out}


class DomainBody(BaseModel):
    domain: str = Field(min_length=4, max_length=253)


@router.post("/sites/{sid}/add-domain")
def site_add_domain(sid: int, b: DomainBody, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    d = _run(ops.add_domain, sid, b.domain)
    audit(u, "site_add_domain", s["domain"], d, request)
    return {"domain": d}


class SuspendIn(BaseModel):
    suspended: bool
    reason: str = ""


@router.post("/sites/{sid}/suspend")
def site_suspend(sid: int, b: SuspendIn, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    if b.suspended and len(b.reason.strip()) < 3:
        raise HTTPException(400, "Please give a short reason")
    _run(ops.maintenance, sid, b.suspended)
    db.x("UPDATE sites SET suspended=? WHERE id=?", (int(b.suspended), sid))
    verb = "Suspended" if b.suspended else "Reactivated"
    db.x("INSERT INTO site_notes(site_id,user,text) VALUES(?,?,?)", (sid, u["username"], f"{verb}" + (f": {b.reason.strip()}" if b.reason.strip() else "")))
    audit(u, "site_suspend" if b.suspended else "site_reactivate", s["domain"], b.reason, request)
    return {"suspended": b.suspended}


# ───────────────────────────── long operations (jobs) ─────────────────────────────
@router.post("/sites/{sid}/backup")
def site_backup(sid: int, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    audit(u, "site_backup", s["domain"], "", request)
    return {"job_id": jobs.start("ops", f"Backup {s['domain']}", lambda log: ops.backup_job(sid, log), u["username"])}


@router.post("/sites/{sid}/migrate")
def site_migrate(sid: int, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    audit(u, "site_migrate", s["domain"], "", request)
    return {"job_id": jobs.start("ops", f"Migrate {s['domain']}", lambda log: ops.migrate_job(sid, log), u["username"])}


@router.post("/sites/{sid}/rename")
def site_rename(sid: int, b: DomainBody, request: Request, u=Depends(need("admin"))):
    s = _site(sid)
    audit(u, "site_rename", s["domain"], b.domain, request)
    return {"job_id": jobs.start("ops", f"Rename {s['domain']} to {b.domain}", lambda log: ops.rename_job(sid, b.domain, log), u["username"])}


# ───────────────────────────── backups & logs ─────────────────────────────
@router.get("/sites/{sid}/backups")
def backups_list(sid: int, _=Depends(need("support"))):
    _site(sid)
    return _run(ops.list_backups, sid)


@router.get("/sites/{sid}/backups/{name}")
def backup_download(sid: int, name: str, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    site, srv = _run(ops.get, sid)
    path = _run(ops.backup_path, site, srv, name)
    runner = ssh.Runner(srv).connect()
    try:
        sftp = runner.client.open_sftp()
        size = sftp.stat(path).st_size
        f = sftp.open(path, "rb")
    except Exception as e:
        runner.close()
        raise HTTPException(404, f"Backup not found: {e}")
    audit(u, "site_backup_download", s["domain"], name, request)

    def stream():
        try:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            runner.close()
    return StreamingResponse(stream(), media_type="application/octet-stream",
                             headers={"Content-Length": str(size), "Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/log-sources")
def log_sources(_=Depends(user)):
    return [{"id": k, "label": v[0]} for k, v in ops.LOGS.items()]


@router.get("/sites/{sid}/logs")
def site_logs(sid: int, source: str = "site", lines: int = 300, q: str = "", _=Depends(need("support"))):
    _site(sid)
    return {"text": _run(ops.read_log, sid, source, lines, q)}


# ───────────────────────────── deletion with approval ─────────────────────────────
class DeleteIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
    confirm: str
    backup_first: bool = True


def _start_drop(sid, domain, backup_first, by):
    return jobs.start("ops", f"Delete site {domain}", lambda log: ops.drop_job(sid, backup_first, log), by)


@router.post("/sites/{sid}/delete")
def site_delete(sid: int, b: DeleteIn, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    if b.confirm.strip().lower() != s["domain"]:
        raise HTTPException(400, "Type the site's domain exactly to confirm")
    if u["role"] == "admin":
        audit(u, "site_delete", s["domain"], b.reason, request)
        return {"job_id": _start_drop(sid, s["domain"], b.backup_first, u["username"]), "pending": False}
    if db.q1("SELECT 1 FROM approvals WHERE site_id=? AND status='pending' AND action='delete_site'", (sid,)):
        raise HTTPException(409, "A deletion request for this site is already waiting for approval")
    aid = db.x("INSERT INTO approvals(action,site_id,site_domain,params,requested_by,reason) VALUES('delete_site',?,?,?,?,?)",
               (sid, s["domain"], json.dumps({"backup_first": b.backup_first}), u["username"], b.reason))
    audit(u, "site_delete_requested", s["domain"], b.reason, request)
    return {"pending": True, "approval_id": aid}


@router.get("/approvals")
def approvals_list(status: str = "", u=Depends(need("support"))):
    sql, args = "SELECT * FROM approvals", []
    cond = []
    if u["role"] != "admin":
        cond.append("requested_by=?"); args.append(u["username"])
    if status:
        cond.append("status=?"); args.append(status)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    return db.q(sql + " ORDER BY id DESC LIMIT 100", tuple(args))


class DecideIn(BaseModel):
    approve: bool


@router.post("/approvals/{aid}/decide")
def approval_decide(aid: int, b: DecideIn, request: Request, u=Depends(need("admin"))):
    a = db.q1("SELECT * FROM approvals WHERE id=?", (aid,))
    if not a or a["status"] != "pending":
        raise HTTPException(404, "No pending request with that id")
    if not b.approve:
        db.x("UPDATE approvals SET status='rejected', decided_by=?, decided_at=datetime('now') WHERE id=?", (u["username"], aid))
        audit(u, "approval_rejected", a["site_domain"], f"request by {a['requested_by']}", request)
        return {"status": "rejected"}
    site = db.q1("SELECT id FROM sites WHERE id=?", (a["site_id"],))
    if not site:
        db.x("UPDATE approvals SET status='rejected', decided_by=?, decided_at=datetime('now') WHERE id=?", (u["username"], aid))
        raise HTTPException(409, "The site no longer exists; the request was closed")
    params = json.loads(a["params"] or "{}")
    by = f"{u['username']} (approved)"
    if a["action"] == "restore_site":
        from . import api_reliability
        job = api_reliability._start_restore(a["site_id"], a["site_domain"], params["group"], params.get("source", "server"), by)
    else:
        job = _start_drop(a["site_id"], a["site_domain"], params.get("backup_first", True), by)
    db.x("UPDATE approvals SET status='approved', decided_by=?, decided_at=datetime('now'), job_id=? WHERE id=?", (u["username"], job, aid))
    audit(u, "approval_approved", a["site_domain"], f"request by {a['requested_by']}", request)
    return {"status": "approved", "job_id": job}


# ───────────────────────────── customers & notes ─────────────────────────────
class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    contact: str = ""
    email: str = ""
    phone: str = ""
    plan: str = ""
    renews_on: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    notes: str = ""


def _customer_out(c):
    days = None
    if c.get("renews_on"):
        try:
            days = (date.fromisoformat(c["renews_on"]) - date.today()).days
        except ValueError:
            days = None
    state = "none" if days is None else "overdue" if days < 0 else "soon" if days <= 14 else "ok"
    return c | {"days_left": days, "renewal": state}


@router.get("/customers")
def customers_list(_=Depends(user)):
    rows = db.q("SELECT c.*, (SELECT COUNT(*) FROM sites s WHERE s.customer_id=c.id) AS sites FROM customers c ORDER BY c.name")
    return [_customer_out(r) for r in rows]


@router.post("/customers")
def customers_create(b: CustomerIn, request: Request, u=Depends(need("support"))):
    cid = db.x("INSERT INTO customers(name,contact,email,phone,plan,renews_on,notes) VALUES(?,?,?,?,?,?,?)",
               (b.name.strip(), b.contact, b.email, b.phone, b.plan, b.renews_on, b.notes))
    audit(u, "customer_add", b.name, "", request)
    return _customer_out(db.q1("SELECT *, 0 AS sites FROM customers WHERE id=?", (cid,)))


@router.put("/customers/{cid}")
def customers_update(cid: int, b: CustomerIn, request: Request, u=Depends(need("support"))):
    if not db.q1("SELECT 1 FROM customers WHERE id=?", (cid,)):
        raise HTTPException(404, "Customer not found")
    db.x("UPDATE customers SET name=?,contact=?,email=?,phone=?,plan=?,renews_on=?,notes=? WHERE id=?",
         (b.name.strip(), b.contact, b.email, b.phone, b.plan, b.renews_on, b.notes, cid))
    audit(u, "customer_edit", b.name, "", request)
    return _customer_out(db.q1("SELECT *, (SELECT COUNT(*) FROM sites s WHERE s.customer_id=customers.id) AS sites FROM customers WHERE id=?", (cid,)))


@router.delete("/customers/{cid}")
def customers_delete(cid: int, request: Request, u=Depends(need("admin"))):
    c = db.q1("SELECT name FROM customers WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "Customer not found")
    db.x("UPDATE sites SET customer_id=NULL WHERE customer_id=?", (cid,))
    db.x("DELETE FROM customers WHERE id=?", (cid,))
    audit(u, "customer_delete", c["name"], "", request)
    return {}


class AssignIn(BaseModel):
    customer_id: int | None = None


@router.put("/sites/{sid}/customer")
def site_assign_customer(sid: int, b: AssignIn, request: Request, u=Depends(need("support"))):
    s = _site(sid, allow_creating=True)
    if b.customer_id is not None and not db.q1("SELECT 1 FROM customers WHERE id=?", (b.customer_id,)):
        raise HTTPException(404, "Customer not found")
    db.x("UPDATE sites SET customer_id=? WHERE id=?", (b.customer_id, sid))
    audit(u, "site_assign_customer", s["domain"], str(b.customer_id), request)
    return {}


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.get("/sites/{sid}/notes")
def notes_list(sid: int, _=Depends(user)):
    _site(sid, allow_creating=True)
    return db.q("SELECT * FROM site_notes WHERE site_id=? ORDER BY id DESC LIMIT 200", (sid,))


@router.post("/sites/{sid}/notes")
def notes_add(sid: int, b: NoteIn, request: Request, u=Depends(need("support"))):
    s = _site(sid, allow_creating=True)
    db.x("INSERT INTO site_notes(site_id,user,text) VALUES(?,?,?)", (sid, u["username"], b.text.strip()))
    audit(u, "site_note", s["domain"], b.text[:100], request)
    return notes_list(sid)


@router.delete("/sites/{sid}/notes/{nid}")
def notes_delete(sid: int, nid: int, request: Request, u=Depends(need("admin"))):
    db.x("DELETE FROM site_notes WHERE id=? AND site_id=?", (nid, sid))
    audit(u, "site_note_delete", str(sid), str(nid), request)
    return {}


# ───────────────────────────── team ─────────────────────────────
class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(pattern="^(viewer|support|admin)$")


class EditUser(BaseModel):
    role: str | None = Field(default=None, pattern="^(viewer|support|admin)$")
    disabled: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


def _other_active_admins(exclude):
    return db.q1("SELECT COUNT(*) n FROM users WHERE role='admin' AND disabled=0 AND username!=?", (exclude,))["n"]


@router.get("/roles")
def roles(_=Depends(user)):
    return [{"id": k, "help": ROLE_HELP[k]} for k in ROLES]


@router.get("/team")
def team_list(_=Depends(need("admin"))):
    return db.q("SELECT username, role, disabled, created FROM users ORDER BY username")


@router.post("/team")
def team_add(b: NewUser, request: Request, u=Depends(need("admin"))):
    if db.q1("SELECT 1 FROM users WHERE username=?", (b.username,)):
        raise HTTPException(409, "That username is taken")
    db.x("INSERT INTO users(username,pw_hash,role) VALUES(?,?,?)", (b.username, security.hash_pw(b.password), b.role))
    audit(u, "user_add", b.username, b.role, request)
    return {}


@router.put("/team/{username}")
def team_edit(username: str, b: EditUser, request: Request, u=Depends(need("admin"))):
    row = db.q1("SELECT * FROM users WHERE username=?", (username,))
    if not row:
        raise HTTPException(404, "No such user")
    losing_admin = row["role"] == "admin" and not row["disabled"] and ((b.role and b.role != "admin") or b.disabled)
    if losing_admin and _other_active_admins(username) == 0:
        raise HTTPException(400, "There must be at least one active administrator")
    if b.role:
        db.x("UPDATE users SET role=? WHERE username=?", (b.role, username))
    if b.disabled is not None:
        db.x("UPDATE users SET disabled=? WHERE username=?", (int(b.disabled), username))
    if b.password:
        db.x("UPDATE users SET pw_hash=? WHERE username=?", (security.hash_pw(b.password), username))
    audit(u, "user_edit", username, ", ".join(k for k, v in (("role→" + (b.role or ""), b.role), ("disabled" if b.disabled else "enabled", b.disabled is not None), ("password reset", b.password)) if v), request)
    return {}


@router.delete("/team/{username}")
def team_delete(username: str, request: Request, u=Depends(need("admin"))):
    row = db.q1("SELECT * FROM users WHERE username=?", (username,))
    if not row:
        raise HTTPException(404, "No such user")
    if username == u["username"]:
        raise HTTPException(400, "You cannot delete your own account")
    if row["role"] == "admin" and not row["disabled"] and _other_active_admins(username) == 0:
        raise HTTPException(400, "There must be at least one active administrator")
    db.x("DELETE FROM users WHERE username=?", (username,))
    audit(u, "user_delete", username, "", request)
    return {}


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=200)


@router.post("/auth/password")
def change_password(b: PasswordIn, request: Request, u=Depends(user)):
    row = db.q1("SELECT pw_hash FROM users WHERE username=?", (u["username"],))
    if not security.check_pw(b.current, row["pw_hash"]):
        raise HTTPException(400, "Current password is wrong")
    db.x("UPDATE users SET pw_hash=? WHERE username=?", (security.hash_pw(b.new), u["username"]))
    audit(u, "password_change", u["username"], "", request)
    return {}


# ───────────────────────────── audit log ─────────────────────────────
@router.get("/audit")
def audit_list(q: str = "", user_filter: str = Query("", alias="user"), limit: int = 100, offset: int = 0, _=Depends(need("admin"))):
    sql, args, cond = "SELECT * FROM audit", [], []
    if q.strip():
        cond.append("(action LIKE ? OR target LIKE ? OR detail LIKE ?)"); args += [f"%{q.strip()}%"] * 3
    if user_filter.strip():
        cond.append("user=?"); args.append(user_filter.strip())
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    rows = db.q(sql + " ORDER BY id DESC LIMIT ? OFFSET ?", tuple(args) + (max(1, min(limit, 500)), max(0, offset)))
    return rows
