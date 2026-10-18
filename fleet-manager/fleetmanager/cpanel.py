"""Minimal cPanel UAPI client (API-token auth) for DNS handling on thesmarterp.com."""
import requests

from . import db, security


class CPanelError(Exception):
    pass


def get_settings():
    rows = {r["key"]: r["value"] for r in db.q("SELECT * FROM settings WHERE key LIKE 'cpanel_%'")}
    if not rows.get("cpanel_host"):
        return None
    return {"host": rows["cpanel_host"], "port": int(rows.get("cpanel_port") or 2083),
            "user": rows.get("cpanel_user", ""), "token": security.decrypt(rows.get("cpanel_token")),
            "verify_tls": rows.get("cpanel_verify", "1") == "1"}


def save_settings(host, port, user, token, verify_tls=True):
    for k, v in (("cpanel_host", host), ("cpanel_port", str(port)), ("cpanel_user", user),
                 ("cpanel_verify", "1" if verify_tls else "0")):
        db.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    if token:  # blank = keep existing
        db.x("INSERT INTO settings(key,value) VALUES('cpanel_token',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
             (security.encrypt(token),))


def call(module, function, **params):
    cfg = get_settings()
    if not cfg:
        raise CPanelError("cPanel is not configured (Settings page)")
    url = f"https://{cfg['host']}:{cfg['port']}/execute/{module}/{function}"
    try:
        r = requests.get(url, params=params, timeout=25, verify=cfg["verify_tls"],
                         headers={"Authorization": f"cpanel {cfg['user']}:{cfg['token']}"})
        data = r.json()
    except Exception as e:
        raise CPanelError(f"cPanel request failed: {e}")
    if data.get("status") != 1:
        raise CPanelError("; ".join(data.get("errors") or []) or f"cPanel error (HTTP {r.status_code})")
    return data.get("data")


def test():
    call("DomainInfo", "domains_data")
    return True


def managed_domains():
    d = call("DomainInfo", "domains_data") or {}
    out = []
    if d.get("main_domain"):
        out.append(d["main_domain"]["domain"])
    out += [x["domain"] for x in d.get("addon_domains", [])]
    out += [x["domain"] for x in d.get("sub_domains", [])]
    return out


def zone_for(domain):
    """Longest managed zone that `domain` falls under (e.g. a.thesmarterp.com -> thesmarterp.com)."""
    zones = [z for z in managed_domains() if domain == z or domain.endswith("." + z)]
    return max(zones, key=len) if zones else None


def records(zone):
    rows = call("ZoneEdit", "fetchzone_records", domain=zone)
    return rows or []


def find_records(zone, domain):
    name = domain.rstrip(".") + "."
    out = []
    for r in records(zone):
        if r.get("type") in ("A", "AAAA", "CNAME") and (r.get("dname") or "").rstrip(".") + "." == name:
            vals = r.get("data_b64") or r.get("data") or []
            out.append({"type": r["type"], "value": (r.get("record") or (vals[0] if vals else "")), "line": r.get("line")})
    return out


def add_a_record(zone, domain, ip, ttl=300):
    name = domain.rstrip(".") + "."
    return call("ZoneEdit", "add_zone_record", domain=zone, name=name, type="A", address=ip, ttl=ttl)
