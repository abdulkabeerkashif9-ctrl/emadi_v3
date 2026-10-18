"""Is a domain usable for a new site?"""
import re
import socket

import requests

from . import cpanel, db

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalise(d):
    return (d or "").strip().lower().rstrip(".")


def resolve(domain):
    try:
        return sorted({i[4][0] for i in socket.getaddrinfo(domain, None, socket.AF_INET)})
    except OSError:
        return []


def rdap_registered(domain):
    """True/False if the registry knows the domain, None if we couldn't tell."""
    try:
        r = requests.get(f"https://rdap.org/domain/{domain}", timeout=10, allow_redirects=True)
        if r.status_code == 404:
            return False
        if r.status_code == 200:
            return True
    except requests.RequestException:
        pass
    return None


def check(domain):
    """Returns {ok, domain, problems[], notes[], dns_ips[], zone}. ok means 'safe to create a site here'."""
    domain = normalise(domain)
    res = {"domain": domain, "ok": False, "problems": [], "notes": [], "dns_ips": [], "zone": None}
    if not DOMAIN_RE.match(domain):
        res["problems"].append("Not a valid domain name")
        return res
    existing = db.q1("SELECT s.domain, v.name AS server FROM sites s JOIN servers v ON v.id=s.server_id WHERE s.domain=?", (domain,))
    if existing:
        res["problems"].append(f"Already used by a site on server '{existing['server']}'")
    res["dns_ips"] = resolve(domain)
    if res["dns_ips"]:
        mine = {r["ip"] for r in db.q("SELECT ip FROM servers")}
        if set(res["dns_ips"]) <= mine:
            res["notes"].append("DNS already points to one of your servers: " + ", ".join(res["dns_ips"]))
        else:
            res["notes"].append("DNS currently points elsewhere: " + ", ".join(res["dns_ips"])
                                + " (you will need to change it, or use cPanel DNS below)")
    if cpanel.get_settings():
        try:
            res["zone"] = cpanel.zone_for(domain)
            if res["zone"]:
                recs = cpanel.find_records(res["zone"], domain)
                if recs:
                    res["notes"].append("cPanel DNS already has: " + ", ".join(f"{r['type']} {r['value']}" for r in recs))
                else:
                    res["notes"].append(f"Zone {res['zone']} is in your cPanel; an A record can be created automatically")
            else:
                reg = rdap_registered(domain)
                if reg is False:
                    res["notes"].append("Domain is not registered yet - register it first")
                    res["problems"].append("Domain is not registered")
                elif reg:
                    res["notes"].append("Domain is registered outside this cPanel; point its DNS to the VPS manually")
        except cpanel.CPanelError as e:
            res["notes"].append(f"cPanel check skipped: {e}")
    res["ok"] = not res["problems"]
    return res
