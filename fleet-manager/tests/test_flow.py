import subprocess
import time

from fleetmanager import db, domains, provision, security
from conftest import FakeRunner


def login(client):
    st = client.get("/api/auth/state").json()
    if st["setup_needed"]:
        assert client.post("/api/auth/setup", json={"username": "admin", "password": "password123"}).status_code == 200
    else:
        client.post("/api/auth/login", json={"username": "admin", "password": "password123"})


def wait_job(client, jid):
    for _ in range(100):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.1)
    raise AssertionError("job hung")


def test_requires_login(client):
    client.cookies.clear()
    assert client.get("/api/servers").status_code == 401
    assert client.get("/api/auth/state").json()["setup_needed"] is True
    login(client)
    assert client.get("/api/servers").status_code == 200
    assert client.post("/api/auth/setup", json={"username": "x" * 5, "password": "password123"}).status_code == 403
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"}).status_code == 401
    login(client)


def test_builtin_apps_and_ordering(client):
    login(client)
    names = {a["name"] for a in client.get("/api/apps").json()}
    assert {"erpnext", "hrms", "crm"} <= names
    assert provision.order_apps(["hrms"]) == ["erpnext", "hrms"]   # dependency pulled in first
    r = client.post("/api/apps", json={"name": "my_app", "git_url": "https://github.com/me/my_app", "requires": "erpnext"})
    assert r.status_code == 200
    assert client.post("/api/apps", json={"name": "bad", "git_url": "https://x.com/a; rm -rf /"}).status_code == 400
    assert client.delete("/api/apps/erpnext").status_code == 400
    assert client.delete("/api/apps/my_app").status_code == 200


def test_server_lifecycle_and_scripts(client, tmp_path):
    login(client)
    s = client.post("/api/servers", json={"name": "vps1", "ip": "203.0.113.10", "ssh_user": "root", "auth_type": "password",
                                          "secret": "hunter2", "version": "version-15"}).json()
    assert "secret" not in s and "secret_enc" not in s and s["status"] == "new"
    assert "hunter2" not in str(db.q("SELECT secret_enc FROM servers"))          # encrypted at rest
    sid = s["id"]
    assert client.post(f"/api/servers/{sid}/test").json()["ok"]
    boot = client.get(f"/api/servers/{sid}/bootstrap.sh").text
    pub = client.get("/api/manager-key").json()["public_key"]
    assert pub in boot
    conf = provision.configure_script(db.q1("SELECT * FROM servers WHERE id=?", (sid,)), "pw")
    for name, text in (("boot", boot), ("conf", conf)):
        f = tmp_path / f"{name}.sh"
        f.write_text(text)
        assert subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True).returncode == 0, name
    assert "--frappe-branch version-15" in conf and "python3.11" in conf and "setup_18.x" in conf

    jid = client.post(f"/api/servers/{sid}/configure").json()["job_id"]
    assert wait_job(client, jid)["status"] == "done"
    s = client.get("/api/servers").json()[0]
    assert s["status"] == "ready" and s["apps"] == ["erpnext"] and s["capacity"]["ok"]
    sites = client.get("/api/sites").json()                       # existing site discovered, company read
    assert [(x["domain"], x["company"]) for x in sites] == [("old.example.com", "Old Co")]
    assert client.post(f"/api/servers/{sid}/configure").status_code == 409


def test_domain_check_and_recommend(client, monkeypatch):
    login(client)
    monkeypatch.setattr(domains, "resolve", lambda d: [])
    assert not domains.check("not a domain")["ok"]
    assert not domains.check("old.example.com")["ok"]               # already a site in the fleet
    assert domains.check("new.example.com")["ok"]
    rec = client.get("/api/recommend").json()
    assert len(rec) == 1 and rec[0]["recommended"]
    # a loaded server is not recommended
    db.x("UPDATE servers SET metrics=? WHERE name='vps1'", ('{"load":9,"cores":2,"mem_total_mb":4000,"mem_pct":50,"disk_pct":10}',))
    rec = client.get("/api/recommend").json()
    assert not rec[0]["ok"] and not rec[0]["recommended"] and "CPU" in rec[0]["reasons"][0]
    db.x("UPDATE servers SET metrics=? WHERE name='vps1'", ('{"load":0.3,"cores":2,"mem_total_mb":4000,"mem_pct":30,"disk_pct":35}',))


def test_create_site_asks_before_installing_missing_app(client, monkeypatch):
    login(client)
    monkeypatch.setattr(domains, "resolve", lambda d: [])
    sid = client.get("/api/servers").json()[0]["id"]
    pre = client.post("/api/sites/precheck", json={"server_id": sid, "apps": ["hrms"]}).json()
    assert pre["install_order"] == ["erpnext", "hrms"] and pre["missing_on_server"] == ["hrms"]
    body = {"domain": "Acme.Example.com", "company": "Acme Ltd", "server_id": sid, "apps": ["hrms"]}
    r = client.post("/api/sites", json=body)
    assert r.status_code == 409 and r.json()["detail"]["missing_on_server"] == ["hrms"]
    r = client.post("/api/sites", json=body | {"install_missing": True})
    assert r.status_code == 200
    assert wait_job(client, r.json()["job_id"])["status"] == "done"
    cmds = [c[1] for c in FakeRunner.calls if c[0] == "run"]
    order = [i for i, c in enumerate(cmds) if "get-app" in c or "new-site" in c or "install-app" in c or "setup nginx" in c]
    text = [cmds[i] for i in order]
    assert "get-app" in text[0] and "hrms" in text[0] and "version-15" in text[0]
    assert "new-site acme.example.com" in text[1]
    assert "install-app erpnext" in text[2] and "install-app hrms" in text[3] and "setup nginx" in text[4]
    site = [x for x in client.get("/api/sites").json() if x["domain"] == "acme.example.com"][0]
    assert site["company"] == "Acme Ltd" and site["ip"] == "203.0.113.10"
    cred = client.get(f"/api/sites/{site['id']}/credentials").json()
    assert len(cred["password"]) >= 16
    # duplicate domain is refused
    assert client.post("/api/sites", json=body | {"install_missing": True}).status_code == 400


def test_failed_job_marks_site_error(client, monkeypatch):
    login(client)
    monkeypatch.setattr(domains, "resolve", lambda d: [])
    sid = client.get("/api/servers").json()[0]["id"]
    orig = FakeRunner.run
    monkeypatch.setattr(FakeRunner, "run", lambda self, cmd, **k: (1, "boom") if "new-site" in cmd else orig(self, cmd, **k))
    r = client.post("/api/sites", json={"domain": "bad.example.com", "server_id": sid, "apps": ["erpnext"]})
    assert wait_job(client, r.json()["job_id"])["status"] == "failed"
    assert [x for x in client.get("/api/sites").json() if x["domain"] == "bad.example.com"][0]["status"] == "error"


def test_cookie_tamper(client):
    client.cookies.set("fm_session", "garbage")
    assert client.get("/api/servers").status_code == 401
    login(client)
