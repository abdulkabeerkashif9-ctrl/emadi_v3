import time

import pytest
from fastapi.testclient import TestClient

from fleetmanager import backups, db, main, monitor, notify, scheduler, security
from test_flow import login


@pytest.fixture
def users(client):
    login(client)
    for n, role in (("rita", "support"), ("vera", "viewer")):
        if not db.q1("SELECT 1 FROM users WHERE username=?", (n,)):
            client.post("/api/team", json={"username": n, "password": "password123", "role": role})
    def as_(n):
        c = TestClient(main.app); assert c.post("/api/auth/login", json={"username": n, "password": "password123"}).status_code == 200; return c
    return client, as_("rita"), as_("vera")


@pytest.fixture
def sid(client):
    login(client)
    srv = db.q1("SELECT id FROM servers ORDER BY id LIMIT 1")
    db.x("DELETE FROM sites WHERE domain='api.example.com'"); db.x("DELETE FROM incidents"); db.x("DELETE FROM checks")
    return db.x("INSERT INTO sites(server_id,domain,status,admin_pw_enc) VALUES(?,?,'up',?)", (srv["id"], "api.example.com", security.encrypt("x")))


def test_summary_uptime_and_incident_lifecycle(users, sid, monkeypatch):
    admin, rita, vera = users
    monkeypatch.setattr(notify, "send", lambda *a, **k: {})
    for ok in (1, 1, 0, 0, 0):
        monitor.record_check(sid, "public", ok); monitor.evaluate_site(sid)
    s = vera.get("/api/monitor/summary").json()
    site = [x for x in s["sites"] if x["id"] == sid][0]
    assert s["open"] == 1 and s["critical"] == 1 and site["uptime24"] == 40.0 and site["bars"][-1] == "partial" and len(site["bars"]) == 48
    inc = vera.get("/api/incidents").json()[0]
    assert inc["kind"] == "site_down" and inc["target_name"] == "api.example.com"
    assert vera.post(f"/api/incidents/{inc['id']}/ack").status_code == 403 and vera.post(f"/api/incidents/{inc['id']}/close").status_code == 403
    assert rita.post(f"/api/incidents/{inc['id']}/ack").status_code == 200
    assert vera.get("/api/incidents").json()[0]["acked_by"] == "rita"
    up = vera.get(f"/api/sites/{sid}/uptime").json()
    assert up["uptime24"] == 40.0 and up["incidents"][0]["id"] == inc["id"]
    assert rita.post(f"/api/incidents/{inc['id']}/close").status_code == 200 and rita.post(f"/api/incidents/{inc['id']}/close").status_code == 404
    assert vera.get("/api/incidents?status=resolved").json()[0]["resolved_by"] == "rita"
    assert any(r["action"] == "incident_close" for r in admin.get("/api/audit?q=incident").json())


def test_monitor_and_notify_settings_are_admin_only(users, monkeypatch):
    admin, rita, vera = users
    db.x("DELETE FROM settings WHERE key='notify'")                                    # other tests may have left channels enabled
    assert rita.get("/api/monitor/settings").status_code == 403 and rita.get("/api/notify").status_code == 403
    assert admin.put("/api/monitor/settings", json={"down_after": 5, "autoheal": True}).json()["autoheal"] is True
    assert admin.put("/api/monitor/settings", json={"disk_warn": 95, "disk_crit": 90}).status_code == 400
    assert admin.put("/api/monitor/settings", json={"autoheal": False, "down_after": 3}).status_code == 200
    assert admin.post("/api/notify/test").status_code == 400                           # nothing enabled yet
    sent = []
    monkeypatch.setattr(notify.requests, "post", lambda url, **k: sent.append((url, k["json"])) or type("R", (), {"status_code": 200, "text": ""})())
    out = admin.put("/api/notify", json={"webhook": {"enabled": True, "url": "https://hooks.example.com/x"}, "telegram": {"enabled": False}}).json()
    assert out["webhook"]["enabled"] and out["webhook"]["url"] == "" and out["webhook"]["has_url"]       # secret never returned
    assert admin.post("/api/notify/test").json() == {"webhook": "ok"} and sent and "test alert" in sent[0][1]["title"]
    assert admin.put("/api/notify", json={"email": {"port": "abc"}}).status_code == 400
    admin.put("/api/notify", json={"webhook": {"enabled": False}})


def test_run_now_checks_sites(users, sid, monkeypatch):
    admin, rita, vera = users
    monkeypatch.setattr(monitor, "_http_ping", lambda d: (True, 5, 200))
    monkeypatch.setattr(monitor, "run_server_checks", lambda *a, **k: None)
    assert vera.post("/api/monitor/run").status_code == 403
    assert rita.post("/api/monitor/run").json()["sites_checked"] >= 1
    assert db.q1("SELECT public_ok FROM sites WHERE id=?", (sid,))["public_ok"] == 1


def test_scheduler_runs_each_task_on_its_interval(monkeypatch):
    calls = []
    for mod, name in ((monitor, "run_site_checks"), (monitor, "run_server_checks"), (monitor, "run_ssl_checks"), (monitor, "prune"),
                      (backups, "run_due"), (backups, "check_overdue")):
        monkeypatch.setattr(mod, name, lambda n=name: calls.append(n))
    sch = scheduler.Scheduler()
    sch.last = {k: 0 for k in sch.last}                                                # pretend nothing ran yet
    monkeypatch.setattr(sch, "_refresh_servers", lambda: calls.append("refresh"))
    sch.tick()
    for _ in range(50):
        if len(calls) >= 7: break
        time.sleep(0.05)
    assert {"run_site_checks", "run_due", "check_overdue"} <= set(calls)
    n = len(calls); sch.tick(); time.sleep(0.2)
    assert len(calls) == n                                                              # nothing is due again immediately
    monitor.save_settings({"enabled": False})
    sch.last = {k: 0 for k in sch.last}; calls.clear(); sch.tick(); time.sleep(0.3)
    assert "run_site_checks" not in calls and "run_due" in calls                       # monitoring off, backups still scheduled
    monitor.save_settings({"enabled": True})
