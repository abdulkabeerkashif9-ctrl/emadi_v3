import base64
import hashlib
import hmac
import os
import secrets
import time

from cryptography.fernet import Fernet

from . import config


def _fernet():
    config.ensure_dirs()
    if not config.KEY_PATH.exists():
        config.KEY_PATH.write_bytes(Fernet.generate_key())
        try:
            os.chmod(config.KEY_PATH, 0o600)
        except OSError:
            pass
    return Fernet(config.KEY_PATH.read_bytes())


def encrypt(s):
    return _fernet().encrypt(s.encode()).decode() if s else None


def decrypt(s):
    return _fernet().decrypt(s.encode()).decode() if s else None


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 240_000).hex()
    return f"{salt}${h}"


def check_pw(pw, stored):
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_pw(pw, salt), stored)


def _secret():
    return _fernet()._signing_key  # stable per-install secret for signing cookies


def make_token(username):
    exp = int(time.time()) + config.SESSION_HOURS * 3600
    body = f"{username}|{exp}"
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode()


def read_token(tok):
    try:
        user, exp, sig = base64.urlsafe_b64decode(tok.encode()).decode().rsplit("|", 2)
        good = hmac.new(_secret(), f"{user}|{exp}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, good) and int(exp) > time.time():
            return user
    except Exception:
        pass
    return None


def gen_password(n=20):
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))
