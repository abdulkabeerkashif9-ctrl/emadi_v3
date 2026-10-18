"""Minimal cPanel UAPI client (API-token auth) for DNS handling on thesmarterp.com."""
import time

import requests

from . import db, security


class CPanelError(Exception):
    pass


def get_settings():
    rows = {r["key"]: r["value"] for r in db.q("SELECT * FROM settings WHERE key LIKE 'cpanel_%'")}
    if not rows.get("cpanel_host"):
        return None
    return {"host": rows["cpanel_host"], "port": int(rows.get("cpanel_port") or 2083),
            "user": rows.get("cpanel_user", ""), "token": security.decrypt(rows.get("cpanel_token")), "auth": rows.get("cpanel_auth", "token"),
            "verify_tls": rows.get("cpanel_verify", "1") == "1"}


def save_settings(host, port, user, token, verify_tls=True, auth="token"):
    for k, v in (("cpanel_host", host), ("cpanel_port", str(port)), ("cpanel_user", user),
                 ("cpanel_verify", "1" if verify_tls else "0"), ("cpanel_auth", auth)):
        db.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    if token:  # blank = keep existing
        db.x("INSERT INTO settings(key,value) VALUES('cpanel_token',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
             (security.encrypt(token),))


_cache = {"key": None, "session": None, "token": None, "at": 0.0}


def _session_login(cfg, force=False):
    """Same flow as the browser login form: POST credentials, keep the session cookie + security token."""
    key = (cfg["host"], cfg["port"], cfg["user"], cfg["token"])
    if not force and _cache["key"] == key and time.time() - _cache["at"] < 600:
        return _cache["session"], _cache["token"]
    s = requests.Session()
    s.verify = cfg["verify_tls"]
    base = f"https://{cfg['host']}:{cfg['port']}"
    try:
        r = s.post(f"{base}/login/?login_only=1", data={"user": cfg["user"], "pass": cfg["token"]},
                   timeout=25, allow_redirects=False)
        j = r.json()
    except requests.RequestException as e:
        raise CPanelError(f"cPanel request failed: {e}")
    except ValueError:
        raise CPanelError(f"cPanel login returned HTTP {r.status_code} that was not JSON - check host/port.")
    if r.status_code != 200 or not j.get("security_token"):
        raise CPanelError(f"cPanel rejected the login for '{cfg['user']}' ({j.get('message') or 'invalid_login'}). "
                          "Check username/password; two-factor must be off for password login.")
    _cache.update(key=key, session=s, token=j["security_token"], at=time.time())
    return s, j["security_token"]


def call(module, function, **params):
    cfg = get_settings()
    if not cfg:
        raise CPanelError("cPanel is not configured (Settings page)")
    base = f"https://{cfg['host']}:{cfg['port']}"
    for attempt in (1, 2):
        try:
            if cfg["auth"] == "password":
                sess, tok = _session_login(cfg, force=attempt == 2)
                url = f"{base}{tok}/execute/{module}/{function}"
                r = sess.get(url, params=params, timeout=25, allow_redirects=False)
            else:
                url = f"{base}/execute/{module}/{function}"
                r = requests.get(url, params=params, timeout=25, verify=cfg["verify_tls"], allow_redirects=False,
                                 headers={"Authorization": f"cpanel {cfg['user']}:{cfg['token']}"})
        except requests.RequestException as e:
            raise CPanelError(f"cPanel request failed: {e}")
        try:
            data = r.json()
            break
        except ValueError:
            if cfg["auth"] == "password" and attempt == 1:
                continue  # session expired: log in again once
            snippet = " ".join(r.text.split())[:160]
            hint = ("This is not the cPanel API. Check host/port: use the exact address you open cPanel with "
                    "(usually port 2083, or 443 for cpanel.yourdomain.com), and that it is not your website or a proxy.")
            if r.status_code in (301, 302, 303, 307, 308):
                hint = f"Redirected to {r.headers.get('Location')} - use that host/port, or check username/password."
            elif r.status_code in (401, 403):
                hint = "Login rejected - check username and API token (the host may also have API tokens disabled)."
            raise CPanelError(f"HTTP {r.status_code} from {url} (signed in as '{cfg['user']}' using {cfg['auth']}) "
                              f"was not JSON: '{snippet}'. {hint}")
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
