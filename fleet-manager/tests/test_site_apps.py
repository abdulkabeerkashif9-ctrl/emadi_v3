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


def test_update_resets_each_app_to_the_remote_then_builds_and_migrates(client, sid):
    FakeRunner.diverged = True                      # history differs (shallow clone / force push): must not fail like `git pull`
    j = wait_job(client, client.post(f"/api/sites/{sid}/update-apps", json={"apps": ["erpnext"]}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    assert "history differs" in j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert not any("bench update" in c or "git pull" in c for c in cmds)
    i = next(i for i, c in enumerate(cmds) if "reset --hard refs/remotes/upstream/version-15" in c and "apps/erpnext" in c)
    assert any("backup --with-files" in c for c in cmds[:i]) and any("fetch --force upstream +refs/heads/version-15:refs/remotes/upstream/version-15" in c for c in cmds[:i])
    tail = cmds[i:]
    assert [k for k in ("setup requirements", "bench build --apps erpnext", "migrate") if any(k in c for c in tail)] == ["setup requirements", "bench build --apps erpnext", "migrate"]


def test_update_refuses_server_side_edits_unless_forced(client, sid):
    FakeRunner.dirty = " M erpnext/hooks.py\n"
    j = wait_job(client, client.post(f"/api/sites/{sid}/update-apps", json={"apps": ["erpnext"]}).json()["job_id"])
    assert j["status"] == "failed" and "changes made directly on the server" in j["log"]
    assert not any("reset --hard" in c[1] for c in FakeRunner.calls if c[0] == "run")
    j = wait_job(client, client.post(f"/api/sites/{sid}/update-apps", json={"apps": ["erpnext"], "force": True}).json()["job_id"])
    assert j["status"] == "done", j["log"]


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


def test_empty_app_is_named_after_the_subdomain_and_installed(client, sid):
    from fleetmanager import ops
    assert ops.empty_app_name("test9.thesmarterp.com") == "test9" and ops.empty_app_name("9shop.x.com") == "app_9shop" and ops.empty_app_name("My-Shop.x.com") == "my_shop" and ops.empty_app_name("erpnext.x.com") == "erpnext_app"
    r = client.post(f"/api/sites/{sid}/empty-app").json()
    assert r["app"] == "apps"
    j = wait_job(client, r["job_id"])
    assert j["status"] == "done", j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    i = next(i for i, c in enumerate(cmds) if "bench new-app apps" in c)
    assert any("install-app apps" in c for c in cmds[i:])
    assert "apps" in db.q1("SELECT apps FROM sites WHERE id=?", (sid,))["apps"]


def test_upload_db_restores_and_removes_the_local_file(client, sid):
    from fleetmanager import config
    url = f"/api/sites/{sid}/upload-db?filename=dump.sql.gz&confirm="
    assert client.put(url + "wrong.example.com", content=b"x").status_code == 400
    assert client.put(f"/api/sites/{sid}/upload-db?filename=evil.sh&confirm=apps.example.com", content=b"x").status_code == 400
    assert client.put(url + "apps.example.com", content=b"").status_code == 400
    r = client.put(url + "apps.example.com", content=b"-- sql dump --")
    assert r.status_code == 200
    j = wait_job(client, r.json()["job_id"])
    assert j["status"] == "done", j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert any("backup --with-files" in c for c in cmds)
    assert any("--force restore" in c and "/tmp/fm-upload-" in c and "database.sql.gz" in c for c in cmds)
    assert FakeRunner.relayed and not list((config.DATA_DIR / "uploads").glob("*"))


def test_upload_db_is_admin_only(client, sid):
    c = TestClient(main.app)
    if not db.q1("SELECT 1 FROM users WHERE username='sue2'"):
        client.post("/api/team", json={"username": "sue2", "password": "password123", "role": "support"})
    c.post("/api/auth/login", json={"username": "sue2", "password": "password123"})
    assert c.put(f"/api/sites/{sid}/upload-db?filename=d.sql&confirm=apps.example.com", content=b"x").status_code == 403


def test_delete_survives_a_dropped_connection_if_the_site_is_gone(client, sid):
    from fleetmanager import ops
    FakeRunner.drop_exit = -1                       # command "fails" with exit -1 but the folder is removed
    j = wait_job(client, __import__("fleetmanager").jobs.start("ops", "drop", lambda log: ops.drop_job(sid, False, log)))
    assert j["status"] == "done", j["log"]
    assert "deletion went through" in j["log"] and not db.q1("SELECT 1 FROM sites WHERE id=?", (sid,))


def test_delete_reports_failure_if_the_site_is_still_there(client, sid):
    from fleetmanager import ops
    FakeRunner.drop_exit, FakeRunner.leftover = 1, "real"
    j = wait_job(client, __import__("fleetmanager").jobs.start("ops", "drop", lambda log: ops.drop_job(sid, False, log)))
    assert j["status"] == "failed" and "drop-site failed (exit 1)" in j["log"] and db.q1("SELECT 1 FROM sites WHERE id=?", (sid,))
    assert sum("drop-site" in c[1] for c in FakeRunner.calls if c[0] == "run") == 2     # one retry


def test_uninstall_app_backs_up_removes_and_updates_the_site(client, sid):
    wait_job(client, client.post(f"/api/sites/{sid}/install-apps", json={"apps": ["hrms"]}).json()["job_id"])
    assert "hrms" in db.q1("SELECT apps FROM sites WHERE id=?", (sid,))["apps"]
    assert client.post(f"/api/sites/{sid}/uninstall-app", json={"app": "hrms", "confirm": "nope"}).status_code == 400
    assert client.post(f"/api/sites/{sid}/uninstall-app", json={"app": "frappe", "confirm": "frappe"}).status_code == 400
    db.x("UPDATE sites SET apps='' WHERE id!=?", (sid,))           # other tests' sites must not look like users of hrms
    j = wait_job(client, client.post(f"/api/sites/{sid}/uninstall-app", json={"app": "hrms", "confirm": "hrms", "remove_from_server": True}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    i = next(i for i, c in enumerate(cmds) if "uninstall-app hrms" in c and "--yes" in c)
    assert any("backup --with-files" in c for c in cmds[:i]) and any("bench remove-app hrms" in c for c in cmds[i:])
    assert "hrms" not in db.q1("SELECT apps FROM sites WHERE id=?", (sid,))["apps"]


def test_uninstall_refused_when_another_app_needs_it_or_server_removal_when_shared(client, sid):
    wait_job(client, client.post(f"/api/sites/{sid}/install-apps", json={"apps": ["hrms"]}).json()["job_id"])
    FakeRunner.site_installed.append("erpnext")
    j = wait_job(client, client.post(f"/api/sites/{sid}/uninstall-app", json={"app": "erpnext", "confirm": "erpnext"}).json()["job_id"])
    assert j["status"] == "failed" and "Remove hrms first" in j["log"]
    srv = db.q1("SELECT server_id FROM sites WHERE id=?", (sid,))["server_id"]
    db.x("DELETE FROM sites WHERE domain='other.example.com'")
    db.x("INSERT OR REPLACE INTO sites(server_id,domain,apps,status,admin_pw_enc) VALUES(?,?,?,?,?)", (srv, "other.example.com", "hrms", "up", security.encrypt("x")))
    j = wait_job(client, client.post(f"/api/sites/{sid}/uninstall-app", json={"app": "hrms", "confirm": "hrms", "remove_from_server": True}).json()["job_id"])
    assert j["status"] == "failed" and "other.example.com" in j["log"]
    db.x("DELETE FROM sites WHERE domain='other.example.com'")


def test_uninstall_is_admin_only(client, sid):
    c = TestClient(main.app)
    if not db.q1("SELECT 1 FROM users WHERE username='sue3'"):
        client.post("/api/team", json={"username": "sue3", "password": "password123", "role": "support"})
    c.post("/api/auth/login", json={"username": "sue3", "password": "password123"})
    assert c.post(f"/api/sites/{sid}/uninstall-app", json={"app": "hrms", "confirm": "hrms"}).status_code == 403


def test_remove_app_from_server_only_when_no_site_uses_it(client, sid):
    srv = db.q1("SELECT server_id FROM sites WHERE id=?", (sid,))["server_id"]
    FakeRunner.apps.append("lonely_app")
    url = f"/api/servers/{srv}/remove-app"
    assert client.post(url, json={"app": "lonely_app", "confirm": "x"}).status_code == 400
    assert client.post(url, json={"app": "frappe", "confirm": "frappe"}).status_code == 400
    FakeRunner.site_installed.append("lonely_app")                     # a site still has it
    j = wait_job(client, client.post(url, json={"app": "lonely_app", "confirm": "lonely_app"}).json()["job_id"])
    assert j["status"] == "failed" and "still installed on" in j["log"]
    FakeRunner.site_installed.clear()
    j = wait_job(client, client.post(url, json={"app": "lonely_app", "confirm": "lonely_app"}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    assert "lonely_app" not in FakeRunner.apps


def test_get_app_failure_names_the_missing_dependency_not_the_branch(client, sid):
    db.x("INSERT OR REPLACE INTO apps(name,title,git_url,branch,requires) VALUES('garm','Garm','https://github.com/x/garm.git','main','')")
    FakeRunner.build_broken = True
    j = wait_job(client, client.post(f"/api/sites/{sid}/install-apps", json={"apps": ["garm"]}).json()["job_id"])
    assert j["status"] == "failed" and "emadi_v3" in j["log"] and "no branch" not in j["log"]


def test_scheduler_enable_runs_enable_resume_and_checks_worker(client, sid):
    r = client.post(f"/api/sites/{sid}/scheduler", json={"on": True})
    assert r.status_code == 200 and r.json()["on"] is True
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert any("enable-scheduler" in c for c in cmds) and any("scheduler resume" in c for c in cmds)
    assert client.post(f"/api/sites/{sid}/scheduler", json={"on": False}).status_code == 200
    assert any("disable-scheduler" in c[1] for c in FakeRunner.calls if c[0] == "run")


def test_developer_mode_toggle_and_state(client, sid):
    assert client.get(f"/api/sites/{sid}/developer-mode").json() == {"on": False}
    assert client.post(f"/api/sites/{sid}/developer-mode", json={"on": True}).json() == {"on": True}
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    assert any("set-config developer_mode 1" in c for c in cmds)
    assert client.post(f"/api/sites/{sid}/developer-mode", json={"on": False}).json() == {"on": False}
    c = TestClient(main.app)
    if not db.q1("SELECT 1 FROM users WHERE username='sue4'"):
        client.post("/api/team", json={"username": "sue4", "password": "password123", "role": "support"})
    c.post("/api/auth/login", json={"username": "sue4", "password": "password123"})
    assert c.post(f"/api/sites/{sid}/developer-mode", json={"on": True}).status_code == 403 and c.get(f"/api/sites/{sid}/developer-mode").status_code == 200


def test_app_folder_present_but_not_installed_is_repaired_before_install_app(client, sid):
    FakeRunner.apps.append("hrms")            # folder is on the server already, so get-app is skipped
    FakeRunner.not_importable = True
    j = wait_job(client, client.post(f"/api/sites/{sid}/install-apps", json={"apps": ["hrms"]}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    i = next(i for i, c in enumerate(cmds) if "pip install" in c and "-e apps/hrms" in c)
    assert any("install-app hrms" in c for c in cmds[i:]) and "installing it now" in j["log"]
    assert any("--no-deps" in c for c in cmds)


def test_app_missing_from_apps_txt_is_registered_and_built(client, sid):
    FakeRunner.apps.append("hrms")
    FakeRunner.not_in_apps_txt = True
    j = wait_job(client, client.post(f"/api/sites/{sid}/install-apps", json={"apps": ["hrms"]}).json()["job_id"])
    assert j["status"] == "done", j["log"]
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    i = next(i for i, c in enumerate(cmds) if "sites/apps.txt" in c and "echo " in c)
    assert any("install-app hrms" in c for c in cmds[i:]) and any("bench build --app hrms" in c for c in cmds[i:])
