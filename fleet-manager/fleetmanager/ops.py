"""Day-to-day site operations that support agents run over SSH (bench commands as the bench user)."""
import re
import shlex
import time
import warnings

import requests

from . import db, domains, provision, security, ssh
from .provision import BENCH_USER, _bench

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,200}$")

# fixed whitelist of log files: (label, path relative to bench or absolute, needs root)
LOGS = {
    "site": ("Site log", "sites/{site}/logs/frappe.log", False),
    "web-error": ("Web server errors", "logs/web.error.log", False),
    "worker-error": ("Background worker errors", "logs/worker.error.log", False),
    "scheduler": ("Scheduler", "logs/scheduler.log", False),
    "bench": ("Bench log", "logs/frappe.log", False),
    "nginx-error": ("Nginx errors", "/var/log/nginx/error.log", True),
    "nginx-access": ("Nginx access", "/var/log/nginx/access.log", True),
}


class OpError(Exception):
    pass


def _site_cmd(s, domain, cmd):
    return _bench(s, f"bench --site {shlex.quote(domain)} {cmd}")


def _run(r, s, domain, cmd, what):
    code, out = r.run(_site_cmd(s, domain, cmd), as_user=BENCH_USER, stream=False)
    if code != 0:
        raise OpError(f"{what} failed: {out.strip()[-600:]}")
    return out


def get(site_id):
    site = db.q1("SELECT * FROM sites WHERE id=?", (site_id,))
    if not site:
        raise OpError("Site not found")
    s = db.q1("SELECT * FROM servers WHERE id=?", (site["server_id"],))
    if not s or s["status"] != "ready":
        raise OpError("The server of this site is not ready")
    return site, s


# ------------------------------------------------------------ quick actions (synchronous)
def maintenance(site_id, on: bool):
    site, s = get(site_id)
    with ssh.Runner(s) as r:
        _run(r, s, site["domain"], f"set-maintenance-mode {'on' if on else 'off'}", "Maintenance mode")
    return site


def clear_cache(site_id):
    site, s = get(site_id)
    with ssh.Runner(s) as r:
        _run(r, s, site["domain"], "clear-cache", "Clear cache")
        _run(r, s, site["domain"], "clear-website-cache", "Clear website cache")


def reset_admin_password(site_id):
    site, s = get(site_id)
    pw = security.gen_password()
    with ssh.Runner(s) as r:
        _run(r, s, site["domain"], f"set-admin-password {shlex.quote(pw)}", "Password reset")
    db.x("UPDATE sites SET admin_pw_enc=? WHERE id=?", (security.encrypt(pw), site_id))
    return pw


def restart_services(server_id):
    s = db.q1("SELECT * FROM servers WHERE id=?", (server_id,))
    if not s or s["status"] != "ready":
        raise OpError("Server is not ready")
    with ssh.Runner(s) as r:
        code, out = r.run("supervisorctl restart all 2>&1; systemctl reload nginx 2>&1", sudo=True, stream=False)
    return out.strip()


def read_log(site_id, source, lines=300, query=""):
    if source not in LOGS:
        raise OpError("Unknown log")
    site, s = get(site_id)
    label, path, root = LOGS[source]
    path = path.format(site=site["domain"])
    if not path.startswith("/"):
        path = f"{s['bench_path']}/{path}"
    n = max(20, min(int(lines), 2000))
    cmd = f"tail -n {n} {shlex.quote(path)} 2>&1"
    if query.strip():
        cmd += f" | grep -i -F -- {shlex.quote(query.strip()[:100])} | tail -n {n}"
    with ssh.Runner(s) as r:
        code, out = (r.run(cmd, sudo=True, stream=False) if root else r.run(cmd, as_user=BENCH_USER, stream=False))
    return out[-200_000:]


def list_backups(site_id):
    site, s = get(site_id)
    d = f"{s['bench_path']}/sites/{site['domain']}/private/backups"
    with ssh.Runner(s) as r:
        code, out = r.run(f"cd {shlex.quote(d)} 2>/dev/null && for f in *; do [ -f \"$f\" ] && echo \"$f|$(stat -c '%s|%Y' \"$f\")\"; done",
                          as_user=BENCH_USER, stream=False)
    items = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3 and NAME_RE.match(parts[0]):
            items.append({"name": parts[0], "size": int(parts[1]), "mtime": int(parts[2])})
    return sorted(items, key=lambda x: -x["mtime"])


def backup_path(site, s, name):
    if not NAME_RE.match(name or "") or ".." in name:
        raise OpError("Bad file name")
    return f"{s['bench_path']}/sites/{site['domain']}/private/backups/{name}"


def add_domain(site_id, new_domain):
    site, s = get(site_id)
    chk = domains.check(new_domain)
    if chk["problems"]:
        raise OpError("; ".join(chk["problems"]))
    d = chk["domain"]
    with ssh.Runner(s) as r:
        code, out = r.run(_bench(s, f"bench setup add-domain {shlex.quote(d)} --site {shlex.quote(site['domain'])}"), as_user=BENCH_USER, stream=False)
        if code != 0:
            raise OpError(f"Add domain failed: {out.strip()[-500:]}")
        _reload_nginx(r, s)
    aliases = [a for a in (site["aliases"] or "").split(",") if a] + [d]
    db.x("UPDATE sites SET aliases=? WHERE id=?", (",".join(dict.fromkeys(aliases)), site_id))
    return d


def _reload_nginx(r, s):
    code, out = r.run(_bench(s, "bench setup nginx --yes"), as_user=BENCH_USER, stream=False)
    if code == 0:
        code, out = r.run("nginx -t 2>&1 && systemctl reload nginx 2>&1", sudo=True, stream=False)
    if code != 0:
        raise OpError(f"nginx could not reload: {out.strip()[-600:]}")


# ------------------------------------------------------------ long actions (run as jobs)
def backup_job(site_id, log):
    site, s = get(site_id)
    with ssh.Runner(s, log) as r:
        log(f">>> Backing up {site['domain']} (database + files)\n")
        code, _ = r.run(_site_cmd(s, site["domain"], "backup --with-files"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"bench backup failed (exit {code})")
    log("\nBackup finished. Download it from the Backups tab.\n")


def migrate_job(site_id, log):
    site, s = get(site_id)
    with ssh.Runner(s, log) as r:
        log(f">>> Migrating {site['domain']}\n")
        code, _ = r.run(_site_cmd(s, site["domain"], "migrate"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"bench migrate failed (exit {code})")
        r.run(_site_cmd(s, site["domain"], "clear-cache"), as_user=BENCH_USER, stream=False)
    log("\nMigration finished.\n")


def rename_job(site_id, new_domain, log):
    site, s = get(site_id)
    chk = domains.check(new_domain)
    if chk["problems"]:
        raise ssh.SSHError("; ".join(chk["problems"]))
    new = chk["domain"]
    with ssh.Runner(s, log) as r:
        log(f">>> Backing up before rename\n")
        code, _ = r.run(_site_cmd(s, site["domain"], "backup --with-files"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError("Backup before rename failed; nothing was changed.")
        log(f"\n>>> Renaming {site['domain']} -> {new}\n")
        code, _ = r.run(_bench(s, f"bench rename-site {shlex.quote(site['domain'])} {shlex.quote(new)}"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"rename-site failed (exit {code}). The backup taken first is in the Backups tab.")
        db.x("UPDATE sites SET domain=?, public_ok=NULL, golive_provider=0, ssl=0 WHERE id=?", (new, site_id))
        try:
            _reload_nginx(r, s)
        except OpError as e:
            raise ssh.SSHError(str(e))
        provision.sync_server(s, r, log)
    log(f"\nRenamed. Point DNS for {new} to {s['ip']} and (on gateway providers) add it in the provider panel.\n")


def drop_job(site_id, backup_first, log):
    site, s = get(site_id)
    pw = security.decrypt(s["db_root_pw_enc"])
    with ssh.Runner(s, log) as r:
        if backup_first:
            log(">>> Backing up before deletion\n")
            code, _ = r.run(_site_cmd(s, site["domain"], "backup --with-files"), as_user=BENCH_USER)
            if code != 0:
                raise ssh.SSHError("Backup failed, so the site was NOT deleted.")
        log(f"\n>>> Deleting {site['domain']}\n")
        code, _ = r.run(_bench(s, f"bench drop-site {shlex.quote(site['domain'])} --force --no-backup --db-root-password {shlex.quote(pw)}"),
                        as_user=BENCH_USER, stream=False)
        if code != 0:
            raise ssh.SSHError(f"drop-site failed (exit {code})")
        db.x("DELETE FROM site_notes WHERE site_id=?", (site_id,))
        db.x("DELETE FROM sites WHERE id=?", (site_id,))
        try:
            _reload_nginx(r, s)
        except OpError as e:
            log(f"!! {e}\n")
        provision.sync_server(s, r, log)
    log("\nSite deleted. Its files were moved to 'archived_sites' on the server" + (", with the backup." if backup_first else ".") + "\n")


# ------------------------------------------------------------ go-live check
def golive(site, server):
    """Is the site reachable from the internet under its own name? (works for gateway providers too)"""
    domain = site["domain"]
    ips = domains.resolve(domain)
    dns = {"ok": server["ip"] in ips, "ips": ips, "expected": server["ip"]}
    pub = {"ok": False, "detail": ""}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            resp = requests.get(f"http://{domain}/api/method/ping", timeout=7, verify=False, allow_redirects=True)
            pub["ok"] = resp.status_code == 200 and "pong" in resp.text
            pub["detail"] = f"HTTP {resp.status_code}" + ("" if pub["ok"] else " — not answering as ERPNext")
        except requests.RequestException as e:
            pub["detail"] = type(e).__name__
    gw = bool(server.get("gateway"))
    db.x("UPDATE sites SET public_ok=?, public_at=? WHERE id=?", (1 if pub["ok"] else 0, time.strftime("%Y-%m-%d %H:%M:%S"), site["id"]))
    return {"dns": dns, "public": pub, "gateway": gw, "gateway_url": server.get("gateway_url") or "",
            "provider_done": bool(site.get("golive_provider")), "inner_ip": _inner_ip(server),
            "live": pub["ok"]}


def _inner_ip(server):
    import json
    try:
        return (json.loads(server.get("metrics") or "{}") or {}).get("inner_ip", "")
    except ValueError:
        return ""
