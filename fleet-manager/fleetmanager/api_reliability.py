"""API for backups (policies, offsite, restore, move) and monitoring (uptime, incidents, alerts)."""
import json
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import backups, db, jobs, monitor, notify, ops, ssh
from .access import audit, need, user

router = APIRouter(prefix="/api")


def _run(fn, *a):
    try:
        return fn(*a)
    except (ops.OpError, ssh.SSHError, ValueError) as e:
        raise HTTPException(400, str(e))


def _site(sid):
    s = db.q1("SELECT s.*, v.name AS server_name FROM sites s JOIN servers v ON v.id=s.server_id WHERE s.id=?", (sid,))
    if not s:
        raise HTTPException(404, "Site not found")
    return s


# ───────────────────────────── backups ─────────────────────────────
@router.get("/backups")
def backups_overview(_=Depends(need("support"))):
    return backups.overview()


class PolicyIn(BaseModel):
    enabled: bool = True
    frequency: str = "daily"
    hour: int = 2
    weekday: int = 0
    interval_hours: int = 24
    keep: int = 7
    offsite: bool = False
    keep_offsite: int = 14


@router.put("/backups/policy")
def policy_default(b: PolicyIn, request: Request, u=Depends(need("admin"))):
    out = _run(backups.save_policy, None, b.model_dump())
    audit(u, "backup_policy_default", "all sites", json.dumps(b.model_dump())[:200], request)
    return out


@router.get("/sites/{sid}/backup-policy")
def policy_get(sid: int, _=Depends(need("support"))):
    _site(sid)
    return backups.get_policy(sid)


@router.put("/sites/{sid}/backup-policy")
def policy_site(sid: int, b: PolicyIn, request: Request, u=Depends(need("admin"))):
    s = _site(sid)
    out = _run(backups.save_policy, sid, b.model_dump())
    audit(u, "backup_policy_site", s["domain"], json.dumps(b.model_dump())[:200], request)
    return out


@router.delete("/sites/{sid}/backup-policy")
def policy_site_clear(sid: int, request: Request, u=Depends(need("admin"))):
    s = _site(sid)
    backups.clear_policy(sid)
    audit(u, "backup_policy_inherit", s["domain"], "", request)
    return backups.get_policy(sid)


@router.get("/sites/{sid}/backup-runs")
def runs(sid: int, _=Depends(need("support"))):
    _site(sid)
    return backups.runs_for(sid, 30)


class DestIn(BaseModel):
    type: str = Field(pattern="^(s3|sftp)$")
    path: str
    provider: str = "Other"
    endpoint: str = ""
    region: str = ""
    access_key: str = ""
    secret_key: str = ""
    host: str = ""
    port: int = 22
    user: str = ""
    password: str = ""


@router.get("/backups/destination")
def dest_get(_=Depends(need("admin"))):
    return backups.dest_masked()


@router.put("/backups/destination")
def dest_put(b: DestIn, request: Request, u=Depends(need("admin"))):
    out = _run(backups.dest_save, b.model_dump())
    audit(u, "offsite_destination", b.type, b.path, request)
    return out


@router.delete("/backups/destination")
def dest_delete(request: Request, u=Depends(need("admin"))):
    backups.dest_clear()
    audit(u, "offsite_destination_removed", "", "", request)
    return {}


@router.post("/backups/destination/test")
def dest_test(request: Request, u=Depends(need("admin"))):
    """Uploads and deletes a tiny file using the first ready server, proving credentials and path work end to end."""
    srv = db.q1("SELECT * FROM servers WHERE status='ready' ORDER BY id LIMIT 1")
    if not srv:
        raise HTTPException(409, "You need a ready server to test the destination from")

    def go():
        with ssh.Runner(srv) as r, backups.rclone_session(r, srv) as (conf, d):
            q = backups.shlex.quote
            probe = q("fm:" + d["path"] + "/.fleet-test")
            code, out = r.run(f"echo ok | rclone --config {q(conf)} rcat {probe} && rclone --config {q(conf)} deletefile {probe}",
                              as_user=backups.BENCH_USER, stream=False, timeout=180)
            if code != 0:
                raise ops.OpError(f"The destination refused the test file: {out.strip()[-300:]}")
        return {"ok": True, "server": srv["name"]}
    out = _run(go)
    audit(u, "offsite_destination_test", srv["name"], "", request)
    return out


@router.get("/sites/{sid}/offsite")
def offsite(sid: int, _=Depends(need("support"))):
    _site(sid)
    return _run(backups.offsite_files, sid)


class RestoreIn(BaseModel):
    group: str = Field(pattern=r"^\d{8}_\d{6}$")
    source: str = Field(default="server", pattern="^(server|offsite)$")
    reason: str = Field(min_length=3, max_length=300)
    confirm: str


def _start_restore(sid, domain, group, source, by):
    return jobs.start("ops", f"Restore {domain} from {group}", lambda log: backups.restore_job(sid, group, source, log), by)


@router.post("/sites/{sid}/restore")
def site_restore(sid: int, b: RestoreIn, request: Request, u=Depends(need("support"))):
    s = _site(sid)
    if b.confirm.strip().lower() != s["domain"]:
        raise HTTPException(400, "Type the site's domain exactly to confirm")
    detail = f"{b.group} from {b.source}: {b.reason}"
    if u["role"] == "admin":
        audit(u, "site_restore", s["domain"], detail, request)
        return {"pending": False, "job_id": _start_restore(sid, s["domain"], b.group, b.source, u["username"])}
    if db.q1("SELECT 1 FROM approvals WHERE site_id=? AND status='pending' AND action='restore_site'", (sid,)):
        raise HTTPException(409, "A restore request for this site is already waiting for approval")
    aid = db.x("INSERT INTO approvals(action,site_id,site_domain,params,requested_by,reason) VALUES('restore_site',?,?,?,?,?)",
               (sid, s["domain"], json.dumps({"group": b.group, "source": b.source}), u["username"], b.reason))
    audit(u, "site_restore_requested", s["domain"], detail, request)
    return {"pending": True, "approval_id": aid}


class MoveIn(BaseModel):
    server_id: int
    confirm: str


@router.post("/sites/{sid}/move")
def site_move(sid: int, b: MoveIn, request: Request, u=Depends(need("admin"))):
    s = _site(sid)
    if b.confirm.strip().lower() != s["domain"]:
        raise HTTPException(400, "Type the site's domain exactly to confirm")
    tgt = db.q1("SELECT * FROM servers WHERE id=? AND status='ready'", (b.server_id,))
    if not tgt or tgt["id"] == s["server_id"]:
        raise HTTPException(400, "Choose a different, ready server")
    audit(u, "site_move", s["domain"], f"{s['server_name']} → {tgt['name']}", request)
    return {"job_id": jobs.start("ops", f"Move {s['domain']} to {tgt['name']}", lambda log: backups.move_job(sid, tgt["id"], log), u["username"])}


# ───────────────────────────── monitoring ─────────────────────────────
@router.get("/monitor/summary")
def mon_summary(_=Depends(user)):
    return monitor.summary()


@router.get("/incidents")
def incidents(status: str = "open", limit: int = 100, _=Depends(user)):
    sql, args = "SELECT * FROM incidents", ()
    if status in ("open", "resolved"):
        sql += " WHERE status=?"; args = (status,)
    order = "ORDER BY CASE severity WHEN 'crit' THEN 0 ELSE 1 END, id DESC" if status == "open" else "ORDER BY id DESC"
    return db.q(f"{sql} {order} LIMIT ?", args + (max(1, min(limit, 300)),))


@router.post("/incidents/{iid}/ack")
def incident_ack(iid: int, request: Request, u=Depends(need("support"))):
    monitor.ack_incident(iid, u["username"])
    audit(u, "incident_ack", str(iid), "", request)
    return {}


@router.post("/incidents/{iid}/close")
def incident_close(iid: int, request: Request, u=Depends(need("support"))):
    if not monitor.close_incident(iid, u["username"]):
        raise HTTPException(404, "No open incident with that id")
    audit(u, "incident_close", str(iid), "", request)
    return {}


@router.get("/sites/{sid}/uptime")
def site_uptime(sid: int, _=Depends(user)):
    s = _site(sid)
    return {"uptime24": monitor.uptime(sid, 24), "uptime7": monitor.uptime(sid, 24 * 7), "uptime30": monitor.uptime(sid, 24 * 30),
            "bars": monitor.bars(sid), "ssl_expires": s["ssl_expires"],
            "incidents": db.q("SELECT * FROM incidents WHERE target_type='site' AND target_id=? ORDER BY id DESC LIMIT 10", (sid,))}


@router.get("/monitor/settings")
def mon_settings(_=Depends(need("admin"))):
    return monitor.settings()


@router.put("/monitor/settings")
def mon_settings_put(b: dict, request: Request, u=Depends(need("admin"))):
    out = _run(monitor.save_settings, b)
    audit(u, "monitor_settings", "", json.dumps({k: b[k] for k in b if k in monitor.DEFAULTS})[:200], request)
    return out


@router.post("/monitor/run")
def mon_run(u=Depends(need("support"))):
    n = monitor.run_site_checks()
    threading.Thread(target=monitor.run_server_checks, daemon=True).start()
    return {"sites_checked": n}


@router.get("/notify")
def notify_get(_=Depends(need("admin"))):
    return notify.masked()


@router.put("/notify")
def notify_put(b: dict, request: Request, u=Depends(need("admin"))):
    try:
        notify.save(b)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"Invalid setting: {e}")
    audit(u, "notify_settings", "", ", ".join(ch for ch, c in notify.get_config().items() if c["enabled"]), request)
    return notify.masked()


@router.post("/notify/test")
def notify_test(request: Request, u=Depends(need("admin"))):
    res = notify.send("✅ Fleet Manager test alert", "If you can read this, alerts are working.", "info")
    audit(u, "notify_test", "", json.dumps(res)[:200], request)
    if not res:
        raise HTTPException(400, "No alert channel is enabled. Enable and save one first.")
    return res
