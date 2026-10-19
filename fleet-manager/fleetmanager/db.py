import sqlite3
import threading
from contextlib import contextmanager

from . import config

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS servers(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, ip TEXT NOT NULL, ssh_port INTEGER DEFAULT 22,
  ssh_user TEXT NOT NULL, auth_type TEXT NOT NULL,           -- 'password' | 'key'
  secret_enc TEXT,                                           -- encrypted password or private key
  version TEXT NOT NULL, status TEXT DEFAULT 'new',         -- new|bootstrapped|configuring|ready|error
  host_fingerprint TEXT, bench_path TEXT DEFAULT '/home/frappe/frappe-bench',
  db_root_pw_enc TEXT, os_info TEXT, metrics TEXT, metrics_at TEXT, last_error TEXT,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS apps(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, title TEXT, git_url TEXT NOT NULL,
  branch TEXT,                                               -- NULL => use the bench's frappe branch
  requires TEXT DEFAULT '',                                  -- comma separated app names to install first
  builtin INTEGER DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS server_apps(
  server_id INTEGER NOT NULL, app_name TEXT NOT NULL, PRIMARY KEY(server_id, app_name));
CREATE TABLE IF NOT EXISTS sites(
  id INTEGER PRIMARY KEY, server_id INTEGER NOT NULL, domain TEXT UNIQUE NOT NULL, company TEXT,
  apps TEXT DEFAULT '', admin_pw_enc TEXT, status TEXT DEFAULT 'creating', -- creating|up|down|error
  http_code INTEGER, checked_at TEXT, ssl INTEGER DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP, user TEXT, role TEXT, action TEXT,
  target TEXT, detail TEXT, ip TEXT);
CREATE INDEX IF NOT EXISTS audit_ts ON audit(id DESC);
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT, email TEXT, phone TEXT, plan TEXT,
  renews_on TEXT, notes TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS site_notes(
  id INTEGER PRIMARY KEY, site_id INTEGER NOT NULL, user TEXT, text TEXT NOT NULL, ts TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS approvals(
  id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP, action TEXT, site_id INTEGER, site_domain TEXT,
  params TEXT, requested_by TEXT, reason TEXT, status TEXT DEFAULT 'pending', decided_by TEXT, decided_at TEXT, job_id INTEGER);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY, kind TEXT, title TEXT, status TEXT DEFAULT 'running', -- running|done|failed
  log TEXT DEFAULT '', created TEXT DEFAULT CURRENT_TIMESTAMP, finished TEXT);
"""

# Official Frappe-ecosystem apps. branch NULL => same branch as the bench's frappe.
BUILTIN_APPS = [
    ("erpnext", "ERPNext", "https://github.com/frappe/erpnext", None, ""),
    ("payments", "Payments", "https://github.com/frappe/payments", None, ""),
    ("hrms", "HRMS", "https://github.com/frappe/hrms", None, "erpnext"),
    ("lending", "Lending", "https://github.com/frappe/lending", None, "erpnext"),
    ("healthcare", "Healthcare", "https://github.com/frappe/health", None, "erpnext"),
    ("education", "Education", "https://github.com/frappe/education", None, "erpnext"),
    ("webshop", "Webshop", "https://github.com/frappe/webshop", None, "erpnext"),
    ("print_designer", "Print Designer", "https://github.com/frappe/print_designer", "develop", ""),
    ("crm", "Frappe CRM", "https://github.com/frappe/crm", "main", ""),
    ("helpdesk", "Helpdesk", "https://github.com/frappe/helpdesk", "main", ""),
    ("insights", "Insights", "https://github.com/frappe/insights", "develop", ""),
    ("builder", "Builder", "https://github.com/frappe/builder", "master", ""),
    ("wiki", "Wiki", "https://github.com/frappe/wiki", "master", ""),
    ("lms", "Learning (LMS)", "https://github.com/frappe/lms", "main", ""),
    ("drive", "Drive", "https://github.com/frappe/drive", "main", ""),
]


@contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(config.DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()


def q(sql, args=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def x(sql, args=()):
    with conn() as c:
        return c.execute(sql, args).lastrowid


# columns added after the first release: (table, column, DDL)
MIGRATIONS = [
    ("users", "role", "TEXT DEFAULT 'admin'"), ("users", "disabled", "INTEGER DEFAULT 0"),
    ("servers", "gateway", "INTEGER DEFAULT 0"), ("servers", "gateway_url", "TEXT"),
    ("sites", "golive_provider", "INTEGER DEFAULT 0"), ("sites", "customer_id", "INTEGER"),
    ("sites", "suspended", "INTEGER DEFAULT 0"), ("sites", "aliases", "TEXT DEFAULT ''"),
    ("sites", "public_ok", "INTEGER"), ("sites", "public_at", "TEXT"),
    ("jobs", "user", "TEXT"),
]


def init():
    config.ensure_dirs()
    with conn() as c:
        c.executescript(SCHEMA)
        for table, col, ddl in MIGRATIONS:
            if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        for name, title, url, branch, req in BUILTIN_APPS:
            c.execute(
                "INSERT OR IGNORE INTO apps(name,title,git_url,branch,requires,builtin) VALUES(?,?,?,?,?,1)",
                (name, title, url, branch, req))
        # a job can't still be running after a restart
        c.execute("UPDATE jobs SET status='failed', finished=CURRENT_TIMESTAMP, "
                  "log=log||'\n[interrupted by restart]' WHERE status='running'")
        c.execute("UPDATE servers SET status='error', last_error='Interrupted by restart' WHERE status='configuring'")
