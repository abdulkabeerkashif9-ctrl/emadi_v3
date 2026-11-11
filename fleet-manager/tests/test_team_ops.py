import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from fleetmanager import config, db, domains, main, ops
from conftest import FakeRunner
from test_flow import login, wait_job


def as_user(name, pw="password123"):
    c = TestClient(main.app)
    assert c.post("/api/auth/login", json={"username": name, "password": pw}).status_code == 200
    return c


@pytest.fixture(scope="module")
def team(client):
    login(client)
    for n, role in (("sue", "support"), ("vic", "viewer")):
        if not db.q1("SELECT 1 FROM users WHERE username=?", (n,)):
            assert client.post("/api/team", json={"username": n, "password": "password123", "role": role}).status_code == 200
    return {"admin": client, "sue": as_user("sue"), "vic": as_user("vic")}


def make_site(admin, domain, monkeypatch):
    monkeypatch.setattr(domains, "resolve", lambda d: [])
    sid = admin.get("/api/servers").json()[0]["id"]
    r = admin.post("/api/sites", json={"domain": domain, "server_id": sid, "apps": ["erpnext"]})
    assert r.status_code == 200, r.text
    assert wait_job(admin, r.json()["job_id"])["status"] == "done"
    return r.json()["site_id"]


def test_roles_are_enforced(team, monkeypatch):
    admin, sue, vic = team["admin"], team["sue"], team["vic"]
    sid = make_site(admin, "roles.example.com", monkeypatch)
    assert vic.get("/api/sites").status_code == 200
    assert vic.post(f"/api/sites/{sid}/backup").status_code == 403
    assert vic.get(f"/api/sites/{sid}/credentials").status_code == 403
    assert vic.get(f"/api/sites/{sid}/logs").status_code == 403
    assert sue.get(f"/api/sites/{sid}/credentials").status_code == 200
    r = sue.post(f"/api/sites/{sid}/backup")
    assert r.status_code == 200 and wait_job(sue, r.json()["job_id"])["status"] == "done"
    for method, url, body in (("delete", f"/api/sites/{sid}", None), ("post", "/api/servers", {}), ("get", "/api/team", None),
                              ("get", "/api/audit", None), ("get", "/api/settings/cpanel", None), ("post", f"/api/sites/{sid}/rename", {"domain": "x.example.com"})):
        resp = getattr(sue, method)(url, **({"json": body} if body is not None else {}))
        assert resp.status_code in (403, 422), (url, resp.status_code)
        assert resp.status_code == 403 or url == "/api/servers"
    assert sue.get("/api/auth/state").json()["role"] == "support"


def test_audit_trail_records_who_did_what(team):
    rows = team["admin"].get("/api/audit?limit=200").json()
    assert any(r["action"] == "site_backup" and r["user"] == "sue" and r["target"] == "roles.example.com" for r in rows)
    assert any(r["action"] == "site_view_credentials" and r["user"] == "sue" for r in rows)
    assert any(r["action"] == "login" and r["user"] == "sue" for r in rows)
    assert team["admin"].get("/api/audit?user=sue").json() and all(r["user"] == "sue" for r in team["admin"].get("/api/audit?user=sue").json())
    assert all("backup" in r["action"] + r["target"] + r["detail"] for r in team["admin"].get("/api/audit?q=backup").json())


def test_quick_operations_run_the_right_commands(team):
    sue = team["sue"]
    sid = [s for s in sue.get("/api/sites").json() if s["domain"] == "roles.example.com"][0]["id"]
    FakeRunner.calls.clear()
    assert sue.post(f"/api/sites/{sid}/maintenance", json={"on": True}).status_code == 200
    assert sue.post(f"/api/sites/{sid}/clear-cache").status_code == 200
    pw = sue.post(f"/api/sites/{sid}/reset-password").json()["password"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert any("set-maintenance-mode on" in c and "roles.example.com" in c for c in cmds)
    assert any("clear-cache" in c for c in cmds) and any("clear-website-cache" in c for c in cmds)
    assert any("set-admin-password" in c and pw in c for c in cmds)
    assert sue.get(f"/api/sites/{sid}/credentials").json()["password"] == pw        # stored for later
    assert "set-admin-password" not in json.dumps([r["detail"] for r in team["admin"].get("/api/audit?limit=50").json()])  # never in audit


def test_logs_and_backups(team):
    sue = team["sue"]
    sid = [s for s in sue.get("/api/sites").json() if s["domain"] == "roles.example.com"][0]["id"]
    assert "error line one" in sue.get(f"/api/sites/{sid}/logs?source=site").json()["text"]
    assert sue.get(f"/api/sites/{sid}/logs?source=../../etc/passwd").status_code == 400
    b = sue.get(f"/api/sites/{sid}/backups").json()
    assert [x["name"] for x in b] == ["20261018_100000-x-files.tar", "20261018_100000-x_database.sql.gz"]   # newest first, bad name dropped
    assert sue.get(f"/api/sites/{sid}/backups/a..b").status_code == 400
    assert sue.get(f"/api/sites/{sid}/backups/x;rm").status_code in (400, 404)


def test_deleting_a_site_needs_approval_for_support(team, monkeypatch):
    admin, sue = team["admin"], team["sue"]
    sid = make_site(admin, "doomed.example.com", monkeypatch)
    assert sue.post(f"/api/sites/{sid}/delete", json={"reason": "customer left", "confirm": "wrong.com"}).status_code == 400
    r = sue.post(f"/api/sites/{sid}/delete", json={"reason": "customer left", "confirm": "doomed.example.com"})
    assert r.json()["pending"] is True
    assert sue.post(f"/api/sites/{sid}/delete", json={"reason": "again", "confirm": "doomed.example.com"}).status_code == 409
    assert sue.post(f"/api/approvals/{r.json()['approval_id']}/decide", json={"approve": True}).status_code == 403
    pending = admin.get("/api/approvals?status=pending").json()
    assert [p["site_domain"] for p in pending] == ["doomed.example.com"] and not team["vic"].get("/api/approvals").status_code == 200
    FakeRunner.calls.clear()
    d = admin.post(f"/api/approvals/{r.json()['approval_id']}/decide", json={"approve": True}).json()
    assert d["status"] == "approved" and wait_job(admin, d["job_id"])["status"] == "done"
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert any("backup --with-files" in c for c in cmds) and any("drop-site doomed.example.com" in c and "--no-backup" in c for c in cmds)
    assert not [s for s in admin.get("/api/sites").json() if s["domain"] == "doomed.example.com"]
    assert admin.get("/api/approvals").json()[0]["status"] == "approved"


def test_rejected_request_keeps_the_site_and_admin_deletes_directly(team, monkeypatch):
    admin, sue = team["admin"], team["sue"]
    sid = make_site(admin, "kept.example.com", monkeypatch)
    aid = sue.post(f"/api/sites/{sid}/delete", json={"reason": "oops", "confirm": "kept.example.com"}).json()["approval_id"]
    assert admin.post(f"/api/approvals/{aid}/decide", json={"approve": False}).json()["status"] == "rejected"
    assert [s for s in admin.get("/api/sites").json() if s["domain"] == "kept.example.com"]
    r = admin.post(f"/api/sites/{sid}/delete", json={"reason": "cleanup", "confirm": "KEPT.example.com", "backup_first": False})
    assert r.json()["pending"] is False and wait_job(admin, r.json()["job_id"])["status"] == "done"
    assert not [s for s in admin.get("/api/sites").json() if s["domain"] == "kept.example.com"]


def test_failed_backup_before_delete_keeps_the_site(team, monkeypatch):
    admin = team["admin"]
    sid = make_site(admin, "safe.example.com", monkeypatch)
    orig = FakeRunner.run
    monkeypatch.setattr(FakeRunner, "run", lambda self, cmd, **k: (1, "disk full") if "backup --with-files" in cmd else orig(self, cmd, **k))
    r = admin.post(f"/api/sites/{sid}/delete", json={"reason": "cleanup", "confirm": "safe.example.com"})
    assert wait_job(admin, r.json()["job_id"])["status"] == "failed"
    assert [s for s in admin.get("/api/sites").json() if s["domain"] == "safe.example.com"]
    assert not any("drop-site" in c[1] for c in FakeRunner.calls if c[0] == "run")


def test_team_management_and_last_admin_protection(team):
    admin = team["admin"]
    assert admin.post("/api/team", json={"username": "sue", "password": "password123", "role": "support"}).status_code == 409
    assert admin.post("/api/team", json={"username": "bad name!", "password": "password123", "role": "support"}).status_code == 422
    assert admin.put("/api/team/admin", json={"role": "support"}).status_code == 400     # only admin
    assert admin.put("/api/team/admin", json={"disabled": True}).status_code == 400
    assert admin.delete("/api/team/admin").status_code == 400
    admin.post("/api/team", json={"username": "boss2", "password": "password123", "role": "admin"})
    assert admin.put("/api/team/boss2", json={"role": "viewer"}).status_code == 200      # fine: 'admin' remains
    assert admin.delete("/api/team/boss2").status_code == 200


def test_disabled_user_loses_access_and_password_change(team):
    admin = team["admin"]
    tmp = admin.post("/api/team", json={"username": "temp1", "password": "password123", "role": "support"})
    c = as_user("temp1")
    assert c.get("/api/sites").status_code == 200
    admin.put("/api/team/temp1", json={"disabled": True})
    assert c.get("/api/sites").status_code == 401                                         # existing session dies
    assert TestClient(main.app).post("/api/auth/login", json={"username": "temp1", "password": "password123"}).status_code == 401
    admin.put("/api/team/temp1", json={"disabled": False, "password": "another-pass-9"})
    c2 = as_user("temp1", "another-pass-9")
    assert c2.post("/api/auth/password", json={"current": "nope", "new": "brand-new-pass"}).status_code == 400
    assert c2.post("/api/auth/password", json={"current": "another-pass-9", "new": "brand-new-pass"}).status_code == 200
    as_user("temp1", "brand-new-pass")


def test_customers_notes_and_suspend(team):
    admin, sue = team["admin"], team["sue"]
    sid = [s for s in sue.get("/api/sites").json() if s["domain"] == "roles.example.com"][0]["id"]
    soon = time.strftime("%Y-%m-%d", time.localtime(time.time() + 5 * 86400))
    c = sue.post("/api/customers", json={"name": "Acme Traders", "email": "a@acme.test", "plan": "Pro", "renews_on": soon}).json()
    assert c["renewal"] == "soon" and 4 <= c["days_left"] <= 6
    assert sue.post("/api/customers", json={"name": "X", "renews_on": "31/12/2026"}).status_code == 422
    assert sue.put(f"/api/sites/{sid}/customer", json={"customer_id": c["id"]}).status_code == 200
    site = [s for s in sue.get("/api/sites").json() if s["id"] == sid][0]
    assert site["customer_name"] == "Acme Traders"
    assert [x for x in sue.get("/api/customers").json() if x["id"] == c["id"]][0]["sites"] == 1
    assert sue.delete(f"/api/customers/{c['id']}").status_code == 403
    assert sue.post(f"/api/sites/{sid}/notes", json={"text": "Customer called about invoices"}).status_code == 200
    assert team["vic"].get(f"/api/sites/{sid}/notes").json()[0]["user"] == "sue"
    assert team["vic"].post(f"/api/sites/{sid}/notes", json={"text": "x"}).status_code == 403
    assert sue.post(f"/api/sites/{sid}/suspend", json={"suspended": True, "reason": ""}).status_code == 400
    FakeRunner.calls.clear()
    assert sue.post(f"/api/sites/{sid}/suspend", json={"suspended": True, "reason": "unpaid invoice"}).status_code == 200
    assert any("set-maintenance-mode on" in c[1] for c in FakeRunner.calls if c[0] == "run")
    assert [s for s in sue.get("/api/sites").json() if s["id"] == sid][0]["suspended"] == 1
    assert "Suspended: unpaid invoice" in [n["text"] for n in sue.get(f"/api/sites/{sid}/notes").json()]
    sue.post(f"/api/sites/{sid}/suspend", json={"suspended": False})
    assert admin.delete(f"/api/customers/{c['id']}").status_code == 200
    assert [s for s in sue.get("/api/sites").json() if s["id"] == sid][0]["customer_id"] is None


def test_golive_checklist(team, monkeypatch):
    sue = team["sue"]
    sid = [s for s in sue.get("/api/sites").json() if s["domain"] == "roles.example.com"][0]["id"]
    ip = sue.get("/api/servers").json()[0]["ip"]

    class R:
        def __init__(self, code, text): self.status_code, self.text = code, text
    monkeypatch.setattr(domains, "resolve", lambda d: [ip])
    monkeypatch.setattr(ops.requests, "get", lambda *a, **k: R(404, "404 page not found"))
    g = sue.get(f"/api/sites/{sid}/golive").json()
    assert g["dns"]["ok"] and not g["public"]["ok"] and not g["live"] and "not answering" in g["public"]["detail"]
    assert [s for s in sue.get("/api/sites").json() if s["id"] == sid][0]["public_ok"] == 0
    monkeypatch.setattr(ops.requests, "get", lambda *a, **k: R(200, '{"message":"pong"}'))
    assert sue.get(f"/api/sites/{sid}/golive").json()["live"] is True
    monkeypatch.setattr(domains, "resolve", lambda d: ["203.0.113.99"])
    assert sue.get(f"/api/sites/{sid}/golive").json()["dns"]["ok"] is False
    assert sue.post(f"/api/sites/{sid}/golive", json={"provider_done": True}).status_code == 200
    assert sue.get(f"/api/sites/{sid}/golive").json()["provider_done"] is True


def test_gateway_server_flag_and_inner_ip(team):
    admin = team["admin"]
    s = admin.get("/api/servers").json()[0]
    body = {"name": s["name"], "ip": s["ip"], "ssh_port": s["ssh_port"], "ssh_user": s["ssh_user"], "auth_type": s["auth_type"],
            "version": s["version"], "gateway": True, "gateway_url": "https://panel.example.com/vps/1"}
    out = admin.put(f"/api/servers/{s['id']}", json=body).json()
    assert out["gateway"] == 1 and out["gateway_url"].startswith("https://")
    assert admin.put(f"/api/servers/{s['id']}", json=body | {"gateway_url": "javascript:alert(1)"}).status_code == 400
    db.x("UPDATE servers SET metrics=? WHERE id=?", (json.dumps({"load": 0.1, "cores": 2, "mem_total_mb": 4000, "mem_pct": 30, "disk_pct": 30, "inner_ip": "192.168.122.6"}), s["id"]))
    assert admin.get("/api/servers").json()[0]["inner_ip"] == "192.168.122.6"
    admin.put(f"/api/servers/{s['id']}", json=body | {"gateway": False, "gateway_url": ""})


def test_old_database_is_migrated(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    c = sqlite3.connect(old)
    c.executescript(db.SCHEMA)                       # base schema: none of the later columns exist yet
    c.execute("INSERT INTO users(username,pw_hash) VALUES('legacy','x')")
    assert "role" not in {r[1] for r in c.execute("PRAGMA table_info(users)")}
    c.commit(); c.close()
    monkeypatch.setattr(config, "DB_PATH", old)
    db.init()
    cols = lambda t: {r["name"] for r in db.q(f"PRAGMA table_info({t})")}
    assert {"role", "disabled"} <= cols("users") and {"gateway", "gateway_url"} <= cols("servers") and {"customer_id", "suspended", "public_ok"} <= cols("sites")
    assert db.q1("SELECT role FROM users WHERE username='legacy'")["role"] == "admin"      # existing users stay admins
    db.init()                                                                              # idempotent
