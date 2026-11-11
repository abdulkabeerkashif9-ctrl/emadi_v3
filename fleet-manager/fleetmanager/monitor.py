"""Uptime checks, server health, incidents and alerts."""
import json
import re
import shlex
import socket
import ssl
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from . import access, db, notify, provision, ssh

DEFAULTS = {
    "enabled": True, "down_after": 3, "recover_after": 2, "sustain": 3,
    "disk_warn": 85, "disk_crit": 92, "mem_warn": 92, "cpu_warn": 2.0,
    "ssl_warn_days": 14, "ssl_crit_days": 5, "remind_minutes": 60, "autoheal": False,
}
LIMITS = {"down_after": (1, 30), "recover_after": (1, 30), "sustain": (1, 30), "disk_warn": (50, 99), "disk_crit": (50, 100),
          "mem_warn": (50, 100), "cpu_warn": (0.5, 20), "ssl_warn_days": (1, 90), "ssl_crit_days": (1, 60), "remind_minutes": (5, 1440)}
SYSTEM = {"username": "system", "role": "system"}
DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,250}$")


def settings():
    raw = db.setting("monitor")
    return {**DEFAULTS, **(json.loads(raw) if raw else {})}


def save_settings(new):
    cur = settings()
    for k, d in DEFAULTS.items():
        if k not in new:
            continue
        v = new[k]
        if isinstance(d, bool):
            cur[k] = bool(v)
        else:
            lo, hi = LIMITS[k]
            v = float(v) if isinstance(d, float) else int(v)
            if not lo <= v <= hi:
                raise ValueError(f"{k} must be between {lo} and {hi}")
            cur[k] = v
    if cur["disk_crit"] < cur["disk_warn"]:
        raise ValueError("disk_crit must not be lower than disk_warn")
    db.set_setting("monitor", json.dumps(cur))
    return cur


# ───────────────────────────── incidents ─────────────────────────────
def _minutes_since(ts):
    if not ts:
        return 10 ** 9
    t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 60


def _alert(inc, event):
    icon = {"open": "🔴" if inc["severity"] == "crit" else "🟠", "escalated": "🔴", "reminder": "⏰", "recovered": "🟢"}[event]
    head = {"recovered": "Recovered: ", "reminder": "Still open: "}.get(event, "")
    title = f"{icon} {head}{inc['title']} — {inc['target_name']}"
    body = (inc["detail"] or "") + ("\n" if inc["detail"] else "") + "Open Fleet Manager → Monitoring for details."
    notify.send(title, body, "ok" if event == "recovered" else inc["severity"])
    db.x("UPDATE incidents SET last_notified=? WHERE id=?", (db.now(), inc["id"]))


def open_incident(kind, ttype, tid, tname, title, detail="", severity="warn"):
    """Open (or refresh) the single open incident for this problem. Alerts on open, escalation and every remind_minutes."""
    row = db.q1("SELECT * FROM incidents WHERE kind=? AND target_type=? AND target_id=? AND status='open'", (kind, ttype, tid))
    if not row:
        iid = db.x("INSERT INTO incidents(kind,target_type,target_id,target_name,title,detail,severity,opened_at) VALUES(?,?,?,?,?,?,?,?)",
                   (kind, ttype, tid, tname, title, detail[:1500], severity, db.now()))
        _alert(db.q1("SELECT * FROM incidents WHERE id=?", (iid,)), "open")
        return iid, True
    notes = [l for l in (row["detail"] or "").split("\n")[1:] if l.startswith("Auto-heal")]   # keep what the system did
    merged = "\n".join([detail.split("\n")[0] or (row["detail"] or "").split("\n")[0]] + notes)[:1500]
    db.x("UPDATE incidents SET title=?, detail=?, severity=? WHERE id=?", (title, merged, severity, row["id"]))
    row = db.q1("SELECT * FROM incidents WHERE id=?", (row["id"],))
    if not row["acked_by"] and _minutes_since(row["last_notified"]) >= settings()["remind_minutes"]:
        _alert(row, "reminder")
    return row["id"], False


def resolve_incident(kind, ttype, tid, by="auto"):
    row = db.q1("SELECT * FROM incidents WHERE kind=? AND target_type=? AND target_id=? AND status='open'", (kind, ttype, tid))
    if not row:
        return False
    db.x("UPDATE incidents SET status='resolved', resolved_at=?, resolved_by=? WHERE id=?", (db.now(), by, row["id"]))
    if by == "auto":
        _alert(db.q1("SELECT * FROM incidents WHERE id=?", (row["id"],)), "recovered")
    return True


def _set_severity(kind, ttype, tid, severity):
    row = db.q1("SELECT * FROM incidents WHERE kind=? AND target_type=? AND target_id=? AND status='open'", (kind, ttype, tid))
    if row and row["severity"] != severity:
        db.x("UPDATE incidents SET severity=? WHERE id=?", (severity, row["id"]))
        if severity == "crit":
            _alert(db.q1("SELECT * FROM incidents WHERE id=?", (row["id"],)), "escalated")


def open_with_escalation(kind, ttype, tid, tname, title, detail, severity):
    before = db.q1("SELECT severity FROM incidents WHERE kind=? AND target_type=? AND target_id=? AND status='open'", (kind, ttype, tid))
    if before and before["severity"] != severity:
        _set_severity(kind, ttype, tid, severity)
    return open_incident(kind, ttype, tid, tname, title, detail, severity)


def ack_incident(iid, user):
    db.x("UPDATE incidents SET acked_by=?, acked_at=? WHERE id=? AND status='open'", (user, db.now(), iid))


def close_incident(iid, user):
    row = db.q1("SELECT * FROM incidents WHERE id=? AND status='open'", (iid,))
    if row:
        db.x("UPDATE incidents SET status='resolved', resolved_at=?, resolved_by=? WHERE id=?", (db.now(), user, iid))
    return bool(row)


# ───────────────────────────── site checks ─────────────────────────────
def _http_ping(domain):
    """(ok, ms, status code) of ERPNext's public ping endpoint, as a visitor would reach it."""
    t = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            r = requests.get(f"http://{domain}/api/method/ping", timeout=8, verify=False, allow_redirects=True)
            return r.status_code == 200 and "pong" in r.text, int((time.time() - t) * 1000), r.status_code
        except requests.RequestException:
            return False, int((time.time() - t) * 1000), 0


def record_check(site_id, kind, ok, ms=0, code=0):
    db.x("INSERT INTO checks(site_id,ts,kind,ok,ms,code) VALUES(?,?,?,?,?,?)", (site_id, db.now(), kind, int(bool(ok)), ms, code))


def run_site_checks():
    sites = db.q("SELECT s.* FROM sites s JOIN servers v ON v.id=s.server_id WHERE v.status='ready' AND s.status IN ('up','down','error')")
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(lambda s: (s, _http_ping(s["domain"])), sites))
    for s, (ok, ms, code) in results:
        record_check(s["id"], "public", ok, ms, code)
        db.x("UPDATE sites SET status=?, http_code=?, checked_at=?, public_ok=?, public_at=? WHERE id=?",
             ("up" if ok else "down", code or None, db.now(), int(ok), db.now(), s["id"]))
        evaluate_site(s["id"])
    return len(results)


def evaluate_site(site_id):
    s = db.q1("SELECT * FROM sites WHERE id=?", (site_id,))
    if not s or s["suspended"]:
        return
    cfg = settings()
    n = max(cfg["down_after"], cfg["recover_after"])
    recent = [r["ok"] for r in db.q("SELECT ok FROM checks WHERE site_id=? AND kind='public' ORDER BY id DESC LIMIT ?", (site_id, n))]
    ever_up = bool(db.q1("SELECT 1 FROM checks WHERE site_id=? AND kind='public' AND ok=1 LIMIT 1", (site_id,)))
    if len(recent) >= cfg["down_after"] and not any(recent[:cfg["down_after"]]) and ever_up:
        origin = db.q1("SELECT ok FROM checks WHERE site_id=? AND kind='origin' ORDER BY id DESC LIMIT 1", (site_id,))
        if origin and origin["ok"]:
            title, detail = "Not reachable from the internet", "ERPNext answers on the server itself, so check DNS, the provider gateway or the firewall."
        elif origin:
            title, detail = "Site is down", "ERPNext does not answer on the server. Check the Logs tab or restart the server services."
        else:
            title, detail = "Site is not answering", "No answer from the public address."
        open_incident("site_down", "site", site_id, s["domain"], title, detail, "crit")
    elif len(recent) >= cfg["recover_after"] and all(recent[:cfg["recover_after"]]):
        resolve_incident("site_down", "site", site_id)


# ───────────────────────────── server checks ─────────────────────────────
def _probe_cmd(domains):
    checks = "".join(f"curl -s -m 8 -H {shlex.quote('Host: ' + d)} http://127.0.0.1/api/method/ping | grep -q pong && echo ORIGIN {shlex.quote(d)} ok || echo ORIGIN {shlex.quote(d)} fail; " for d in domains)
    return ("for u in nginx mariadb redis-server supervisor; do echo SVC $u $(systemctl is-active $u 2>&1 | head -1); done; "
            "supervisorctl status 2>/dev/null | awk '{print \"SUP\",$1,$2}'; "
            "for p in 11000 13000; do (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null && echo PORT $p up || echo PORT $p down; done; " + checks)


def _server_probe(srv, domains):
    """One SSH session: metrics + services + per-site origin check. Returns (metrics dict, parsed probe dict)."""
    with ssh.Runner(srv) as r:
        m = provision.collect_metrics(r)
        code, out = r.run(_probe_cmd(domains), sudo=True, stream=False, timeout=120)
    p = {"svc": {}, "sup": {}, "port": {}, "origin": {}}
    for line in out.splitlines():
        t = line.split()
        if len(t) == 3 and t[0] == "SVC":
            p["svc"][t[1]] = t[2]
        elif len(t) == 3 and t[0] == "SUP":
            p["sup"][t[1]] = t[2]
        elif len(t) == 3 and t[0] == "PORT":
            p["port"][t[1]] = t[2]
        elif len(t) == 3 and t[0] == "ORIGIN":
            p["origin"][t[1]] = t[2] == "ok"
    return m, p


def _autoheal(srv, problems):
    cmds = []
    for svc in problems.get("svc", []):
        cmds.append(f"systemctl restart {shlex.quote(svc)}")
    if problems.get("sup") or problems.get("port"):
        cmds.append("supervisorctl restart all")
    if not cmds:
        return ""
    with ssh.Runner(srv) as r:
        r.run("; ".join(cmds), sudo=True, stream=False, timeout=180)
    access.audit(SYSTEM, "auto_heal", srv["name"], "; ".join(cmds))
    return "Auto-heal ran: " + "; ".join(cmds)


def run_server_checks(server_id=None):
    cfg = settings()
    servers = db.q("SELECT * FROM servers WHERE status='ready'" + (" AND id=?" if server_id else ""), (server_id,) if server_id else ())
    for srv in servers:
        domains = [s["domain"] for s in db.q("SELECT domain FROM sites WHERE server_id=? AND status!='creating'", (srv["id"],)) if DOMAIN_RE.match(s["domain"])]
        try:
            m, p = _server_probe(srv, domains)
        except Exception as e:
            db.x("INSERT INTO server_samples(server_id,ts,ok) VALUES(?,?,0)", (srv["id"], db.now()))
            last = [r["ok"] for r in db.q("SELECT ok FROM server_samples WHERE server_id=? ORDER BY id DESC LIMIT 2", (srv["id"],))]
            if len(last) >= 2 and not any(last):
                open_incident("server_down", "server", srv["id"], srv["name"], "Server not reachable", f"SSH failed: {str(e)[:300]}", "crit")
            continue
        resolve_incident("server_down", "server", srv["id"])
        load = (m.get("load") or 0)
        db.x("INSERT INTO server_samples(server_id,ts,load,mem_pct,disk_pct,ok) VALUES(?,?,?,?,?,1)", (srv["id"], db.now(), load / max(m.get("cores", 1), 1), m.get("mem_pct"), m.get("disk_pct")))
        db.x("UPDATE servers SET metrics=?, metrics_at=?, os_info=COALESCE(?, os_info) WHERE id=?", (json.dumps(m), db.now(), m.get("os"), srv["id"]))
        _evaluate_server(srv, m, p, cfg)
        for d, ok in p["origin"].items():
            row = db.q1("SELECT id FROM sites WHERE server_id=? AND domain=?", (srv["id"], d))
            if row:
                record_check(row["id"], "origin", ok)


def _evaluate_server(srv, m, p, cfg):
    sid, name = srv["id"], srv["name"]
    disk = m.get("disk_pct") or 0
    if disk >= cfg["disk_warn"]:
        open_with_escalation("disk", "server", sid, name, "Disk almost full", f"Root disk is {disk}% used. Free space or enlarge the disk.", "crit" if disk >= cfg["disk_crit"] else "warn")
    elif disk < cfg["disk_warn"] - 2:
        resolve_incident("disk", "server", sid)
    n = cfg["sustain"]
    samples = db.q("SELECT load, mem_pct FROM server_samples WHERE server_id=? AND ok=1 ORDER BY id DESC LIMIT ?", (sid, n))
    if len(samples) >= n and all((x["mem_pct"] or 0) >= cfg["mem_warn"] for x in samples):
        open_incident("memory", "server", sid, name, "Memory is nearly exhausted", f"RAM use has stayed above {cfg['mem_warn']}% (now {m.get('mem_pct')}%). Sites may become slow or crash.", "warn")
    elif samples and (samples[0]["mem_pct"] or 0) < cfg["mem_warn"] - 3:
        resolve_incident("memory", "server", sid)
    if len(samples) >= n and all((x["load"] or 0) >= cfg["cpu_warn"] for x in samples):
        open_incident("cpu", "server", sid, name, "CPU is overloaded", f"Load per core has stayed above {cfg['cpu_warn']} (now {samples[0]['load']:.1f}).", "warn")
    elif samples and (samples[0]["load"] or 0) < cfg["cpu_warn"] * 0.8:
        resolve_incident("cpu", "server", sid)
    bad = {"svc": [k for k, v in p["svc"].items() if v != "active"], "sup": [k for k, v in p["sup"].items() if v != "RUNNING"],
           "port": [k for k, v in p["port"].items() if v != "up"]}
    if any(bad.values()):
        parts = ([f"{', '.join(bad['svc'])} not running"] if bad["svc"] else []) + ([f"supervisor programs not running: {', '.join(bad['sup'])}"] if bad["sup"] else []) + ([f"bench redis port(s) closed: {', '.join(bad['port'])}"] if bad["port"] else [])
        iid, created = open_incident("service", "server", sid, name, "A required service is not running", "; ".join(parts), "crit")
        row = db.q1("SELECT detail FROM incidents WHERE id=?", (iid,))
        if cfg["autoheal"] and "Auto-heal" not in (row["detail"] or ""):
            try:
                note = _autoheal(srv, bad)
            except Exception as e:
                note = f"Auto-heal failed: {str(e)[:150]}"
            db.x("UPDATE incidents SET detail=detail||? WHERE id=?", (f"\n{note}", iid))
    else:
        resolve_incident("service", "server", sid)


# ───────────────────────────── SSL expiry ─────────────────────────────
def _cert_days(domain):
    """Days until the certificate on domain:443 expires. None = no HTTPS; raises ssl.SSLError when invalid."""
    try:
        with socket.create_connection((domain, 443), timeout=6) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=domain) as s:
                return (ssl.cert_time_to_seconds(s.getpeercert()["notAfter"]) - time.time()) / 86400
    except ssl.SSLCertVerificationError:
        raise
    except OSError:
        return None


def run_ssl_checks():
    cfg = settings()
    for s in db.q("SELECT * FROM sites WHERE status IN ('up','down')"):
        try:
            days = _cert_days(s["domain"])
        except ssl.SSLError as e:
            open_incident("ssl", "site", s["id"], s["domain"], "HTTPS certificate problem", str(getattr(e, "verify_message", e))[:200], "crit")
            continue
        if days is None:
            continue
        exp = time.strftime("%Y-%m-%d", time.gmtime(time.time() + days * 86400))
        db.x("UPDATE sites SET ssl_expires=? WHERE id=?", (exp, s["id"]))
        if days <= cfg["ssl_warn_days"]:
            open_with_escalation("ssl", "site", s["id"], s["domain"], "HTTPS certificate expires soon", f"Expires on {exp} ({max(0, int(days))} days left).", "crit" if days <= cfg["ssl_crit_days"] else "warn")
        else:
            resolve_incident("ssl", "site", s["id"])


def prune():
    cut = lambda days: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - days * 86400))
    db.x("DELETE FROM checks WHERE ts < ?", (cut(35),))
    db.x("DELETE FROM server_samples WHERE ts < ?", (cut(8),))
    db.x("DELETE FROM incidents WHERE status='resolved' AND resolved_at < ?", (cut(180),))


# ───────────────────────────── read models ─────────────────────────────
def uptime(site_id, hours):
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - hours * 3600))
    r = db.q1("SELECT COUNT(*) n, SUM(ok) ok FROM checks WHERE site_id=? AND kind='public' AND ts>=?", (site_id, since))
    return None if not r["n"] else round(100.0 * (r["ok"] or 0) / r["n"], 2)


def bars(site_id, hours=24, buckets=48):
    """List of 'none' | 'ok' | 'partial' | 'down', oldest first."""
    now = time.time(); span = hours * 3600 / buckets
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now - hours * 3600))
    acc = [[0, 0] for _ in range(buckets)]
    for r in db.q("SELECT ts, ok FROM checks WHERE site_id=? AND kind='public' AND ts>=?", (site_id, since)):
        t = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        i = min(buckets - 1, max(0, int((t - (now - hours * 3600)) / span)))
        acc[i][0] += 1; acc[i][1] += 0 if r["ok"] else 1
    return ["none" if n == 0 else "ok" if bad == 0 else "down" if bad == n else "partial" for n, bad in acc]


def summary():
    sites = []
    for s in db.q("SELECT s.id, s.domain, s.status, s.suspended, s.public_ok, s.ssl_expires, s.checked_at, v.name AS server_name FROM sites s JOIN servers v ON v.id=s.server_id ORDER BY s.domain"):
        last = db.q1("SELECT ms FROM checks WHERE site_id=? AND kind='public' ORDER BY id DESC LIMIT 1", (s["id"],))
        sites.append(s | {"uptime24": uptime(s["id"], 24), "uptime7": uptime(s["id"], 24 * 7), "uptime30": uptime(s["id"], 24 * 30),
                          "bars": bars(s["id"]), "ms": last["ms"] if last else None})
    servers = []
    for v in db.q("SELECT id, name, status, metrics, metrics_at FROM servers WHERE status='ready'"):
        m = json.loads(v["metrics"]) if v["metrics"] else {}
        spark = [r["mem_pct"] for r in reversed(db.q("SELECT mem_pct FROM server_samples WHERE server_id=? AND ok=1 ORDER BY id DESC LIMIT 36", (v["id"],)))]
        servers.append({"id": v["id"], "name": v["name"], "load": m.get("load"), "cores": m.get("cores"), "mem_pct": m.get("mem_pct"),
                        "disk_pct": m.get("disk_pct"), "metrics_at": v["metrics_at"], "mem_spark": spark})
    inc = db.q("SELECT COUNT(*) n, SUM(severity='crit') c FROM incidents WHERE status='open'")[0]
    return {"sites": sites, "servers": servers, "open": inc["n"] or 0, "critical": inc["c"] or 0}
