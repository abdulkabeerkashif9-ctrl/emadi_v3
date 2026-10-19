import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from fleetmanager import backups, db, domains, main, monitor, ops, security, ssh
from conftest import FakeRunner
from test_flow import login, wait_job


def ts(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


NOW = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)          # a Wednesday, 10:00 UTC


@pytest.fixture(autouse=True)
def utc(monkeypatch):
    monkeypatch.setenv("TZ", "UTC"); time.tzset()
    yield
    monkeypatch.delenv("TZ"); time.tzset()


@pytest.fixture
def site(client):
    login(client)
    srv = db.q1("SELECT id FROM servers ORDER BY id LIMIT 1")
    db.x("DELETE FROM sites WHERE domain='bk.example.com'")
    sid = db.x("INSERT INTO sites(server_id,domain,status,admin_pw_enc,apps) VALUES(?,?,?,?,?)", (srv["id"], "bk.example.com", "up", security.encrypt("x"), "erpnext"))
    for t in ("backup_runs", "incidents"):
        db.x(f"DELETE FROM {t}")
    db.x("DELETE FROM backup_policies WHERE site_id IS NOT NULL"); db.x("DELETE FROM settings WHERE key='offsite'")
    backups.save_policy(None, {"enabled": True, "frequency": "daily", "hour": 2, "keep": 7, "offsite": False, "keep_offsite": 14})
    FakeRunner.backups["bk.example.com"] = []
    return sid


def run(started, status="ok", trigger="scheduled"):
    return {"started": ts(started), "status": status, "trigger": trigger}


def test_policy_validation_override_and_inherit(site):
    assert backups.get_policy(site)["source"] == "default"
    with pytest.raises(ops.OpError):
        backups.save_policy(site, {"frequency": "monthly"})
    with pytest.raises(ops.OpError):
        backups.save_policy(site, {"hour": 24})
    with pytest.raises(ops.OpError):
        backups.save_policy(site, {"keep": 0})
    p = backups.save_policy(site, {"frequency": "weekly", "weekday": 2, "hour": 4, "keep": 3})
    assert p["source"] == "site" and p["frequency"] == "weekly" and backups.get_policy(None)["frequency"] == "daily"
    backups.clear_policy(site)
    assert backups.get_policy(site)["source"] == "default"


def test_is_due_daily_weekly_hours_and_retries():
    daily = {"enabled": 1, "frequency": "daily", "hour": 2, "weekday": 0, "interval_hours": 24}
    assert backups.is_due(daily, [], NOW)                                              # never backed up
    assert not backups.is_due(daily, [run(NOW.replace(hour=2, minute=5))], NOW)        # today's slot done
    assert backups.is_due(daily, [run(NOW - timedelta(days=1, hours=7))], NOW)         # yesterday 03:00 → today 02:00 missed
    assert not backups.is_due({**daily, "enabled": 0}, [], NOW)
    assert backups.is_due(daily, [run(NOW - timedelta(days=2)), run(NOW, "ok", "pre-restore")], NOW)      # pre-restore doesn't count
    failed = [run(NOW.replace(hour=2, minute=5), "failed")]
    assert backups.is_due(daily, failed, NOW)                                          # retry after an hour
    assert not backups.is_due(daily, [run(NOW - timedelta(minutes=20), "failed")], NOW)
    assert not backups.is_due(daily, [run(NOW - timedelta(hours=h), "failed") for h in (1.5, 2.5, 3.5)], NOW)   # 3 tries per slot
    weekly = {**daily, "frequency": "weekly", "weekday": 0, "hour": 3}                 # Mondays 03:00
    assert backups.last_scheduled(weekly, NOW) == datetime(2026, 10, 19, 3, 0, tzinfo=timezone.utc)
    assert not backups.is_due(weekly, [run(datetime(2026, 10, 19, 3, 10, tzinfo=timezone.utc))], NOW)
    assert backups.is_due(weekly, [run(datetime(2026, 10, 12, 3, 10, tzinfo=timezone.utc))], NOW)
    hours = {**daily, "frequency": "hours", "interval_hours": 6}
    assert not backups.is_due(hours, [run(NOW - timedelta(hours=5))], NOW) and backups.is_due(hours, [run(NOW - timedelta(hours=7))], NOW)


def test_run_backup_records_run_and_prunes_old_groups(site):
    backups.save_policy(site, {"keep": 2})
    for _ in range(4):
        backups.run_backup(site, "manual")
    runs = backups.runs_for(site)
    assert len(runs) == 4 and all(r["status"] == "ok" and r["size_bytes"] == 6000 and r["trigger"] == "manual" for r in runs)
    names = {f["name"][:15] for f in FakeRunner.backups["bk.example.com"]}
    assert names == {"20270101_000004", "20270101_000003"}                               # only the newest 2 backups remain


def test_failed_backup_opens_incident_and_next_success_closes_it(site, monkeypatch):
    sent = []; monkeypatch.setattr(monitor.notify, "send", lambda *a, **k: sent.append(a) or {})
    FakeRunner.backup_fail = True
    with pytest.raises(ssh.SSHError):
        backups.run_backup(site, "scheduled")
    assert backups.runs_for(site)[0]["status"] == "failed" and "disk full" in backups.runs_for(site)[0]["message"]
    assert db.q1("SELECT severity FROM incidents WHERE kind='backup_failed' AND status='open'")["severity"] == "crit" and sent
    FakeRunner.backup_fail = False
    backups.run_backup(site, "scheduled")
    assert db.q1("SELECT status FROM incidents WHERE kind='backup_failed'")["status"] == "resolved"


def test_destination_validation_and_secrets(site):
    assert backups.dest_masked() == {"configured": False}
    with pytest.raises(ops.OpError):
        backups.dest_save({"type": "s3", "path": "bucket", "access_key": "a\nb", "secret_key": "s"})   # config-injection attempt
    with pytest.raises(ops.OpError):
        backups.dest_save({"type": "s3", "path": "bucket/../x", "access_key": "a", "secret_key": "s"})
    with pytest.raises(ops.OpError):
        backups.dest_save({"type": "ftp", "path": "x"})
    m = backups.dest_save({"type": "s3", "provider": "Wasabi", "endpoint": "s3.wasabisys.com", "region": "", "access_key": "AK", "secret_key": "SK", "path": "/my-bucket/erp/"})
    assert m["configured"] and m["path"] == "my-bucket/erp" and m["secret_key"] == "" and m["has_secret"]
    m2 = backups.dest_save({"type": "s3", "provider": "Wasabi", "access_key": "AK2", "secret_key": "", "path": "my-bucket/erp"})   # blank secret keeps the old one
    assert backups.dest_get()["secret_key"] == "SK" and backups.dest_get()["access_key"] == "AK2"
    assert "pass = OBS" in backups._conf({"type": "sftp", "host": "h", "port": 22, "user": "u"}, "OBS") and "provider = Wasabi" in backups._conf(backups.dest_get(), "")


def test_offsite_copy_verify_prune_and_failure(site):
    backups.dest_save({"type": "sftp", "host": "backup.example.com", "port": 22, "user": "bk", "password": "pw", "path": "erp"})
    backups.save_policy(site, {"offsite": True, "keep": 5, "keep_offsite": 2})
    for _ in range(3):
        backups.run_backup(site, "manual")
    assert all(r["offsite_status"] == "ok" for r in backups.runs_for(site))
    assert {f["name"][:15] for f in FakeRunner.offsite["bk.example.com"]} == {"20270101_000003", "20270101_000002"}   # offsite keeps 2, server keeps 5
    assert len({f["name"][:15] for f in FakeRunner.backups["bk.example.com"]}) == 3
    conf = [p for p in FakeRunner.written if "fm-rclone" in p][-1]
    assert FakeRunner.written[conf][1] == 0o600 and "pass = OBSCURED" in FakeRunner.written[conf][0]                    # secret never world-readable
    assert any("rm -f" in c[1] and "fm-rclone" in c[1] for c in FakeRunner.calls if c[0] == "run")                      # and removed afterwards
    FakeRunner.offsite_fail = True
    backups.run_backup(site, "manual")
    last = backups.runs_for(site)[0]
    assert last["status"] == "ok" and last["offsite_status"].startswith("failed")                                      # local backup still counts
    assert db.q1("SELECT severity FROM incidents WHERE kind='backup_offsite'")["severity"] == "warn"
    FakeRunner.offsite_fail = False
    backups.run_backup(site, "manual")
    assert db.q1("SELECT status FROM incidents WHERE kind='backup_offsite'")["status"] == "resolved"


def test_offsite_without_destination_is_skipped_not_failed(site):
    backups.save_policy(site, {"offsite": True})
    backups.run_backup(site, "manual")
    assert backups.runs_for(site)[0]["offsite_status"].startswith("skipped")


def test_due_sites_and_overdue_warning(site):
    assert site in backups.due_sites()
    backups.run_backup(site, "scheduled")
    assert site not in backups.due_sites()
    db.x("UPDATE backup_runs SET started=?", (ts(datetime.now(timezone.utc) - timedelta(days=3)),))
    backups.check_overdue()
    assert db.q1("SELECT severity FROM incidents WHERE kind='backup_overdue'")["severity"] == "warn"
    backups.run_backup(site, "scheduled"); backups.check_overdue()
    assert db.q1("SELECT status FROM incidents WHERE kind='backup_overdue'")["status"] == "resolved"
    ids, threads = backups.run_due()
    [t.join(10) for t in threads]


def test_restore_order_safety_backup_and_failure(site):
    backups.run_backup(site, "manual")
    gid = backups._groups(FakeRunner.backups["bk.example.com"]).__iter__().__next__()
    FakeRunner.calls.clear()
    backups.restore_job(site, gid, "server", lambda t: None)
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    i_safety = next(i for i, c in enumerate(cmds) if "backup --with-files" in c)
    i_restore = next(i for i, c in enumerate(cmds) if " restore " in c)
    i_on = next(i for i, c in enumerate(cmds) if "set-maintenance-mode on" in c)
    i_off = max(i for i, c in enumerate(cmds) if "set-maintenance-mode off" in c)
    assert i_safety < i_on < i_restore < i_off                                         # backup → maintenance on → restore → off
    r = cmds[i_restore]
    assert f"{gid}-bk_example_com-database.sql.gz" in r and "--with-public-files" in r and "--with-private-files" in r and "--db-root-password" in r
    assert backups.runs_for(site)[0]["trigger"] == "pre-restore"
    FakeRunner.restore_fail = True; FakeRunner.calls.clear()
    with pytest.raises(ssh.SSHError, match="safety backup"):
        backups.restore_job(site, gid, "server", lambda t: None)
    assert "set-maintenance-mode off" in [c[1] for c in FakeRunner.calls if c[0] == "run"][-1] or any("set-maintenance-mode off" in c[1] for c in FakeRunner.calls if c[0] == "run")
    with pytest.raises(ssh.SSHError, match="Bad backup id"):
        backups.restore_job(site, "../etc", "server", lambda t: None)
    with pytest.raises(ssh.SSHError, match="not found"):
        backups.restore_job(site, "20200101_000000", "server", lambda t: None)


def test_restore_from_offsite_downloads_first(site):
    backups.dest_save({"type": "s3", "provider": "AWS", "access_key": "a", "secret_key": "s", "path": "bkt"})
    backups.save_policy(site, {"offsite": True})
    backups.run_backup(site, "manual")
    gid = next(iter(backups._groups(FakeRunner.offsite["bk.example.com"])))
    FakeRunner.backups["bk.example.com"] = []                                           # the server lost its local copy
    FakeRunner.calls.clear()
    backups.restore_job(site, gid, "offsite", lambda t: None)
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert next(i for i, c in enumerate(cmds) if "copyto fm:" in c) < next(i for i, c in enumerate(cmds) if " restore " in c)


@pytest.fixture
def team(client, site):
    for n, role in (("bob", "support"), ("vic", "viewer")):
        if not db.q1("SELECT 1 FROM users WHERE username=?", (n,)):
            client.post("/api/team", json={"username": n, "password": "password123", "role": role})
    c = TestClient(main.app); c.post("/api/auth/login", json={"username": "bob", "password": "password123"})
    return client, c


def test_restore_api_needs_approval_for_support(team, site):
    admin, bob = team
    backups.run_backup(site, "manual")
    gid = next(iter(backups._groups(FakeRunner.backups["bk.example.com"])))
    body = {"group": gid, "source": "server", "reason": "customer asked", "confirm": "bk.example.com"}
    assert bob.post(f"/api/sites/{site}/restore", json=body | {"confirm": "x"}).status_code == 400
    r = bob.post(f"/api/sites/{site}/restore", json=body)
    assert r.json()["pending"] is True and bob.post(f"/api/sites/{site}/restore", json=body).status_code == 409
    aid = r.json()["approval_id"]
    FakeRunner.calls.clear()
    d = admin.post(f"/api/approvals/{aid}/decide", json={"approve": True}).json()
    assert wait_job(admin, d["job_id"])["status"] == "done"
    assert any(" restore " in c[1] for c in FakeRunner.calls if c[0] == "run")
    r2 = admin.post(f"/api/sites/{site}/restore", json=body)
    assert r2.json()["pending"] is False and wait_job(admin, r2.json()["job_id"])["status"] == "done"


def test_backup_api_roles_and_manual_job(team, site):
    admin, bob = team
    vic = TestClient(main.app); vic.post("/api/auth/login", json={"username": "vic", "password": "password123"})
    assert bob.get("/api/backups").status_code == 200 and vic.get("/api/backups").status_code == 403
    assert bob.put("/api/backups/policy", json={"frequency": "daily"}).status_code == 403
    assert admin.put("/api/backups/policy", json={"frequency": "weekly", "weekday": 6, "hour": 1, "keep": 4}).json()["frequency"] == "weekly"
    assert admin.put("/api/backups/policy", json={"frequency": "daily", "hour": 99}).status_code in (400, 422)
    admin.put("/api/backups/policy", json={"frequency": "daily", "hour": 2})
    assert admin.put(f"/api/sites/{site}/backup-policy", json={"frequency": "hours", "interval_hours": 12}).json()["source"] == "site"
    assert admin.delete(f"/api/sites/{site}/backup-policy").json()["source"] == "default"
    r = bob.post(f"/api/sites/{site}/backup")
    assert wait_job(bob, r.json()["job_id"])["status"] == "done"
    assert bob.get(f"/api/sites/{site}/backup-runs").json()[0]["trigger"] == "manual"
    ov = bob.get("/api/backups").json()
    row = [s for s in ov["sites"] if s["id"] == site][0]
    assert row["last_ok"] and row["next_run"] and ov["destination"]["configured"] is False
    assert admin.put("/api/backups/destination", json={"type": "s3", "path": "b", "access_key": "a", "secret_key": "s"}).json()["configured"]
    assert bob.get("/api/backups/destination").status_code == 403
    assert admin.post("/api/backups/destination/test").json()["ok"]
    FakeRunner.offsite_fail = True
    assert admin.post("/api/backups/destination/test").status_code == 400
    FakeRunner.offsite_fail = False
    assert admin.delete("/api/backups/destination").status_code == 200 and not backups.dest_configured()


def test_move_site_between_servers(team, site):
    admin, bob = team
    src = db.q1("SELECT * FROM servers ORDER BY id LIMIT 1")
    tid = db.x("INSERT INTO servers(name,ip,ssh_port,ssh_user,auth_type,secret_enc,version,status,db_root_pw_enc,bench_path) VALUES('vps2','203.0.113.77',22,'root','password',?,?,'ready',?,'/home/frappe/frappe-bench')",
               (security.encrypt("x"), src["version"], security.encrypt("rootpw")))
    FakeRunner.apps = ["erpnext"]
    assert bob.post(f"/api/sites/{site}/move", json={"server_id": tid, "confirm": "bk.example.com"}).status_code == 403
    assert admin.post(f"/api/sites/{site}/move", json={"server_id": src["id"], "confirm": "bk.example.com"}).status_code == 400
    assert admin.post(f"/api/sites/{site}/move", json={"server_id": tid, "confirm": "nope"}).status_code == 400
    FakeRunner.calls.clear()
    r = admin.post(f"/api/sites/{site}/move", json={"server_id": tid, "confirm": "bk.example.com"})
    job = wait_job(admin, r.json()["job_id"])
    assert job["status"] == "done", job["log"]
    assert db.q1("SELECT server_id FROM sites WHERE id=?", (site,))["server_id"] == tid
    ran = [(c[2], c[1]) for c in FakeRunner.calls if c[0] == "run"]
    assert any(n == "vps2" and "new-site bk.example.com" in c for n, c in ran) and any(n == "vps2" and " restore " in c for n, c in ran)
    assert FakeRunner.relayed and all(p.startswith("/tmp/fm-move-") for p, _ in FakeRunner.relayed)
    assert "point DNS" in job["log"]
    assert any(n == "vps2" and "rm -rf /tmp/fm-move-" in c for n, c in ran)          # staging cleaned on both sides
    db.x("UPDATE servers SET version='version-16' WHERE id=?", (tid,))
    db.x("UPDATE sites SET server_id=? WHERE id=?", (src["id"], site))
    r = admin.post(f"/api/sites/{site}/move", json={"server_id": tid, "confirm": "bk.example.com"})
    j = wait_job(admin, r.json()["job_id"])
    assert j["status"] == "failed" and "different ERPNext versions" in j["log"]
    assert db.q1("SELECT server_id FROM sites WHERE id=?", (site,))["server_id"] == src["id"]       # unchanged on failure
    db.x("DELETE FROM servers WHERE id=?", (tid,))
