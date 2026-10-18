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

## Notes / limitations

* "Company" shows what you typed at creation until the ERPNext setup wizard has been completed in the browser; after that the real Company record is read from the site on each refresh.
* Version → Python/Node mapping is in `fleetmanager/config.py` (v16 values especially should be verified). App branches are editable on the Apps page.
* Removing a site/server in the UI only forgets it here; nothing is deleted on the VPS.
* SSH host keys are pinned on first connect; a changed key blocks connections until you re-save the server with its IP.
* Passphrase-protected private keys are not supported.
* The configure script gives the `frappe` user passwordless sudo (standard for bench production setups).

## Tests

`pip install -r requirements.txt && pytest` — covers the API flow with a fake VPS and the SSH layer against an in-process SSH server. The provisioning scripts have **not** yet been run against a real VPS; do that first on your test VPS and report failures from the job log.
