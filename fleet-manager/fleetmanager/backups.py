"""Scheduled backups, retention, offsite copies (via rclone on the server), restore, and moving a site."""
import json
import re
import secrets
import shlex
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from . import db, monitor, ops, provision, security, ssh
from .ops import NAME_RE, OpError
from .provision import BENCH_USER, _bench

GROUP_RE = re.compile(r"^(\d{8}_\d{6})-")
PROVIDERS = ("AWS", "Cloudflare", "DigitalOcean", "Wasabi", "Minio", "Other")
FREQUENCIES = ("daily", "weekly", "hours")
_locks = {}
_locks_guard = threading.Lock()


def _lock(server_id):
    with _locks_guard:
        return _locks.setdefault(server_id, threading.RLock())     # one heavy operation per server at a time


# ───────────────────────────── policies ─────────────────────────────
def get_policy(site_id=None):
    row = db.q1("SELECT * FROM backup_policies WHERE site_id=?", (site_id,)) if site_id else None
    source = "site" if row else "default"
    if not row:
        row = db.q1("SELECT * FROM backup_policies WHERE site_id IS NULL")
    return {k: row[k] for k in ("enabled", "frequency", "hour", "weekday", "interval_hours", "keep", "offsite", "keep_offsite")} | {"source": source}


def _validate(d):
    out = {"enabled": 1 if d.get("enabled", True) else 0, "offsite": 1 if d.get("offsite") else 0, "frequency": d.get("frequency", "daily")}
    if out["frequency"] not in FREQUENCIES:
        raise OpError("Frequency must be daily, weekly or hours")
    for k, lo, hi, dflt in (("hour", 0, 23, 2), ("weekday", 0, 6, 0), ("interval_hours", 1, 168, 24), ("keep", 1, 60, 7), ("keep_offsite", 1, 365, 14)):
        try:
            v = int(d.get(k, dflt))
        except (TypeError, ValueError):
            raise OpError(f"{k} must be a number")
        if not lo <= v <= hi:
            raise OpError(f"{k} must be between {lo} and {hi}")
        out[k] = v
    return out


def save_policy(site_id, data):
    v = _validate(data)
    row = db.q1("SELECT id FROM backup_policies WHERE site_id IS ?", (site_id,))
    cols = ("enabled", "frequency", "hour", "weekday", "interval_hours", "keep", "offsite", "keep_offsite")
    if row:
        db.x(f"UPDATE backup_policies SET {', '.join(c + '=?' for c in cols)} WHERE id=?", tuple(v[c] for c in cols) + (row["id"],))
    else:
        db.x(f"INSERT INTO backup_policies(site_id,{','.join(cols)}) VALUES(?,{','.join('?' * len(cols))})", (site_id,) + tuple(v[c] for c in cols))
    return get_policy(site_id)


def clear_policy(site_id):
    db.x("DELETE FROM backup_policies WHERE site_id=?", (site_id,))


def _utc(ts):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def last_scheduled(policy, now):
    """Most recent moment (aware datetime) at which the schedule says a backup should have started; None for 'every N hours'."""
    if policy["frequency"] == "hours":
        return None
    local = now.astimezone()
    t = local.replace(hour=policy["hour"], minute=0, second=0, microsecond=0)
    if policy["frequency"] == "daily":
        return t if t <= local else t - timedelta(days=1)
    t -= timedelta(days=(local.weekday() - policy["weekday"]) % 7)
    return t if t <= local else t - timedelta(days=7)


def next_scheduled(policy, now, last_attempt=None):
    if policy["frequency"] == "hours":
        base = _utc(last_attempt) if last_attempt else now
        return max(now, base + timedelta(hours=policy["interval_hours"]))
    return last_scheduled(policy, now) + timedelta(days=1 if policy["frequency"] == "daily" else 7)


def is_due(policy, runs, now):
    """runs: this site's backup_runs, newest first. Retries a failed run hourly, at most 3 times per slot."""
    if not policy["enabled"]:
        return False
    runs = [r for r in runs if r["trigger"] != "pre-restore"]
    last = runs[0] if runs else None
    if last is None:
        return True
    started = _utc(last["started"])
    if policy["frequency"] == "hours":
        return now - started >= timedelta(hours=policy["interval_hours"])
    sched = last_scheduled(policy, now)
    if started < sched:
        return True
    failed = [r for r in runs if r["status"] == "failed" and _utc(r["started"]) >= sched]
    return last["status"] == "failed" and len(failed) < 3 and now - started >= timedelta(hours=1)


# ───────────────────────────── offsite destination ─────────────────────────────
def _clean(v, name, allow_empty=False):
    v = str(v or "").strip()
    if (not v and not allow_empty) or re.search(r"[\x00-\x1f]", v):
        raise OpError(f"{name} is missing or contains invalid characters")
    return v


def dest_get():
    raw = db.setting("offsite")
    return json.loads(security.decrypt(raw)) if raw else {}


def dest_configured():
    d = dest_get()
    return bool(d.get("type") and d.get("path"))


def dest_save(new):
    cur = dest_get()
    t = new.get("type", cur.get("type"))
    if t not in ("s3", "sftp"):
        raise OpError("Destination type must be s3 or sftp")
    d = {"type": t, "path": _clean(new.get("path"), "Bucket / folder path").strip("/")}
    if ".." in d["path"]:
        raise OpError("Path must not contain '..'")
    if t == "s3":
        prov = new.get("provider") or "Other"
        if prov not in PROVIDERS:
            raise OpError("Unknown S3 provider")
        d |= {"provider": prov, "endpoint": _clean(new.get("endpoint"), "Endpoint", True), "region": _clean(new.get("region"), "Region", True),
              "access_key": _clean(new.get("access_key"), "Access key"),
              "secret_key": _clean(new.get("secret_key") or cur.get("secret_key"), "Secret key")}
    else:
        try:
            port = int(new.get("port") or 22)
        except ValueError:
            raise OpError("Port must be a number")
        d |= {"host": _clean(new.get("host"), "Host"), "port": port, "user": _clean(new.get("user"), "User"),
              "password": _clean(new.get("password") or cur.get("password"), "Password")}
    db.set_setting("offsite", security.encrypt(json.dumps(d)))
    return dest_masked()


def dest_masked():
    d = dest_get()
    if not d:
        return {"configured": False}
    return {k: ("" if k in ("secret_key", "password") else v) for k, v in d.items()} | {"configured": dest_configured(), "has_secret": bool(d.get("secret_key") or d.get("password"))}


def dest_clear():
    db.x("DELETE FROM settings WHERE key='offsite'")


def _conf(d, obscured):
    if d["type"] == "s3":
        lines = ["[fm]", "type = s3", f"provider = {d['provider']}", f"access_key_id = {d['access_key']}", f"secret_access_key = {d['secret_key']}", "acl = private"]
        if d.get("endpoint"):
            lines.append(f"endpoint = {d['endpoint']}")
        if d.get("region"):
            lines.append(f"region = {d['region']}")
    else:
        lines = ["[fm]", "type = sftp", f"host = {d['host']}", f"port = {d['port']}", f"user = {d['user']}", f"pass = {obscured}"]
    return "\n".join(lines) + "\n"


@contextmanager
def rclone_session(r, s):
    """Installs rclone if needed and writes a throw-away config (mode 600, owned by the bench user) for this session."""
    d = dest_get()
    if not (d.get("type") and d.get("path")):
        raise OpError("No offsite destination is configured (Settings → Integrations)")
    code, out = r.run("command -v rclone >/dev/null 2>&1 || apt-get install -y -q rclone", sudo=True, stream=False, timeout=900)
    if code != 0:
        raise OpError(f"Could not install rclone on the server: {out.strip()[-300:]}")
    obscured = ""
    if d["type"] == "sftp":
        code, out = r.run(f"printf %s {shlex.quote(d['password'])} | rclone obscure -", stream=False)
        if code != 0:
            raise OpError("rclone could not prepare the SFTP password")
        obscured = out.strip().splitlines()[-1]
    tok = secrets.token_hex(6)
    tmp, conf = f"/tmp/fm-rclone-{tok}.conf", f"/home/{BENCH_USER}/.fm-rclone-{tok}.conf"
    r.write_file(tmp, _conf(d, obscured), 0o600)
    r.run(f"install -o {BENCH_USER} -g {BENCH_USER} -m 600 {tmp} {conf}; rm -f {tmp}", sudo=True, stream=False)
    try:
        yield conf, d
    finally:
        r.run(f"rm -f {conf} {tmp}", sudo=True, stream=False)


def _remote(d, domain, name=""):
    return f"fm:{d['path']}/{domain}" + (f"/{name}" if name else "")


def _rc(r, conf, args, **k):
    return r.run(f"rclone --config {shlex.quote(conf)} {args}", as_user=BENCH_USER, stream=False, **k)


def offsite_list(r, conf, d, domain):
    code, out = _rc(r, conf, f"lsjson {shlex.quote(_remote(d, domain))}")
    if code == 3 or "directory not found" in out.lower():
        return []
    if code != 0:
        raise OpError(f"Could not list the offsite copy: {out.strip()[-300:]}")
    try:
        items = json.loads(out)
    except ValueError:
        raise OpError("Unexpected answer from rclone")
    return sorted([{"name": i["Name"], "size": i["Size"], "mtime": i.get("ModTime", "")} for i in items if not i.get("IsDir") and NAME_RE.match(i["Name"])],
                  key=lambda x: x["name"], reverse=True)


def _offsite_push(r, s, site, files, log, keep):
    """Upload, verify sizes, then prune the offsite copy to the newest `keep` backups."""
    domain = site["domain"]
    with rclone_session(r, s) as (conf, d):
        for f in files:
            log(f"  uploading {f['name']} ({f['size'] // 1024} KB)\n")
            src = f"{s['bench_path']}/sites/{domain}/private/backups/{f['name']}"
            code, out = _rc(r, conf, f"copyto {shlex.quote(src)} {shlex.quote(_remote(d, domain, f['name']))}", timeout=7200)
            if code != 0:
                raise OpError(f"Upload of {f['name']} failed: {out.strip()[-300:]}")
        have = {i["name"]: i["size"] for i in offsite_list(r, conf, d, domain)}
        for f in files:
            if have.get(f["name"]) != f["size"]:
                raise OpError(f"Offsite copy of {f['name']} could not be verified")
        _prune_offsite(r, conf, d, domain, keep, log)


def _groups(files):
    out = {}
    for f in files:
        m = GROUP_RE.match(f["name"])
        if m:
            out.setdefault(m.group(1), []).append(f)
    return dict(sorted(out.items(), reverse=True))        # newest first


def _prune_server(r, s, site, keep, log):
    groups = _groups(ops.backups_via(r, s, site["domain"]))
    old = [f["name"] for g in list(groups)[keep:] for f in groups[g]]
    if old:
        d = f"{s['bench_path']}/sites/{site['domain']}/private/backups"
        r.run(f"cd {shlex.quote(d)} && rm -f -- " + " ".join(shlex.quote(n) for n in old), as_user=BENCH_USER, stream=False)
        log(f"  removed {len(old)} old file(s) from the server (keeping the newest {keep} backups)\n")


def _prune_offsite(r, conf, d, domain, keep, log):
    groups = _groups(offsite_list(r, conf, d, domain))
    old = [f["name"] for g in list(groups)[keep:] for f in groups[g]]
    for n in old:
        _rc(r, conf, f"deletefile {shlex.quote(_remote(d, domain, n))}")
    if old:
        log(f"  removed {len(old)} old file(s) offsite (keeping the newest {keep} backups)\n")


# ───────────────────────────── running a backup ─────────────────────────────
def run_backup(site_id, trigger="manual", log=lambda t: None):
    site, s = ops.get(site_id)
    pol = get_policy(site_id)
    domain = site["domain"]
    with _lock(s["id"]):
        run_id = db.x("INSERT INTO backup_runs(site_id,domain,started,status,trigger) VALUES(?,?,?,'running',?)", (site_id, domain, db.now(), trigger))
        try:
            with ssh.Runner(s, log) as r:
                log(f">>> Backing up {domain} (database + files)\n")
                code, out = r.run(ops._site_cmd(s, domain, "backup --with-files"), as_user=BENCH_USER)
                if code != 0:
                    raise ssh.SSHError(f"bench backup failed (exit {code}): {out.strip()[-300:]}")
                groups = _groups(ops.backups_via(r, s, domain))
                if not groups:
                    raise ssh.SSHError("The backup command finished but no backup files were found")
                gid, files = next(iter(groups.items()))
                size = sum(f["size"] for f in files)
                offsite = ""
                if pol["offsite"] and trigger != "pre-restore":
                    if not dest_configured():
                        offsite = "skipped: no destination configured"
                    else:
                        try:
                            log(">>> Copying offsite\n")
                            _offsite_push(r, s, site, files, log, pol["keep_offsite"])
                            offsite = "ok"
                        except (OpError, ssh.SSHError) as e:
                            offsite = f"failed: {e}"[:300]
                            log(f"!! Offsite copy failed: {e}\n")
                if trigger != "pre-restore":
                    _prune_server(r, s, site, pol["keep"], log)
            db.x("UPDATE backup_runs SET finished=?, status='ok', group_ts=?, size_bytes=?, offsite_status=? WHERE id=?", (db.now(), gid, size, offsite, run_id))
            monitor.resolve_incident("backup_failed", "site", site_id)
            monitor.resolve_incident("backup_overdue", "site", site_id)
            if offsite.startswith("failed"):
                monitor.open_incident("backup_offsite", "site", site_id, domain, "Offsite backup copy failed", offsite, "warn")
            elif offsite == "ok":
                monitor.resolve_incident("backup_offsite", "site", site_id)
            log(f"\nBackup finished ({size // 1024} KB){'; offsite copy ' + offsite if offsite else ''}.\n")
            return run_id
        except Exception as e:
            db.x("UPDATE backup_runs SET finished=?, status='failed', message=? WHERE id=?", (db.now(), str(e)[:400], run_id))
            monitor.open_incident("backup_failed", "site", site_id, domain, "Backup failed", str(e)[:400], "crit")
            raise


def runs_for(site_id, limit=50):
    return db.q("SELECT * FROM backup_runs WHERE site_id=? ORDER BY id DESC LIMIT ?", (site_id, limit))


def due_sites(now=None):
    now = now or datetime.now(timezone.utc)
    out = []
    for s in db.q("SELECT s.id FROM sites s JOIN servers v ON v.id=s.server_id WHERE v.status='ready' AND s.status IN ('up','down')"):
        if is_due(get_policy(s["id"]), runs_for(s["id"], 10), now):
            out.append(s["id"])
    return out


def run_due():
    """Called by the scheduler every minute: backs up due sites, one server at a time."""
    ids = due_sites()
    by_server = {}
    for sid in ids:
        by_server.setdefault(db.q1("SELECT server_id FROM sites WHERE id=?", (sid,))["server_id"], []).append(sid)
    threads = []

    def work(sites):
        for sid in sites:
            try:
                run_backup(sid, "scheduled")
            except Exception:
                pass                                   # already recorded as a failed run + incident
    for sites in by_server.values():
        t = threading.Thread(target=work, args=(sites,), daemon=True); t.start(); threads.append(t)
    return ids, threads


def check_overdue(now=None):
    """Warn when an enabled site has no successful backup for far longer than its schedule allows."""
    now = now or datetime.now(timezone.utc)
    for s in db.q("SELECT * FROM sites WHERE status IN ('up','down')"):
        pol = get_policy(s["id"])
        if not pol["enabled"]:
            monitor.resolve_incident("backup_overdue", "site", s["id"])
            continue
        limit = {"daily": timedelta(hours=36), "weekly": timedelta(days=9), "hours": timedelta(hours=pol["interval_hours"] * 2 + 1)}[pol["frequency"]]
        ok = db.q1("SELECT started FROM backup_runs WHERE site_id=? AND status='ok' ORDER BY id DESC LIMIT 1", (s["id"],))
        age_base = _utc(ok["started"]) if ok else _utc(s["created"])
        if now - age_base > limit:
            monitor.open_incident("backup_overdue", "site", s["id"], s["domain"], "No recent backup",
                                  "Last successful backup: " + (ok["started"] + " UTC" if ok else "never"), "warn")
        else:
            monitor.resolve_incident("backup_overdue", "site", s["id"])


def overview():
    now = datetime.now(timezone.utc)
    sites = []
    for s in db.q("SELECT s.id, s.domain, s.status, v.name AS server_name FROM sites s JOIN servers v ON v.id=s.server_id ORDER BY s.domain"):
        pol = get_policy(s["id"])
        runs = runs_for(s["id"], 10)
        last = runs[0] if runs else None
        last_ok = next((r for r in runs if r["status"] == "ok"), None)
        nxt = None
        if pol["enabled"]:
            nxt = (now if is_due(pol, runs, now) else next_scheduled(pol, now, runs[0]["started"] if runs else None)).isoformat()
        sites.append(s | {"policy": pol, "last": last, "last_ok": last_ok, "next_run": nxt})
    return {"sites": sites, "default": get_policy(None), "destination": dest_masked(),
            "runs": db.q("SELECT * FROM backup_runs ORDER BY id DESC LIMIT 25")}


# ───────────────────────────── restore ─────────────────────────────
def _pick(files, suffix, exclude=None):
    for f in files:
        if f["name"].endswith(suffix) and not (exclude and f["name"].endswith(exclude)):
            return f
    return None


def _restore_cmd(s, domain, bdir, files, pw):
    db_f, pub, priv = _pick(files, "-database.sql.gz"), _pick(files, "-files.tar", "-private-files.tar"), _pick(files, "-private-files.tar")
    if not db_f:
        raise OpError("This backup has no database file, so it cannot be restored")
    opts = f"--db-root-password {shlex.quote(pw)}"
    if pub:
        opts += f" --with-public-files {shlex.quote(bdir + '/' + pub['name'])}"
    if priv:
        opts += f" --with-private-files {shlex.quote(bdir + '/' + priv['name'])}"
    return ops._site_cmd(s, domain, f"--force restore {shlex.quote(bdir + '/' + db_f['name'])} {opts}")


def offsite_files(site_id):
    site, s = ops.get(site_id)
    with ssh.Runner(s) as r, rclone_session(r, s) as (conf, d):
        return offsite_list(r, conf, d, site["domain"])


def restore_job(site_id, group, source, log):
    site, s = ops.get(site_id)
    domain = site["domain"]
    if not re.fullmatch(r"\d{8}_\d{6}", group or ""):
        raise ssh.SSHError("Bad backup id")
    bdir = f"{s['bench_path']}/sites/{domain}/private/backups"
    pw = security.decrypt(s["db_root_pw_enc"])
    with _lock(s["id"]):
        with ssh.Runner(s, log) as r:
            files = _groups(ops.backups_via(r, s, domain)).get(group, [])
            if source == "offsite":
                log(">>> Fetching the backup from offsite storage\n")
                with rclone_session(r, s) as (conf, d):
                    off = _groups(offsite_list(r, conf, d, domain)).get(group, [])
                    if not off:
                        raise ssh.SSHError("That backup was not found offsite")
                    for f in off:
                        code, out = _rc(r, conf, f"copyto {shlex.quote(_remote(d, domain, f['name']))} {shlex.quote(bdir + '/' + f['name'])}", timeout=7200)
                        if code != 0:
                            raise ssh.SSHError(f"Download of {f['name']} failed: {out.strip()[-300:]}")
                    files = off
            if not files:
                raise ssh.SSHError("That backup was not found on the server")
            cmd = _restore_cmd(s, domain, bdir, files, pw)       # validates before touching anything
        log(">>> Safety backup of the current state (so this restore can be undone)\n")
        run_backup(site_id, "pre-restore", log)
        with ssh.Runner(s, log) as r:
            log(">>> Restoring (the site is in maintenance mode meanwhile)\n")
            r.run(ops._site_cmd(s, domain, "set-maintenance-mode on"), as_user=BENCH_USER, stream=False)
            code, _ = r.run(cmd, as_user=BENCH_USER)
            if code != 0:
                r.run(ops._site_cmd(s, domain, "set-maintenance-mode off"), as_user=BENCH_USER, stream=False)
                raise ssh.SSHError(f"Restore failed (exit {code}). The safety backup taken just before is in the Backups tab.")
            r.run(ops._site_cmd(s, domain, "migrate"), as_user=BENCH_USER)
            r.run(ops._site_cmd(s, domain, "clear-cache"), as_user=BENCH_USER, stream=False)
            if not site["suspended"]:
                r.run(ops._site_cmd(s, domain, "set-maintenance-mode off"), as_user=BENCH_USER, stream=False)
    log("\nRestore finished. The Administrator password is now the one from that backup; use Reset password if you don't know it.\n")


# ───────────────────────────── upload a database file ─────────────────────────────
DB_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\- ]{0,150}\.(sql|sql\.gz)$", re.I)


def upload_db_job(site_id, local_path, filename, log):
    """Replace the site's database with an uploaded .sql / .sql.gz dump. The local temp file is always deleted."""
    import os
    try:
        site, s = ops.get(site_id)
        domain = site["domain"]
        if not DB_FILE_RE.match(filename or ""):
            raise ssh.SSHError("Only .sql or .sql.gz files can be uploaded")
        size = os.path.getsize(local_path)
        if size <= 0:
            raise ssh.SSHError("The uploaded file is empty")
        pw = security.decrypt(s["db_root_pw_enc"])
        ext = ".sql.gz" if filename.lower().endswith(".gz") else ".sql"
        with _lock(s["id"]):
            log(">>> Safety backup of the current state (so this upload can be undone)\n")
            run_backup(site_id, "pre-upload", log)
            stage = f"/tmp/fm-upload-{secrets.token_hex(5)}"
            remote = f"{stage}/database{ext}"
            with ssh.Runner(s, log) as r:
                try:
                    r.run(f"mkdir -p {stage} && chmod 777 {stage}", sudo=True, stream=False)
                    log(f"\n>>> Sending {filename} ({size >> 20 or 1} MB) to {s['name']}\n")
                    def chunks():
                        sent = 0
                        with open(local_path, "rb") as src:
                            while True:
                                chunk = src.read(262144)
                                if not chunk:
                                    return
                                yield chunk
                                sent += len(chunk)
                                if sent // (64 << 20) != (sent - len(chunk)) // (64 << 20):
                                    log(f"    {sent >> 20} MB sent…\n")
                    r.write_chunks(remote, chunks())
                    r.run(f"chmod 644 {shlex.quote(remote)}", sudo=True, stream=False)
                    log("\n>>> Loading the database (the site is in maintenance mode meanwhile)\n")
                    r.run(ops._site_cmd(s, domain, "set-maintenance-mode on"), as_user=BENCH_USER, stream=False)
                    code, _ = r.run(ops._site_cmd(s, domain, f"--force restore {shlex.quote(remote)} --db-root-password {shlex.quote(pw)}"), as_user=BENCH_USER)
                    if code != 0:
                        r.run(ops._site_cmd(s, domain, "set-maintenance-mode off"), as_user=BENCH_USER, stream=False)
                        raise ssh.SSHError(f"Loading the database failed (exit {code}). The safety backup taken just before is in the Backups tab.")
                    log("\n>>> Migrating\n")
                    r.run(ops._site_cmd(s, domain, "migrate"), as_user=BENCH_USER)
                    r.run(ops._site_cmd(s, domain, "clear-cache"), as_user=BENCH_USER, stream=False)
                    if not site["suspended"]:
                        r.run(ops._site_cmd(s, domain, "set-maintenance-mode off"), as_user=BENCH_USER, stream=False)
                    provision.sync_server(s, r, log)
                finally:
                    r.run(f"rm -rf {stage}", sudo=True, stream=False)
        log("\nDatabase uploaded. The Administrator password is now the one stored in that database; use Reset password if you don't know it.\n")
    finally:
        try:
            os.remove(local_path)
        except OSError:
            pass


# ───────────────────────────── move to another server ─────────────────────────────
def _relay(rs, rt, src, dst, log):
    total = 0

    def chunks():
        nonlocal total
        for chunk in rs.read_chunks(src, sudo=True):
            total += len(chunk)
            if total // (64 << 20) != (total - len(chunk)) // (64 << 20):
                log(f"    {total >> 20} MB copied…\n")
            yield chunk
    rt.write_chunks(dst, chunks())
    return total


def move_job(site_id, target_id, log):
    site, src = ops.get(site_id)
    tgt = db.q1("SELECT * FROM servers WHERE id=?", (target_id,))
    if not tgt or tgt["status"] != "ready":
        raise ssh.SSHError("The target server is not ready")
    if tgt["id"] == src["id"]:
        raise ssh.SSHError("The site is already on that server")
    if tgt["version"] != src["version"]:
        raise ssh.SSHError(f"Servers run different ERPNext versions ({src['version']} vs {tgt['version']}); a move would break the site")
    domain = site["domain"]
    apps = provision.order_apps([a for a in (site["apps"] or "").split(",") if a])
    first, second = sorted((src["id"], tgt["id"]))
    with _lock(first), _lock(second):
        missing = provision.missing_on_server(tgt["id"], apps)
        if missing:
            log(f">>> Installing missing apps on {tgt['name']}: {', '.join(missing)}\n")
            with ssh.Runner(tgt, log) as rt:
                for n in missing:
                    provision.get_app(tgt, rt, n, log)
                rt.run(_bench(tgt, "bench restart || true"), as_user=BENCH_USER)
        log(f">>> Backing up {domain} on {src['name']}\n")
        run_backup(site_id, "move", log)
        with ssh.Runner(src, log) as rs, ssh.Runner(tgt, log) as rt:
            files = next(iter(_groups(ops.backups_via(rs, src, domain)).values()))
            code, _ = rt.run(f"test -d {shlex.quote(tgt['bench_path'] + '/sites/' + domain)}", as_user=BENCH_USER, stream=False)
            if code == 0:
                raise ssh.SSHError(f"A site named {domain} already exists on {tgt['name']}; remove it there first")
            provision.ensure_db_root_password(rt, tgt)
            provision.ensure_bench_services(rt, tgt, log)
            log(f"\n>>> Creating an empty site on {tgt['name']}\n")
            code, _ = rt.run(_bench(tgt, f"bench new-site {shlex.quote(domain)} --db-root-password {shlex.quote(security.decrypt(tgt['db_root_pw_enc']))} "
                                         f"--admin-password {shlex.quote(security.gen_password())}"), as_user=BENCH_USER)
            if code != 0:
                raise ssh.SSHError(f"Could not create the site on {tgt['name']} (exit {code})")
            tok = secrets.token_hex(5)
            stage = f"/tmp/fm-move-{tok}"
            sbd, tbd = f"{src['bench_path']}/sites/{domain}/private/backups", f"{tgt['bench_path']}/sites/{domain}/private/backups"
            try:
                rs.run(f"mkdir -p {stage} && cp {' '.join(shlex.quote(sbd + '/' + f['name']) for f in files)} {stage}/ && chmod -R a+rX {stage}", sudo=True, stream=False)
                rt.run(f"mkdir -p {stage} && chmod 777 {stage}", sudo=True, stream=False)
                log(f"\n>>> Transferring {len(files)} file(s) {src['name']} → {tgt['name']} (through this computer)\n")
                for f in files:
                    log(f"  {f['name']}\n")
                    _relay(rs, rt, f"{stage}/{f['name']}", f"{stage}/{f['name']}", log)
                rt.run(f"install -d -o {BENCH_USER} -g {BENCH_USER} {shlex.quote(tbd)}; "
                       f"for f in {stage}/*; do install -o {BENCH_USER} -g {BENCH_USER} -m 640 \"$f\" {shlex.quote(tbd)}/; done", sudo=True, stream=False)
            finally:
                rs.run(f"rm -rf {stage}", sudo=True, stream=False)
                rt.run(f"rm -rf {stage}", sudo=True, stream=False)
            log("\n>>> Restoring on the new server\n")
            code, _ = rt.run(_restore_cmd(tgt, domain, tbd, files, security.decrypt(tgt["db_root_pw_enc"])), as_user=BENCH_USER)
            if code != 0:
                raise ssh.SSHError(f"Restore on {tgt['name']} failed (exit {code}). The original site on {src['name']} is untouched.")
            rt.run(ops._site_cmd(tgt, domain, "migrate"), as_user=BENCH_USER)
            ops._reload_nginx(rt, tgt)
            db.x("UPDATE sites SET server_id=?, golive_provider=0, public_ok=NULL, status='up' WHERE id=?", (tgt["id"], site_id))
            provision.sync_server(tgt, rt, log)
            provision.sync_server(src, rs, log)
    log(f"\nMoved to {tgt['name']} ({tgt['ip']}).\nNEXT: point DNS for {domain} to {tgt['ip']}" + (" and add the domain in the provider panel" if tgt["gateway"] else "")
        + f". The original is still on {src['name']}; remove it there once you have checked the new one.\n")
