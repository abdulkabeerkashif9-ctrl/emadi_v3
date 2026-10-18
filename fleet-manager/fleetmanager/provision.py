"""Everything that actually touches a VPS: bootstrap script, configuring, metrics, sites, apps."""
import ast
import json
import shlex

from . import config, cpanel, db, domains, security, ssh

BENCH_USER = "frappe"

# A fresh VPS runs unattended-upgrades (sometimes stuck for hours) and holds the apt lock; stop it, repair, and go on.
APT_PREP = """# a fresh VPS runs unattended-upgrades; make apt calls wait for the lock, and stop the updater if it is holding it
mkdir -p /etc/apt/apt.conf.d && echo 'DPkg::Lock::Timeout "900";' > /etc/apt/apt.conf.d/99fleet-lock
systemctl stop apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
if pgrep -f unattended-upgr >/dev/null 2>&1; then
  echo "Stopping unattended-upgrades (it holds the package lock)..."
  timeout 60 systemctl stop unattended-upgrades 2>/dev/null || true
  pkill -f unattended-upgr 2>/dev/null || true
  sleep 3
  dpkg --configure -a || true
fi
"""


# ---------------------------------------------------------------- bootstrap script (given to the user)
def bootstrap_script(server):
    pub = ssh.manager_public_key()
    return f"""#!/usr/bin/env bash
# Fleet Manager bootstrap for "{server['name']}" ({server['ip']}) - run ONCE as root on the new VPS:
#   sudo bash bootstrap.sh
# It installs the minimum needed so Fleet Manager can log in over SSH and configure the rest.
set -euo pipefail
[ "$(id -u)" = 0 ] || {{ echo "Run as root (sudo bash bootstrap.sh)"; exit 1; }}
. /etc/os-release
case "$ID $VERSION_ID" in
  "ubuntu 22.04"|"ubuntu 24.04") ;;
  *) echo "WARNING: tested on Ubuntu 22.04/24.04 only (found $PRETTY_NAME)";;
esac
export DEBIAN_FRONTEND=noninteractive
{APT_PREP}apt-get update -y
apt-get install -y openssh-server sudo curl ca-certificates ufw
systemctl enable --now ssh || systemctl enable --now sshd || true

# let Fleet Manager log in with its own key, as the SSH user entered in the app
TARGET="{server['ssh_user']}"
id "$TARGET" >/dev/null 2>&1 || {{ echo "User $TARGET does not exist on this VPS"; exit 1; }}
HOME_DIR=$(getent passwd "$TARGET" | cut -d: -f6)
install -d -m 700 -o "$TARGET" -g "$(id -gn "$TARGET")" "$HOME_DIR/.ssh"
touch "$HOME_DIR/.ssh/authorized_keys"
chown "$TARGET": "$HOME_DIR/.ssh/authorized_keys"; chmod 600 "$HOME_DIR/.ssh/authorized_keys"
grep -qF "{pub}" "$HOME_DIR/.ssh/authorized_keys" || echo "{pub}" >> "$HOME_DIR/.ssh/authorized_keys"

# keep SSH reachable if the firewall is enabled later
ufw allow {server['ssh_port']}/tcp >/dev/null 2>&1 || true

echo
echo "Bootstrap done on $(hostname) - $PRETTY_NAME - $(nproc) CPU, $(free -m | awk '/Mem:/{{print $2}}') MB RAM"
echo "Now go back to Fleet Manager and press 'Configure server'."
"""


# ---------------------------------------------------------------- configure script (run by the app)
def configure_script(server, db_root_pw):
    v = config.VERSIONS[server["version"]]
    py, node = v["python"], v["node"]
    return f"""#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
{APT_PREP}. /etc/os-release
echo "== OS: $PRETTY_NAME"
[ "$ID" = ubuntu ] || {{ echo "Only Ubuntu 22.04/24.04 is supported"; exit 1; }}

echo "== [1/9] System packages"
apt-get update -y
apt-get install -y git curl wget ca-certificates software-properties-common build-essential \\
  python3-dev python3-setuptools python3-pip python3-venv pipx redis-server \\
  mariadb-server mariadb-client libmariadb-dev pkg-config libffi-dev libssl-dev \\
  xvfb libfontconfig fontconfig libxrender1 libxext6 xfonts-75dpi xfonts-base \\
  nginx supervisor cron ufw openssl certbot fail2ban ansible-core

echo "== [2/9] Swap (if RAM is small)"
if [ "$(free -m | awk '/Mem:/{{print $2}}')" -lt 3800 ] && [ -z "$(swapon --show --noheadings)" ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "== [3/9] Python {py}"
if ! command -v python{py} >/dev/null; then
  add-apt-repository -y ppa:deadsnakes/ppa && apt-get update -y
  apt-get install -y python{py} python{py}-venv python{py}-dev
fi

echo "== [4/9] Node {node} + yarn"
if ! node -v 2>/dev/null | grep -q '^v{node}\\.'; then
  curl -fsSL https://deb.nodesource.com/setup_{node}.x | bash -
  apt-get install -y nodejs
fi
command -v yarn >/dev/null || npm install -g yarn

echo "== [5/9] wkhtmltopdf (patched qt)"
if ! wkhtmltopdf --version 2>/dev/null | grep -q 'with patched qt'; then
  CN=${{VERSION_CODENAME:-jammy}}; ARCH=$(dpkg --print-architecture)
  URL=https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.${{CN}}_${{ARCH}}.deb
  wget -q -O /tmp/wk.deb "$URL" || wget -q -O /tmp/wk.deb "${{URL/$CN/jammy}}"
  apt-get install -y /tmp/wk.deb
fi

echo "== [6/9] MariaDB"
cat > /etc/mysql/mariadb.conf.d/99-frappe.cnf <<'CNF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
[mysql]
default-character-set = utf8mb4
CNF
systemctl enable --now mariadb && systemctl restart mariadb
# always (re)apply: a socket-auth login ignores the password, so "does the password work?" can't be tested as OS root
mariadb -e "ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD('{db_root_pw}'); FLUSH PRIVILEGES;"
mariadb -uroot -p'{db_root_pw}' -h127.0.0.1 -e 'select 1' >/dev/null && echo "MariaDB root password OK over TCP"
systemctl enable --now redis-server

echo "== [7/9] '{BENCH_USER}' user"
id {BENCH_USER} >/dev/null 2>&1 || adduser --disabled-password --gecos "" {BENCH_USER}
echo '{BENCH_USER} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-{BENCH_USER}; chmod 440 /etc/sudoers.d/90-{BENCH_USER}
chmod o+x /home/{BENCH_USER}

echo "== [8/9] bench + {server['version']} (this takes the longest)"
sudo -u {BENCH_USER} -H bash -lc '
  set -euo pipefail
  export PATH=$HOME/.local/bin:$PATH
  grep -q ".local/bin" ~/.profile || echo "export PATH=\\$HOME/.local/bin:\\$PATH" >> ~/.profile
  command -v uv >/dev/null || pipx install uv
  command -v bench >/dev/null || pipx install frappe-bench
  cd ~
  if [ ! -d frappe-bench/apps/frappe ]; then
    rm -rf frappe-bench   # leftover from a failed earlier attempt
    bench init frappe-bench --frappe-branch {server['version']} --python python{py} --verbose </dev/null
  fi
  cd frappe-bench
  bench config dns_multitenant on
'

echo "== [9/9] Production (nginx + supervisor) and firewall"
cd /home/{BENCH_USER}/frappe-bench
env PATH=/home/{BENCH_USER}/.local/bin:$PATH bench setup production {BENCH_USER} --yes
# allow every port sshd really listens on (providers often forward a custom public port to 22), plus the configured one
for p in {server['ssh_port']} 22 $(ss -H -tlnp 2>/dev/null | awk '/sshd/{{n=split($4,a,":"); print a[n]}}' | sort -u); do
  ufw allow "$p"/tcp
done
ufw allow 80/tcp; ufw allow 443/tcp; ufw --force enable
systemctl start apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
echo "== DONE"
"""


# ---------------------------------------------------------------- helpers
def _bench(server, cmd):
    return f"cd {shlex.quote(server['bench_path'])} && export PATH=$HOME/.local/bin:$PATH && {cmd}"


def configure_server(server_id, log):
    s = db.q1("SELECT * FROM servers WHERE id=?", (server_id,))
    db.x("UPDATE servers SET status='configuring', last_error=NULL WHERE id=?", (server_id,))
    try:
        pw = security.decrypt(s["db_root_pw_enc"])
        if not pw:
            pw = security.gen_password()
            db.x("UPDATE servers SET db_root_pw_enc=? WHERE id=?", (security.encrypt(pw), server_id))
        with ssh.Runner(s, log) as r:
            log("Connected. Uploading configure script...\n")
            path = "/tmp/fleet_configure.sh"
            r.write_file(path, configure_script(s, pw), 0o700)
            code, _ = r.run(f"bash {path}; rc=$?; rm -f {path}; exit $rc", sudo=True)
            if code != 0:
                raise ssh.SSHError(f"Configure script failed (exit {code})")
            sync_server(s, r, log)
        db.x("UPDATE servers SET status='ready' WHERE id=?", (server_id,))
        log("\nServer is ready.\n")
    except Exception as e:
        db.x("UPDATE servers SET status='error', last_error=? WHERE id=?", (str(e), server_id))
        raise


def collect_metrics(r):
    code, out = r.run(
        "echo LOAD $(cut -d' ' -f1 /proc/loadavg); echo CORES $(nproc); "
        "free -m | awk '/Mem:/{print \"MEM\",$2,$3}'; df -P / | awk 'NR==2{gsub(\"%\",\"\",$5); print \"DISK\",$5}'; "
        ". /etc/os-release; echo OS $PRETTY_NAME", stream=False)
    m = {}
    for line in out.splitlines():
        p = line.split(None, 1)
        if len(p) < 2:
            continue
        k, v = p
        if k == "LOAD":
            m["load"] = float(v)
        elif k == "CORES":
            m["cores"] = int(v)
        elif k == "MEM":
            tot, used = (int(i) for i in v.split())
            m["mem_total_mb"], m["mem_pct"] = tot, round(100 * used / tot)
        elif k == "DISK":
            m["disk_pct"] = int(v)
        elif k == "OS":
            m["os"] = v
    return m


def list_bench_apps(s, r):
    code, out = r.run(f"ls -1 {shlex.quote(s['bench_path'])}/apps 2>/dev/null", as_user=BENCH_USER, stream=False)
    return [a.strip() for a in out.splitlines() if a.strip() and a.strip() != "frappe" and "/" not in a] if code == 0 else []


def list_bench_sites(s, r):
    code, out = r.run(
        f"cd {shlex.quote(s['bench_path'])}/sites 2>/dev/null && for d in */; do d=${{d%/}}; "
        "[ -f \"$d/site_config.json\" ] && echo $d; done", as_user=BENCH_USER, stream=False)
    return [x.strip() for x in out.splitlines() if x.strip()] if code == 0 else []


COMPANY_KWARGS = "{'doctype': 'Company', 'pluck': 'name', 'limit': 1}"


def site_company(s, r, domain):
    code, out = r.run(_bench(s, f"bench --site {shlex.quote(domain)} execute frappe.get_all "
                                f"--kwargs {shlex.quote(COMPANY_KWARGS)}"), as_user=BENCH_USER, stream=False)
    for line in reversed(out.strip().splitlines()):
        try:
            v = json.loads(line)
        except ValueError:
            try:
                v = ast.literal_eval(line)
            except Exception:
                continue
        if isinstance(v, list):
            return v[0] if v else None
    return None


def site_apps(s, r, domain):
    code, out = r.run(_bench(s, f"bench --site {shlex.quote(domain)} list-apps"), as_user=BENCH_USER, stream=False)
    return [l.split()[0] for l in out.splitlines() if l.strip() and code == 0 and not l.startswith(("Error", "Traceback"))]


def sync_server(s, r, log=lambda _t: None):
    """Refresh metrics, installed apps and the site list from the server."""
    import time
    m = collect_metrics(r)
    apps = list_bench_apps(s, r)
    db.x("DELETE FROM server_apps WHERE server_id=?", (s["id"],))
    for a in apps:
        db.x("INSERT INTO server_apps VALUES(?,?)", (s["id"], a))
    db.x("UPDATE servers SET metrics=?, metrics_at=?, os_info=? WHERE id=?",
         (json.dumps(m), time.strftime("%Y-%m-%d %H:%M:%S"), m.get("os"), s["id"]))
    if not apps and not list_bench_sites(s, r):
        return
    remote = list_bench_sites(s, r)
    known = {x["domain"]: x for x in db.q("SELECT * FROM sites WHERE server_id=?", (s["id"],))}
    for d in remote:
        if d not in known and d not in ("assets",):
            log(f"Found existing site {d}\n")
            db.x("INSERT OR IGNORE INTO sites(server_id,domain,apps,status) VALUES(?,?,?,'up')",
                 (s["id"], d, ",".join(site_apps(s, r, d))))
    for d in set(known) | set(remote):
        if d in remote:
            c = site_company(s, r, d)
            if c:
                db.x("UPDATE sites SET company=? WHERE server_id=? AND domain=?", (c, s["id"], d))
    for d in set(known) - set(remote):
        if known[d]["status"] != "creating":
            db.x("UPDATE sites SET status='error' WHERE id=?", (known[d]["id"],))


def refresh_server(server_id, log=lambda _t: None):
    s = db.q1("SELECT * FROM servers WHERE id=?", (server_id,))
    with ssh.Runner(s, log) as r:
        sync_server(s, r, log)
    check_sites(server_id)


def check_sites(server_id):
    import requests, time
    s = db.q1("SELECT * FROM servers WHERE id=?", (server_id,))
    for site in db.q("SELECT * FROM sites WHERE server_id=? AND status!='creating'", (server_id,)):
        try:
            resp = requests.get(f"http://{s['ip']}/", headers={"Host": site["domain"]}, timeout=6, allow_redirects=False)
            code, ok = resp.status_code, resp.status_code < 400
        except requests.RequestException:
            code, ok = None, False
        db.x("UPDATE sites SET status=?, http_code=?, checked_at=? WHERE id=?",
             ("up" if ok else "down", code, time.strftime("%Y-%m-%d %H:%M:%S"), site["id"]))


# ---------------------------------------------------------------- recommendation
def server_capacity(s):
    m = json.loads(s["metrics"]) if s.get("metrics") else None
    if not m:
        return {"known": False, "ok": False, "score": 999, "reasons": ["no metrics yet - press Refresh"]}
    per_core = m["load"] / max(m["cores"], 1)
    reasons = []
    if per_core > config.MAX_LOAD_PER_CORE: reasons.append(f"CPU load {per_core:.2f}/core")
    if m["mem_pct"] > config.MAX_MEM_PCT: reasons.append(f"RAM {m['mem_pct']}% used")
    if m["disk_pct"] > config.MAX_DISK_PCT: reasons.append(f"disk {m['disk_pct']}% used")
    n_sites = db.q1("SELECT COUNT(*) n FROM sites WHERE server_id=?", (s["id"],))["n"]
    if m["mem_total_mb"] and n_sites * 700 > m["mem_total_mb"] * 1.5:
        reasons.append(f"{n_sites} sites on {m['mem_total_mb']} MB RAM")
    score = 40 * per_core / config.MAX_LOAD_PER_CORE + 0.35 * m["mem_pct"] + 0.15 * m["disk_pct"] + 2 * n_sites
    return {"known": True, "ok": not reasons, "score": round(score, 1), "reasons": reasons, "sites": n_sites, "metrics": m}


def recommend():
    out = []
    for s in db.q("SELECT * FROM servers WHERE status='ready'"):
        cap = server_capacity(s)
        out.append({"id": s["id"], "name": s["name"], "ip": s["ip"], "version": s["version"], **cap})
    out.sort(key=lambda x: (not x["ok"], x["score"]))
    for i, o in enumerate(out):
        o["recommended"] = i == 0 and o["ok"]
    return out


# ---------------------------------------------------------------- apps & sites
def order_apps(names):
    """Add required apps and sort so dependencies install first."""
    reg = {a["name"]: a for a in db.q("SELECT * FROM apps")}
    out = []

    def visit(n):
        if n in out or n == "frappe":
            return
        if n not in reg:
            raise ValueError(f"Unknown app '{n}'")
        for dep in filter(None, (reg[n]["requires"] or "").split(",")):
            visit(dep.strip())
        out.append(n)
    for n in names:
        visit(n)
    return out


def missing_on_server(server_id, names):
    have = {r["app_name"] for r in db.q("SELECT app_name FROM server_apps WHERE server_id=?", (server_id,))}
    return [n for n in order_apps(names) if n not in have]


def get_app(s, r, name, log):
    a = db.q1("SELECT * FROM apps WHERE name=?", (name,))
    branch = a["branch"] or s["version"]
    log(f"\n>>> Fetching app {name} ({a['git_url']} @ {branch})\n")
    code, _ = r.run(_bench(s, f"bench get-app --branch {shlex.quote(branch)} {shlex.quote(a['git_url'])}"),
                    as_user=BENCH_USER)
    if code != 0:
        raise ssh.SSHError(f"bench get-app failed for {name} (exit {code}). Check the git URL/branch in Apps.")
    db.x("INSERT OR IGNORE INTO server_apps VALUES(?,?)", (s["id"], name))


REDIS_PORTS = (11000, 13000)  # bench's own redis queue / cache (not the system redis on 6379)


def _redis_up(r):
    chk = " && ".join(f"(echo > /dev/tcp/127.0.0.1/{p}) 2>/dev/null" for p in REDIS_PORTS)
    return r.run(chk, stream=False)[0] == 0


def ensure_bench_services(r, s, log):
    """bench needs its redis instances (run by supervisor) before new-site/install-app can enqueue jobs."""
    if _redis_up(r):
        return
    log("\n>>> Bench redis is not running; (re)starting bench services via supervisor\n")
    r.run(_bench(s, "bench setup supervisor --yes"), as_user=BENCH_USER)
    r.run("systemctl enable --now supervisor 2>/dev/null; supervisorctl reread; supervisorctl update; "
          "supervisorctl restart all; sleep 8", sudo=True)
    if not _redis_up(r):
        _, st = r.run("supervisorctl status 2>&1 | head -30; ss -tlnp | grep -E ':(11000|13000) ' || true", sudo=True, stream=False)
        raise RuntimeError("Bench redis still not reachable on ports 11000/13000. supervisor says:\n" + st)
    log("Bench services are up.\n")


def ensure_db_root_password(r, s):
    """Make sure MariaDB root accepts the stored password over TCP (what bench new-site uses)."""
    pw = security.decrypt(s["db_root_pw_enc"])
    sql = (f"ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket OR mysql_native_password "
           f"USING PASSWORD('{pw}'); FLUSH PRIVILEGES;")
    code, out = r.run(f"mariadb -e {shlex.quote(sql)}", sudo=True, stream=False)
    if code != 0:
        raise ssh.SSHError(f"Could not set the MariaDB root password: {out.strip()[:300]}")


def create_site(site_id, log, install_missing=True, add_dns=False, enable_ssl=False):
    site = db.q1("SELECT * FROM sites WHERE id=?", (site_id,))
    s = db.q1("SELECT * FROM servers WHERE id=?", (site["server_id"],))
    domain = site["domain"]
    apps = order_apps([a for a in site["apps"].split(",") if a])
    try:
        if add_dns:
            zone = cpanel.zone_for(domain)
            if not zone:
                raise RuntimeError(f"{domain} is not in the connected cPanel account")
            have = cpanel.find_records(zone, domain)
            if any(x["type"] == "A" and x["value"] == s["ip"] for x in have):
                log(f">>> DNS: A record {domain} -> {s['ip']} already exists, leaving it\n")
            elif have:
                raise RuntimeError(f"DNS already has {', '.join(x['type'] + ' ' + x['value'] for x in have)} for {domain}; "
                                   "remove it in cPanel Zone Editor first, or create the site without the DNS option")
            else:
                cpanel.add_a_record(zone, domain, s["ip"])
                log(f">>> DNS: created A record {domain} -> {s['ip']} in {zone}\n")
        with ssh.Runner(s, log) as r:
            have = set(list_bench_apps(s, r))
            for n in apps:
                if n not in have:
                    if not install_missing:
                        raise RuntimeError(f"App {n} is not on the server")
                    get_app(s, r, n, log)
            if set(apps) - have:
                log("\n>>> Restarting bench services to load new apps\n")
                r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER)
            ensure_db_root_password(r, s)
            ensure_bench_services(r, s, log)
            site_dir = shlex.quote(f"{s['bench_path']}/sites/{domain}")
            if r.run(f"test -d {site_dir}", as_user=BENCH_USER, stream=False)[0] == 0:
                if r.run(f"test -f {site_dir}/site_config.json", as_user=BENCH_USER, stream=False)[0] == 0:
                    raise RuntimeError(f"A working site named {domain} already exists on this server. "
                                       "Refresh the server to import it instead of creating it.")
                log(f"\n>>> Removing leftover folder from a failed earlier attempt for {domain}\n")
                r.run(f"rm -rf {site_dir}", as_user=BENCH_USER, check=True, stream=False)
            log(f"\n>>> Creating site {domain} (a few minutes)\n")
            code, _ = r.run(_bench(s, f"bench new-site {shlex.quote(domain)} "
                                      f"--db-root-password {shlex.quote(security.decrypt(s['db_root_pw_enc']))} "
                                      f"--admin-password {shlex.quote(security.decrypt(site['admin_pw_enc']))}"),
                            as_user=BENCH_USER)
            if code != 0:
                raise ssh.SSHError(f"bench new-site failed (exit {code})")
            try:
                for n in apps:
                    log(f"\n>>> Installing {n} on {domain}\n")
                    code, _ = r.run(_bench(s, f"bench --site {shlex.quote(domain)} install-app {shlex.quote(n)}"), as_user=BENCH_USER)
                    if code != 0:
                        raise ssh.SSHError(f"install-app {n} failed (exit {code})")
                log("\n>>> Configuring nginx\n")
                r.run(_bench(s, "bench setup nginx --yes && sudo systemctl reload nginx"), as_user=BENCH_USER, check=True)
            except Exception:
                # we created this site a moment ago in this job, so it is safe to remove the half-built remains
                log(f"\n>>> Rolling back: removing the incomplete site {domain}\n")
                r.run(_bench(s, f"bench drop-site {shlex.quote(domain)} --force --no-backup "
                                f"--db-root-password {shlex.quote(security.decrypt(s['db_root_pw_enc']))}"),
                      as_user=BENCH_USER, stream=False)
                raise
            if enable_ssl:
                if s["ip"] in domains.resolve(domain):
                    log("\n>>> Requesting Let's Encrypt certificate\n")
                    code, _ = r.run(_bench(s, f"sudo env PATH=$PATH bench setup lets-encrypt {shlex.quote(domain)} --non-interactive"),
                                    as_user=BENCH_USER)
                    if code == 0:
                        db.x("UPDATE sites SET ssl=1 WHERE id=?", (site_id,))
                    else:
                        log("!! SSL failed - the site works over HTTP; retry later.\n")
                else:
                    log(f"!! Skipping SSL: {domain} does not resolve to {s['ip']} yet.\n")
            sync_server(s, r, log)
        db.x("UPDATE sites SET status='up' WHERE id=?", (site_id,))
        check_sites(s["id"])
        log(f"\nSite ready: http://{domain}  (login: Administrator, password shown in the Sites page)\n")
    except Exception:
        db.x("UPDATE sites SET status='error' WHERE id=?", (site_id,))
        raise


def install_apps_on_server(server_id, names, log):
    s = db.q1("SELECT * FROM servers WHERE id=?", (server_id,))
    with ssh.Runner(s, log) as r:
        have = set(list_bench_apps(s, r))
        for n in order_apps(names):
            if n not in have:
                get_app(s, r, n, log)
        r.run(_bench(s, "bench restart || true"), as_user=BENCH_USER)
        sync_server(s, r, log)
