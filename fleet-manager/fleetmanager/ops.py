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


def scheduler(site_id, on: bool):
    """Turn the site's scheduler (background jobs: data import, emails, reports) on or off. 'Schedule is inactive' comes from here,
    or from maintenance mode being on, or from the scheduler worker process being stopped."""
    site, s = get(site_id)
    d = site["domain"]
    with ssh.Runner(s) as r:
        if on:
            _run(r, s, d, "enable-scheduler", "Enable scheduler")
            r.run(_site_cmd(s, d, "scheduler resume"), as_user=BENCH_USER, stream=False)
            code, out = r.run("supervisorctl status 2>&1 | grep -i schedule", sudo=True, stream=False)
            running = "RUNNING" in out
            if not running:
                r.run("supervisorctl start all 2>&1", sudo=True, stream=False)
        else:
            _run(r, s, d, "disable-scheduler", "Disable scheduler")
            running = None
    return {"on": on, "worker_running": running, "maintenance": bool(site["suspended"])}


def developer_mode(site_id, on=None):
    """Read (on=None) or set `developer_mode` in the site's site_config.json. Returns the resulting state."""
    import json as _json
    site, s = get(site_id)
    d = site["domain"]
    path = f"{s['bench_path']}/sites/{d}/site_config.json"
    with ssh.Runner(s) as r:
        if on is not None:
            _run(r, s, d, f"set-config developer_mode {1 if on else 0}", "Developer mode")
            r.run(_site_cmd(s, d, "clear-cache"), as_user=BENCH_USER, stream=False)
            r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER, stream=False)
        code, out = r.run(f"cat {shlex.quote(path)}", sudo=True, stream=False)
    try:
        cfg = _json.loads(out) if code == 0 else {}
    except ValueError:
        cfg = {}
    return {"on": bool(cfg.get("developer_mode"))}


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


def backups_via(r, s, domain):
    d = f"{s['bench_path']}/sites/{domain}/private/backups"
    code, out = r.run(f"cd {shlex.quote(d)} 2>/dev/null && for f in *; do [ -f \"$f\" ] && echo \"$f|$(stat -c '%s|%Y' \"$f\")\"; done",
                      as_user=BENCH_USER, stream=False)
    items = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3 and NAME_RE.match(parts[0]):
            items.append({"name": parts[0], "size": int(parts[1]), "mtime": int(parts[2])})
    return sorted(items, key=lambda x: (-x["mtime"], x["name"]))


def list_backups(site_id):
    site, s = get(site_id)
    with ssh.Runner(s) as r:
        return backups_via(r, s, site["domain"])


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
def backup_job(site_id, log, trigger="manual"):
    from . import backups
    backups.run_backup(site_id, trigger, log)


def migrate_job(site_id, log):
    site, s = get(site_id)
    with ssh.Runner(s, log) as r:
        log(f">>> Migrating {site['domain']}\n")
        code, _ = r.run(_site_cmd(s, site["domain"], "migrate"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"bench migrate failed (exit {code})")
        r.run(_site_cmd(s, site["domain"], "clear-cache"), as_user=BENCH_USER, stream=False)
    log("\nMigration finished.\n")


# ------------------------------------------------------------ apps on a site
def _app_info_cmd(check):
    """One line per app: name|branch|commit|commits behind upstream. With check=True each app is fetched (in parallel, 25 s each)."""
    fetch = "timeout 25 git -C $a fetch -q 2>/dev/null; " if check else ""
    one = ('n=$(basename $a); [ -d $a.git ] || exit 0; ' + fetch +
           'echo "$n|$(git -C $a rev-parse --abbrev-ref HEAD)|$(git -C $a rev-parse --short HEAD)|'
           '$(git -C $a rev-list --count HEAD..@{u} 2>/dev/null || echo 0)"')
    return f'for a in apps/*/; do ( {one} ) & done; wait'


def apps_info(site_id, check=True):
    """Installed apps of a site with version and number of upstream commits not yet pulled (only when check=True: that needs a
    network fetch per app), plus installable apps."""
    site, s = get(site_id)
    with ssh.Runner(s) as r:
        mine = provision.site_apps(s, r, site["domain"])
        code, out = r.run(_bench(s, "bench version 2>/dev/null"), as_user=BENCH_USER, stream=False, timeout=60)
        versions = {l.split()[0]: l.split()[1] for l in out.splitlines() if code == 0 and len(l.split()) >= 2}
        code, out = r.run(_bench(s, _app_info_cmd(check)), as_user=BENCH_USER, stream=False, timeout=120)
        git = {}
        for l in out.splitlines():
            p = l.split("|")
            if len(p) == 4:
                git[p[0]] = {"branch": p[1], "commit": p[2], "behind": int(p[3]) if p[3].isdigit() else 0}
    reg = {a["name"]: a for a in db.q("SELECT * FROM apps")}
    on_server = {a["app_name"] for a in db.q("SELECT app_name FROM server_apps WHERE server_id=?", (s["id"],))}
    installed = [{"name": n, "title": (reg.get(n) or {}).get("title") or n, "version": versions.get(n, ""), **git.get(n, {})} for n in mine]
    available = [{"name": n, "title": a["title"], "on_server": n in on_server, "requires": a["requires"]}
                 for n, a in reg.items() if n not in mine]
    return {"installed": installed, "available": available}


def _store_apps(s, r, site):
    now = [n for n in provision.site_apps(s, r, site["domain"]) if n != "frappe"]
    db.x("UPDATE sites SET apps=? WHERE id=?", (",".join(now), site["id"]))


def install_apps_job(site_id, names, log):
    site, s = get(site_id)
    domain = site["domain"]
    names = provision.order_apps(names)
    with ssh.Runner(s, log) as r:
        have = set(provision.site_apps(s, r, domain))
        todo = [n for n in names if n not in have]
        if not todo:
            log("All of these apps are already installed.\n")
            return
        log(f">>> Backing up {domain} before installing\n")
        _run(r, s, domain, "backup --with-files", "Safety backup")
        server_has = set(provision.list_bench_apps(s, r))
        for n in todo:
            if n not in server_has:
                provision.get_app(s, r, n, log)
        repaired = [n for n in todo if provision.ensure_importable(s, r, n, log)]
        for n in todo:
            log(f"\n>>> Installing {n} on {domain}\n")
            code, _ = r.run(_site_cmd(s, domain, f"install-app {shlex.quote(n)}"), as_user=BENCH_USER)
            if code != 0:
                raise ssh.SSHError(f"install-app {n} failed (exit {code}). The site keeps running; a backup from before is on the Backups tab.")
        for n in repaired:
            log(f"\n>>> Building assets of {n}\n")
            r.run(_bench(s, f"bench build --app {shlex.quote(n)}"), as_user=BENCH_USER, timeout=3600)
        r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER)
        provision.sync_server(s, r, log)
        _store_apps(s, r, site)
    log("\nApps installed.\n")


def uninstall_app_job(site_id, name, remove_from_server, log):
    site, s = get(site_id)
    domain = site["domain"]
    if not NAME_RE.match(name or "") or name == "frappe":
        raise OpError("That app cannot be removed")
    with ssh.Runner(s, log) as r:
        installed = set(provision.site_apps(s, r, domain))
        if name not in installed:
            raise ssh.SSHError(f"{name} is not installed on {domain}")
        needed_by = [a["name"] for a in db.q("SELECT name, requires FROM apps") if name in (a["requires"] or "").split(",") and a["name"] in installed]
        if needed_by:
            raise ssh.SSHError(f"Remove {', '.join(needed_by)} first: it needs {name}")
        used_elsewhere = [x["domain"] for x in db.q("SELECT domain, apps FROM sites WHERE server_id=? AND id!=?", (s["id"], site_id)) if name in (x["apps"] or "").split(",")]
        if remove_from_server and used_elsewhere:
            raise ssh.SSHError(f"{name} is also installed on {', '.join(used_elsewhere)}, so it cannot be removed from the server")
        log(f">>> Backing up {domain} before removing {name}\n")
        _run(r, s, domain, "backup --with-files", "Safety backup")
        log(f"\n>>> Uninstalling {name} from {domain}\n")
        code, _ = r.run(_site_cmd(s, domain, f"uninstall-app {shlex.quote(name)} --yes --no-backup"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"uninstall-app {name} failed (exit {code}). The site keeps running; the backup from before is on the Backups tab.")
        if remove_from_server:
            log(f"\n>>> Removing {name} from the server\n")
            code, _ = r.run(_bench(s, f"bench remove-app {shlex.quote(name)} --force"), as_user=BENCH_USER)
            if code != 0:
                raise ssh.SSHError(f"The app was uninstalled from the site, but removing it from the server failed (exit {code})")
        r.run(_site_cmd(s, domain, "clear-cache"), as_user=BENCH_USER, stream=False)
        r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER)
        provision.sync_server(s, r, log)
        _store_apps(s, r, site)
    log(f"\n{name} removed from {domain}" + (" and from the server." if remove_from_server else ". Its code is still on the server.") + "\n")


def remove_server_app_job(server_id, name, log):
    """Delete an app's code from the VPS (bench remove-app). Refused while any site on the server has it installed."""
    s = db.q1("SELECT * FROM servers WHERE id=?", (server_id,))
    if not s or s["status"] != "ready":
        raise OpError("The server is not ready")
    if not NAME_RE.match(name or "") or name == "frappe":
        raise OpError("That app cannot be removed")
    with ssh.Runner(s, log) as r:
        if name not in set(provision.list_bench_apps(s, r)):
            raise ssh.SSHError(f"{name} is not on {s['name']}")
        users = [x["domain"] for x in db.q("SELECT domain FROM sites WHERE server_id=? AND status!='creating'", (server_id,))
                 if name in provision.site_apps(s, r, x["domain"])]
        users += [d for d in provision.list_bench_sites(s, r) if d not in users and d != "assets" and name in provision.site_apps(s, r, d)]
        if users:
            raise ssh.SSHError(f"{name} is still installed on {', '.join(users)}. Remove it from those sites first (Site → Apps → Remove).")
        log(f">>> Removing {name} from {s['name']}\n")
        code, _ = r.run(_bench(s, f"bench remove-app {shlex.quote(name)} --force"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"bench remove-app {name} failed (exit {code})")
        r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER)
        provision.sync_server(s, r, log)
    log(f"\n{name} removed from {s['name']}.\n")


def _git(r, s, app, args, stream=False, timeout=600):
    return r.run(_bench(s, f"git -C {shlex.quote('apps/' + app)} {args}"), as_user=BENCH_USER, stream=stream, timeout=timeout)


def _pull_app(r, s, app, force, log):
    """Bring one app's code to the remote branch tip. A clean (deployed) copy is simply moved to the remote state, which also
    works when the history diverged (shallow clones, force-pushed branches). Edits made on the server need force."""
    code, out = _git(r, s, app, "status --porcelain -uno")
    if code != 0:
        raise ssh.SSHError(f"{app}: apps/{app} is not a git repository on the server")
    if out.strip() and not force:
        raise ssh.SSHError(f"{app} has changes made directly on the server:\n{out.strip()[:400]}\n"
                           "Tick 'Overwrite changes made on the server' to replace them with the repository version.")
    code, out = _git(r, s, app, "remote")
    remotes = out.split()
    remote = "upstream" if "upstream" in remotes or not remotes else remotes[0]
    code, out = _git(r, s, app, "rev-parse --abbrev-ref HEAD")
    branch = out.strip().splitlines()[-1] if out.strip() else ""
    if code != 0 or not branch or branch == "HEAD":
        raise ssh.SSHError(f"{app} is not on a branch on the server (detached HEAD); fix it manually with git checkout")
    log(f"\n>>> {app}: fetching {remote}/{branch}\n")
    # fetch into a named remote-tracking ref instead of FETCH_HEAD: FETCH_HEAD is not reliable on shallow clones or after a
    # repository change, and a named ref can be checked before anything is reset
    ref = f"refs/remotes/{remote}/{branch}"
    code, out = _git(r, s, app, f"fetch --force {shlex.quote(remote)} {shlex.quote('+refs/heads/' + branch + ':' + ref)}", stream=True, timeout=1800)
    if code != 0:
        raise ssh.SSHError(f"git fetch failed for {app} (exit {code}). Does the branch '{branch}' exist in the repository?")
    code, _ = _git(r, s, app, f"rev-parse --verify --quiet {shlex.quote(ref + '^{commit}')}")
    if code != 0:
        raise ssh.SSHError(f"{app}: the repository has no commits on branch '{branch}' (is it empty, or is the branch name different? "
                           "Check the branch under Apps).")
    ff, _ = _git(r, s, app, f"merge-base --is-ancestor HEAD {shlex.quote(ref)}")
    if ff != 0:
        log(f"{app}: the server's history differs from the repository's; using the repository version.\n")
    code, out = _git(r, s, app, f"reset --hard {shlex.quote(ref)}", stream=True)
    if code != 0:
        raise ssh.SSHError(f"git reset failed for {app} (exit {code}): {out.strip()[-300:]}")


def update_apps_job(site_id, names, log, force=False):
    """Pull the latest code of the given apps (shared by every site on the server), rebuild, then migrate this site.
    Other sites on the server pick up the new code at their next migrate."""
    site, s = get(site_id)
    domain = site["domain"]
    clean = [n for n in names if NAME_RE.match(n)]
    if not clean:
        raise OpError("Choose at least one app to update")
    with ssh.Runner(s, log) as r:
        log(f">>> Backing up {domain} before updating\n")
        _run(r, s, domain, "backup --with-files", "Safety backup")
        for n in clean:
            _pull_app(r, s, n, force, log)
        log("\n>>> Installing requirements\n")
        code, _ = r.run(_bench(s, "bench setup requirements"), as_user=BENCH_USER, timeout=3600)
        if code != 0:
            raise ssh.SSHError(f"bench setup requirements failed (exit {code}). The code was updated but the site was not migrated; the pre-update backup is on the Backups tab.")
        log("\n>>> Building assets\n")
        code, _ = r.run(_bench(s, f"bench build --apps {shlex.quote(','.join(clean))}"), as_user=BENCH_USER, timeout=3600)
        if code != 0:
            raise ssh.SSHError(f"bench build failed (exit {code}). Check the log above.")
        log(f"\n>>> Migrating {domain}\n")
        code, _ = r.run(_site_cmd(s, domain, "migrate"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"bench migrate failed (exit {code}). The pre-update backup is on the Backups tab.")
        r.run(_site_cmd(s, domain, "clear-cache"), as_user=BENCH_USER, stream=False)
        r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER)
        provision.sync_server(s, r, log)
        _store_apps(s, r, site)
    log("\nUpdate finished.\n")


RESERVED_APPS = {"frappe", "erpnext", "hrms", "payments", "lending", "healthcare", "education", "webshop", "crm", "helpdesk", "insights", "builder", "print_designer", "test", "tests"}


def empty_app_name(domain):
    """Python-module-safe name from the site's subdomain: test9.example.com -> app_test9 (a leading digit is not a valid module name)."""
    n = re.sub(r"[^a-z0-9]+", "_", domain.split(".")[0].lower()).strip("_") or "site"
    if not n[0].isalpha():
        n = "app_" + n
    if n in RESERVED_APPS:
        n += "_app"
    return n[:60]


def empty_app_job(site_id, log):
    """bench new-app (answers the prompts), then install it on this site."""
    site, s = get(site_id)
    domain, name = site["domain"], empty_app_name(site["domain"])
    with ssh.Runner(s, log) as r:
        installed = set(provision.site_apps(s, r, domain))
        if name in installed:
            log(f"The app '{name}' is already installed on {domain}.\n")
            return
        if name in set(provision.list_bench_apps(s, r)):
            log(f">>> App '{name}' already exists on the server; installing it on the site\n")
        else:
            log(f">>> Creating empty app '{name}'\n")
            answers = " ".join(shlex.quote(a) for a in (name.replace("_", " ").title(), f"Custom app for {domain}", "Fleet Manager", "admin@example.com", "", "", "mit"))
            # prompts: title, description, publisher, email, icon, color, license, then optional extras -> defaults
            cmd = f"{{ printf '%s\\n' {answers}; yes ''; }} | bench new-app {shlex.quote(name)}"
            code, _ = r.run(_bench(s, cmd), as_user=BENCH_USER)
            if code != 0:
                raise ssh.SSHError(f"bench new-app failed (exit {code})")
        log(f"\n>>> Backing up {domain} before installing\n")
        _run(r, s, domain, "backup --with-files", "Safety backup")
        log(f"\n>>> Installing {name} on {domain}\n")
        code, _ = r.run(_site_cmd(s, domain, f"install-app {shlex.quote(name)}"), as_user=BENCH_USER)
        if code != 0:
            raise ssh.SSHError(f"install-app {name} failed (exit {code})")
        r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER)
        provision.sync_server(s, r, log)
        _store_apps(s, r, site)
    log(f"\nEmpty app '{name}' created and installed. Its code is in apps/{name} on the server.\n")


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
        drop = _bench(s, f"bench drop-site {shlex.quote(site['domain'])} --force --no-backup --db-root-password {shlex.quote(pw)}")
        site_dir = f"{s['bench_path']}/sites/{site['domain']}"

        def gone(rr):
            code, _ = rr.run(f"test -d {shlex.quote(site_dir)}", as_user=BENCH_USER, stream=False)
            return code != 0

        code, out = -1, ""
        for attempt in (1, 2):
            try:
                code, out = r.run(drop, as_user=BENCH_USER, timeout=900)
            except ssh.SSHError as e:
                code, out = -1, str(e)
            if code == 0:
                break
            # exit -1 / dropped connection: the command may well have finished. Look at the server before deciding.
            log(f"\n!! drop-site ended with exit {code}; checking what happened on the server…\n")
            r.close()
            r.connect()
            if gone(r):
                log("The site folder is gone, so the deletion went through.\n")
                code = 0
                break
            if attempt == 1:
                log("The site is still there; trying once more.\n")
        if code != 0:
            raise ssh.SSHError(f"drop-site failed (exit {code}). {out.strip()[-400:]}")
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
