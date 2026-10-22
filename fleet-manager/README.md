# ERP Fleet Manager

Browser UI (runs on your laptop) to manage ERPNext sites across your VPS servers and the thesmarterp.com cPanel.

## Run

Needs Python 3.10+.  Windows: double-click `start.bat`.  Linux/macOS: `./start.sh`.
Open http://localhost:8800 — on first run you create the admin account.

Data (SQLite DB, encryption key, the SSH key the app uses) lives in `data/`. **Back it up; never commit it.**
The server listens on 127.0.0.1 only. Put HTTPS in front of it (reverse proxy) before exposing it with `--host 0.0.0.0`.

## Workflow

1. **Settings** → enter cPanel host, username and an API token (cPanel → Security → Manage API Tokens). Used for domain checks and DNS A records.
2. **Servers → Add VPS**: name, IP, SSH user (root or a sudo user), password or private key, ERPNext version.
   1. *Bootstrap file* – shows a script to run once on the VPS (installs SSH/sudo, authorises this app's key).
   2. *Test SSH*, then *Configure server* – installs MariaDB, Redis, Nginx, Supervisor, Node, wkhtmltopdf, bench, creates the `frappe` user and a production bench. Takes 15–30 min; live log in the UI. Ubuntu 22.04/24.04 only.
3. **Apps** – official Frappe apps are pre-registered. *New app* → git URL (+ branch, + required apps) to add your own.
4. **Sites → New site**: domain (checked against your fleet, DNS and cPanel) → server (least-loaded is recommended; busy ones are flagged; you can override) → apps. If an app isn't on the chosen server you're asked whether to install it there too. Optionally creates the DNS A record in cPanel and a Let's Encrypt certificate. The Administrator password is shown under *Login* on the Sites page.
5. **Sites** dashboard lists domain, company, server IP, apps and live HTTP status. Existing sites on a server are discovered when you refresh it.

## Team, roles and safety

* **Roles** (Settings → Team): *Viewer* reads everything but sees no passwords or logs; *Support* runs day-to-day work (create sites, backups, logs, notes, customers, reset passwords); *Admin* also manages servers, apps, team, settings and deletions.
* **Approvals:** a Support user who asks to delete a site creates a request; an Admin approves or rejects it (Approvals page). Deletions always need the typed domain and a reason, and take a backup first by default.
* **Audit log:** every login, view of credentials and change is recorded with user, time and IP. Passwords are never recorded.
* Upgrading from an older version keeps your data; existing accounts become Admins automatically.

## Site page (for support agents)

Overview (go-live checklist, customer), Operations (maintenance mode, clear cache, migrate, reset Administrator password, backup, extra domain, suspend/reactivate, rename, delete), Backups (list + download), Logs (site, web, worker, scheduler, nginx; filter and auto-refresh), Notes, Apps, Activity. **Open as Administrator** signs in with one click using the stored password.

**Go-live checklist / provider gateway:** tick *Behind a provider gateway* on a server whose VPS has a private address (provider routes web traffic). Each site then shows the exact values to add in the provider's panel and checks DNS and public reachability.

## Notes / limitations

* "Company" shows what you typed at creation until the ERPNext setup wizard has been completed in the browser; after that the real Company record is read from the site on each refresh.
* Version → Python/Node mapping is in `fleetmanager/config.py` (v16 values especially should be verified). App branches are editable on the Apps page.
* Removing a site/server in the UI only forgets it here; nothing is deleted on the VPS.
* SSH host keys are pinned on first connect; a changed key blocks connections until you re-save the server with its IP.
* Passphrase-protected private keys are not supported.
* The configure script gives the `frappe` user passwordless sudo (standard for bench production setups).

## Tests

`pip install -r requirements.txt && pytest` — covers the API flow with a fake VPS and the SSH layer against an in-process SSH server. The provisioning scripts have **not** yet been run against a real VPS; do that first on your test VPS and report failures from the job log.

## Backups, restore and moving sites

**Backups** (support and up) shows every site's last backup, schedule and next run.

- **Schedules**: a default schedule (daily/weekly/every N hours, with retention) applies to all sites; an admin can give a site its own. Old backups are pruned automatically (`keep` on the server, `keep_offsite` offsite).
- **Offsite copy**: Settings → Backup storage takes any S3-compatible bucket (AWS, Backblaze B2, Wasabi, R2, MinIO…) or an SFTP server. Each VPS uploads directly with `rclone`, which is installed automatically on first use. Use **Test** to prove the credentials.
- **Restore**: site → Backups → *Restore…* from the server or from offsite. You must give a reason and type the domain. A safety backup of the current state is taken first. Support staff send a request that an admin approves under Approvals.
- **Move to another server** (admin): site → Operations. The site is backed up, copied through this computer to a server running the same ERPNext version, and restored there. The original stays untouched; then point DNS (and the provider panel) at the new server.

## Monitoring and alerts

**Monitoring** shows uptime (24 h / 7 d / 30 d), a 24-hour bar per site, server CPU/memory/disk, HTTPS certificate expiry and open incidents. Sites are checked from the public internet every minute, servers over SSH every 5 minutes.

- An incident opens after 3 failed checks and closes after 2 good ones. Staff can **Acknowledge** or **Close** it; reminders repeat every 60 minutes.
- Settings → Alerts: send alerts to **Telegram**, **email (SMTP)** and/or a **webhook** (Slack, Discord, Teams or a WhatsApp gateway). Thresholds and an optional **Auto-heal** (restart the server's services once per incident) are configured there.

> Schedules, monitoring and alerts only run while Fleet Manager is running — keep it on a machine that is always on.

## Installing and updating apps on an existing site

Site → **Apps**: *Install app* adds registry apps to the site (downloading them to the server first if needed); ticking apps and pressing *Update selected* pulls their newest code and migrates the site. Both take a backup first. App code is shared by every site on a server, so an update reaches all of them (they migrate when next migrated).

## Upload database and empty app

- **Upload database** (admin; site → Operations): upload a `.sql` or `.sql.gz` dump and it replaces the site's data. A safety backup is taken first, and the site is in maintenance mode while it loads. The Administrator password becomes the one stored in the dump.
- **Create & install empty app** (site → Apps): creates a blank app named after the site's subdomain (`test9.example.com` → `test9`; names starting with a digit get an `app_` prefix) and installs it on the site.
