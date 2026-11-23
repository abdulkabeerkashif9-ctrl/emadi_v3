from fleetmanager import db
from test_flow import login


def test_apps_list_survives_an_old_database_without_server_apps(client):
    login(client)
    with db.conn() as c:
        c.execute("DROP TABLE IF EXISTS server_apps")
    r = client.get("/api/apps")
    assert r.status_code == 200
    assert any(a["name"] == "erpnext" for a in r.json())
    assert db.q("SELECT 1 FROM server_apps LIMIT 1") == []   # schema was restored


def test_unexpected_error_shows_its_cause(client, monkeypatch):
    login(client)
    from fleetmanager import main

    real_q = main.db.q

    def boom(sql, args=()):
        if "FROM apps" in sql:
            raise RuntimeError("disk on fire")
        return real_q(sql, args)

    monkeypatch.setattr(main.db, "q", boom)
    c = client.__class__(main.app, raise_server_exceptions=False)
    c.cookies.update(client.cookies)
    r = c.get("/api/apps")
    assert r.status_code == 500 and "RuntimeError: disk on fire" in r.json()["detail"]
