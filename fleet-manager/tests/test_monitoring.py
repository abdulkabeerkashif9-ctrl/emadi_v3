import json
import ssl
import time

import pytest

from fleetmanager import db, monitor, notify, security
from conftest import FakeRunner


@pytest.fixture
def sent(monkeypatch):
    """Capture alerts instead of calling Telegram/SMTP."""
    out = []
    monkeypatch.setattr(notify, "send", lambda title, body="", level="info", only=None: out.append((title, body, level)) or {"test": "ok"})
    return out


@pytest.fixture
def site(client):
    from test_flow import login
    login(client)
    srv = db.q1("SELECT id FROM servers LIMIT 1")
    db.x("DELETE FROM sites WHERE domain='mon.example.com'")
    sid = db.x("INSERT INTO sites(server_id,domain,status,admin_pw_enc) VALUES(?,?,?,?)", (srv["id"], "mon.example.com", "up", security.encrypt("x")))
    db.x("DELETE FROM incidents"); db.x("DELETE FROM checks")
    yield sid


def feed(site_id, results):
    for ok in results:
        monitor.record_check(site_id, "public", ok)
        monitor.evaluate_site(site_id)


def test_site_down_needs_consecutive_failures_and_prior_success(site, sent):
    feed(site, [0, 0, 0])
    assert not db.q("SELECT * FROM incidents")                       # never been up: a brand-new site is not an outage
    feed(site, [1, 0, 0])
    assert not db.q("SELECT * FROM incidents") and not sent          # only 2 failures
    feed(site, [0])
    inc = db.q1("SELECT * FROM incidents")
    assert inc["kind"] == "site_down" and inc["severity"] == "crit" and inc["status"] == "open"
    assert len(sent) == 1 and "mon.example.com" in sent[0][0]
    feed(site, [0, 0])
    assert len(db.q("SELECT * FROM incidents")) == 1 and len(sent) == 1   # de-duplicated, no alert spam
    feed(site, [1])
    assert db.q1("SELECT status FROM incidents")["status"] == "open"      # needs 2 good checks
    feed(site, [1])
    assert db.q1("SELECT status FROM incidents")["status"] == "resolved"
    assert len(sent) == 2 and sent[1][0].startswith("🟢 Recovered")


def test_origin_result_explains_where_it_breaks(site, sent):
    monitor.record_check(site, "origin", True)
    feed(site, [1, 0, 0, 0])
    assert db.q1("SELECT title FROM incidents")["title"] == "Not reachable from the internet"
    db.x("DELETE FROM incidents"); monitor.record_check(site, "origin", False)
    feed(site, [0])
    assert db.q1("SELECT title FROM incidents")["title"] == "Site is down"


def test_suspended_sites_do_not_alert(site, sent):
    db.x("UPDATE sites SET suspended=1 WHERE id=?", (site,))
    feed(site, [1, 0, 0, 0, 0])
    assert not db.q("SELECT * FROM incidents") and not sent


def test_reminders_respect_acknowledgement(site, sent, monkeypatch):
    feed(site, [1, 0, 0, 0])
    iid = db.q1("SELECT id FROM incidents")["id"]
    db.x("UPDATE incidents SET last_notified=? WHERE id=?", (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 3 * 3600)), iid))
    monitor.ack_incident(iid, "sue")
    feed(site, [0]); assert len(sent) == 1                                 # acknowledged: no reminder
    db.x("UPDATE incidents SET acked_by=NULL WHERE id=?", (iid,))
    feed(site, [0]); assert len(sent) == 2 and sent[1][0].startswith("⏰")
    assert monitor.close_incident(iid, "sue") and db.q1("SELECT resolved_by FROM incidents")["resolved_by"] == "sue"
    assert len(sent) == 2                                                  # manual close is silent


def test_run_site_checks_updates_site_and_uptime(site, sent, monkeypatch):
    monkeypatch.setattr(monitor, "_http_ping", lambda d: (d != "bad.example.com", 42, 200))
    assert monitor.run_site_checks() >= 1
    row = db.q1("SELECT status, public_ok FROM sites WHERE id=?", (site,))
    assert row["status"] == "up" and row["public_ok"] == 1
    assert monitor.uptime(site, 24) == 100.0
    assert monitor.bars(site)[-1] == "ok" and monitor.bars(site)[0] == "none"
    monkeypatch.setattr(monitor, "_http_ping", lambda d: (False, 9, 0))
    monitor.run_site_checks()
    assert db.q1("SELECT status FROM sites WHERE id=?", (site,))["status"] == "down"
    assert monitor.uptime(site, 24) == 50.0 and monitor.summary()["sites"]


def probe_ok():
    return ({"load": 0.2, "cores": 2, "mem_total_mb": 4000, "mem_pct": 40, "disk_pct": 30, "os": "Ubuntu"},
            {"svc": {"nginx": "active", "mariadb": "active"}, "sup": {"web": "RUNNING"}, "port": {"11000": "up", "13000": "up"}, "origin": {"mon.example.com": True}})


def test_server_checks_disk_services_and_autoheal(site, sent, monkeypatch):
    srv = db.q1("SELECT * FROM servers LIMIT 1")
    monkeypatch.setattr(monitor, "_server_probe", lambda s, d: probe_ok())
    monitor.run_server_checks(srv["id"])
    assert not db.q("SELECT * FROM incidents") and db.q1("SELECT ok FROM checks WHERE kind='origin'")["ok"] == 1
    m, p = probe_ok(); m["disk_pct"] = 88
    monkeypatch.setattr(monitor, "_server_probe", lambda s, d: (m, p)); monitor.run_server_checks(srv["id"])
    assert db.q1("SELECT severity FROM incidents WHERE kind='disk'")["severity"] == "warn"
    m["disk_pct"] = 95; monitor.run_server_checks(srv["id"])
    assert db.q1("SELECT severity FROM incidents WHERE kind='disk'")["severity"] == "crit" and any(t.startswith("🔴") for t, *_ in sent)
    m["disk_pct"] = 50; monitor.run_server_checks(srv["id"])
    assert db.q1("SELECT status FROM incidents WHERE kind='disk'")["status"] == "resolved"
    # service down: alert, and only heal when the admin enabled it
    m2, p2 = probe_ok(); p2["svc"]["nginx"] = "failed"; p2["port"]["11000"] = "down"
    monkeypatch.setattr(monitor, "_server_probe", lambda s, d: (m2, p2))
    FakeRunner.calls.clear(); monitor.run_server_checks(srv["id"])
    inc = db.q1("SELECT * FROM incidents WHERE kind='service'")
    assert "nginx" in inc["detail"] and "11000" in inc["detail"] and not any(c[0] == "run" and "restart" in c[1] for c in FakeRunner.calls)
    db.x("DELETE FROM incidents WHERE kind='service'"); monitor.save_settings({"autoheal": True})
    monitor.run_server_checks(srv["id"]); monitor.run_server_checks(srv["id"])
    healed = [c[1] for c in FakeRunner.calls if c[0] == "run" and "restart" in c[1]]
    assert len(healed) == 1 and "systemctl restart nginx" in healed[0] and "supervisorctl restart all" in healed[0]   # once per incident
    assert "Auto-heal ran" in db.q1("SELECT detail FROM incidents WHERE kind='service'")["detail"]
    assert db.q1("SELECT 1 FROM audit WHERE user='system' AND action='auto_heal'")
    monitor.save_settings({"autoheal": False})
    monkeypatch.setattr(monitor, "_server_probe", lambda s, d: probe_ok()); monitor.run_server_checks(srv["id"])
    assert db.q1("SELECT status FROM incidents WHERE kind='service'")["status"] == "resolved"


def test_unreachable_server_opens_incident_after_two_failures(site, sent, monkeypatch):
    srv = db.q1("SELECT * FROM servers LIMIT 1")
    def boom(s, d): raise OSError("timed out")
    monkeypatch.setattr(monitor, "_server_probe", boom)
    monitor.run_server_checks(srv["id"]); assert not db.q("SELECT * FROM incidents WHERE kind='server_down'")
    monitor.run_server_checks(srv["id"]); assert db.q1("SELECT severity FROM incidents WHERE kind='server_down'")["severity"] == "crit"
    monkeypatch.setattr(monitor, "_server_probe", lambda s, d: probe_ok()); monitor.run_server_checks(srv["id"])
    assert db.q1("SELECT status FROM incidents WHERE kind='server_down'")["status"] == "resolved"


def test_ssl_expiry_levels(site, sent, monkeypatch):
    for days, sev in ((30, None), (10, "warn"), (2, "crit")):
        monkeypatch.setattr(monitor, "_cert_days", lambda d, days=days: days)
        monitor.run_ssl_checks()
        row = db.q1("SELECT severity, status FROM incidents WHERE kind='ssl' AND target_id=?", (site,))
        assert (row["severity"] if row and row["status"] == "open" else None) == sev
    def bad(d): raise ssl.SSLCertVerificationError("certificate has expired")
    monkeypatch.setattr(monitor, "_cert_days", bad); monitor.run_ssl_checks()
    assert "expired" in db.q1("SELECT detail FROM incidents WHERE kind='ssl' AND status='open'")["detail"]
    monkeypatch.setattr(monitor, "_cert_days", lambda d: None); monitor.run_ssl_checks()      # no HTTPS: nothing to check


def test_settings_validation_and_prune(site):
    with pytest.raises(ValueError):
        monitor.save_settings({"disk_warn": 95, "disk_crit": 90})
    with pytest.raises(ValueError):
        monitor.save_settings({"down_after": 0})
    assert monitor.save_settings({"down_after": 5})["down_after"] == 5; monitor.save_settings({"down_after": 3})
    db.x("INSERT INTO checks(site_id,ts,kind,ok) VALUES(?,?,?,1)", (site, "2020-01-01 00:00:00", "public"))
    monitor.prune()
    assert not db.q("SELECT * FROM checks WHERE ts < '2021-01-01'")


def test_notification_channels(monkeypatch):
    calls = []
    class Resp:
        def __init__(s, code=200): s.status_code, s.text = code, "x"
    monkeypatch.setattr(notify.requests, "post", lambda url, **k: calls.append((url, k.get("json"))) or Resp())
    class SMTP:
        def __init__(s, host, port, timeout=0): calls.append(("smtp", host, port))
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def starttls(s): calls.append("starttls")
        def login(s, u, p): calls.append(("login", u))
        def send_message(s, m): calls.append(("mail", m["To"], m["Subject"]))
    monkeypatch.setattr(notify.smtplib, "SMTP", SMTP)
    assert notify.send("t") == {} and not notify.configured()
    notify.save({"telegram": {"enabled": True, "token": "123:abc", "chat_id": "42"},
                 "email": {"enabled": True, "host": "smtp.example.com", "port": "587", "user": "u", "password": "pw", "from": "a@b.c", "to": "x@y.z"},
                 "webhook": {"enabled": True, "url": "https://hooks.example.com/abc"}})
    assert notify.configured() and "pw" not in json.dumps(notify.masked()) and notify.masked()["email"]["has_password"]
    res = notify.send("Hello", "World", "crit")
    assert res == {"telegram": "ok", "email": "ok", "webhook": "ok"}
    assert any(c[0] == "https://api.telegram.org/bot123:abc/sendMessage" for c in calls if isinstance(c, tuple) and isinstance(c[0], str))
    hook = [c for c in calls if isinstance(c, tuple) and c[0] == "https://hooks.example.com/abc"][0][1]
    assert hook["text"] == "Hello\nWorld" and hook["content"] == hook["text"] and hook["level"] == "crit"
    assert ("mail", "x@y.z", "Hello") in calls and "starttls" in calls
    notify.save({"telegram": {"token": "", "chat_id": "99"}})                       # blank secret keeps the stored one
    assert notify.get_config()["telegram"]["token"] == "123:abc" and notify.get_config()["telegram"]["chat_id"] == "99"
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: Resp(500))
    assert notify.send("x", only="telegram")["telegram"].startswith("RuntimeError")  # failures are reported, never raised
    db.x("DELETE FROM settings WHERE key='notify'")
