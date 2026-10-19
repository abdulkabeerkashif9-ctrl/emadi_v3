"""Send alerts to Telegram, email (SMTP) and a generic webhook. Never raises: returns a result per channel."""
import json
import smtplib
import time
from email.message import EmailMessage

import requests

from . import db, security

DEFAULTS = {
    "telegram": {"enabled": False, "token": "", "chat_id": ""},
    "email": {"enabled": False, "host": "", "port": 587, "user": "", "password": "", "from": "", "to": "", "starttls": True},
    "webhook": {"enabled": False, "url": ""},
}
SECRETS = {"telegram": ["token"], "email": ["password"], "webhook": ["url"]}  # masked when shown in the UI


def get_config():
    raw = db.setting("notify")
    cfg = json.loads(security.decrypt(raw)) if raw else {}
    return {ch: {**d, **(cfg.get(ch) or {})} for ch, d in DEFAULTS.items()}


def masked():
    cfg = get_config()
    out = {}
    for ch, c in cfg.items():
        out[ch] = {k: ("" if k in SECRETS[ch] else v) for k, v in c.items()} | {f"has_{k}": bool(c.get(k)) for k in SECRETS[ch]}
    return out


def save(new):
    """Merge posted settings; blank secret fields keep the stored value."""
    cur = get_config()
    for ch, d in DEFAULTS.items():
        for k in d:
            if k in (new.get(ch) or {}):
                v = new[ch][k]
                if k in SECRETS[ch] and v in ("", None):
                    continue
                if isinstance(d[k], bool):
                    v = bool(v)
                elif isinstance(d[k], int):
                    v = int(v)
                else:
                    v = str(v).strip()
                cur[ch][k] = v
    db.set_setting("notify", security.encrypt(json.dumps(cur)))


def _telegram(c, title, body):
    r = requests.post(f"https://api.telegram.org/bot{c['token']}/sendMessage", timeout=15,
                      json={"chat_id": c["chat_id"], "text": f"{title}\n{body}"[:4000]})
    if r.status_code != 200:
        raise RuntimeError(f"Telegram said HTTP {r.status_code}: {r.text[:120]}")


def _email(c, title, body):
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = title, c["from"] or c["user"], c["to"]
    msg.set_content(body or title)
    with smtplib.SMTP(c["host"], int(c["port"]), timeout=20) as s:
        if c.get("starttls"):
            s.starttls()
        if c.get("user"):
            s.login(c["user"], c["password"])
        s.send_message(msg)


def _webhook(c, title, body, level):
    text = f"{title}\n{body}".strip()
    r = requests.post(c["url"], timeout=15, json={"title": title, "body": body, "level": level, "text": text, "content": text,
                                                     "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "fleet-manager"})
    if r.status_code >= 300:
        raise RuntimeError(f"Webhook said HTTP {r.status_code}")


def send(title, body="", level="info", only=None):
    """Returns {channel: 'ok' | error text} for every enabled channel (empty dict if none is configured)."""
    cfg, res = get_config(), {}
    for ch in ("telegram", "email", "webhook"):
        c = cfg[ch]
        if not c["enabled"] or (only and ch != only):
            continue
        try:
            if ch == "telegram":
                _telegram(c, title, body)
            elif ch == "email":
                _email(c, title, body)
            else:
                _webhook(c, title, body, level)
            res[ch] = "ok"
        except Exception as e:  # a broken channel must never break monitoring
            res[ch] = f"{type(e).__name__}: {e}"[:200]
    return res


def configured():
    return any(c["enabled"] for c in get_config().values())
