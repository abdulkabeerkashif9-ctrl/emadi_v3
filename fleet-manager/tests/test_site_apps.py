import pytest
from fastapi.testclient import TestClient

from fleetmanager import db, main, security
from conftest import FakeRunner
from test_flow import login, wait_job


@pytest.fixture
def sid(client):
    login(client)
    srv = db.q1("SELECT id FROM servers ORDER BY id LIMIT 1")
    db.x("DELETE FROM sites WHERE domain='apps.example.com'")
    return db.x("INSERT INTO sites(server_id,domain,status,admin_pw_enc) VALUES(?,?,'up',?)", (srv["id"], "apps.example.com", security.encrypt("x")))


def test_info_lists_installed_available_and_pending_updates(client, sid):
    r = client.get(f"/api/sites/{sid}/apps").json()
    erp = next(a for a in r["installed"] if a["name"] == "erpnext")
    assert erp["behind"] == 3 and erp["version"] == "15.2.0"
    assert any(a["name"] == "hrms" for a in r["available"]) and not any(a["name"] == "erpnext" for a in r["available"])


def test_install_app_takes_backup_fetches_and_installs(client, sid):
    j = wait_job(client, client.post(f"/api/sites/{sid}/install-apps", json={"apps": ["hrms"]}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert any("backup --with-files" in c for c in cmds)
    assert any("get-app" in c and "hrms" in c for c in cmds)
    assert any("install-app" in c and "hrms" in c for c in cmds)
    assert "hrms" in db.q1("SELECT apps FROM sites WHERE id=?", (sid,))["apps"]


def test_update_pulls_then_migrates(client, sid):
    j = wait_job(client, client.post(f"/api/sites/{sid}/update-apps", json={"apps": ["erpnext"]}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    i = next(i for i, c in enumerate(cmds) if "bench update --pull" in c and "--apps erpnext" in c)
    assert any("migrate" in c for c in cmds[i:]) and any("backup --with-files" in c for c in cmds[:i])


def test_update_rejects_bad_names_and_viewers(client, sid):
    assert client.post(f"/api/sites/{sid}/update-apps", json={"apps": ["x; rm -rf /"]}).status_code == 400
    c = TestClient(main.app)
    if not db.q1("SELECT 1 FROM users WHERE username='vera2'"):
        client.post("/api/team", json={"username": "vera2", "password": "password123", "role": "viewer"})
    c.post("/api/auth/login", json={"username": "vera2", "password": "password123"})
    assert c.post(f"/api/sites/{sid}/install-apps", json={"apps": ["hrms"]}).status_code == 403


def test_custom_repo_without_version_branch_falls_back_to_default_branch(client, sid):
    db.x("INSERT OR REPLACE INTO apps(name,title,git_url,branch,requires) VALUES('custom_app','Custom','https://github.com/x/custom_app.git',NULL,'')")
    FakeRunner.no_branch = True
    j = wait_job(client, client.post(f"/api/sites/{sid}/install-apps", json={"apps": ["custom_app"]}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    assert "default branch 'main'" in j["log"]
    assert any("--branch main" in c[1] for c in FakeRunner.calls)
