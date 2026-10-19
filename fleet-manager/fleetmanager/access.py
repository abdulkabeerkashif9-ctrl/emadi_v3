"""Who is calling (session -> user + role), what they may do, and the audit trail."""
from fastapi import Depends, HTTPException, Request

from . import db, security

ROLES = {"viewer": 1, "support": 2, "admin": 3}
ROLE_HELP = {"viewer": "Read-only", "support": "Day-to-day operations", "admin": "Everything, including servers, team and deletions"}


def user(request: Request) -> dict:
    name = security.read_token(request.cookies.get("fm_session", ""))
    row = db.q1("SELECT username, role, disabled FROM users WHERE username=?", (name,)) if name else None
    if not row or row["disabled"]:
        raise HTTPException(401, "Not logged in")
    return {"username": row["username"], "role": row["role"] if row["role"] in ROLES else "admin"}


def need(role: str):
    def dep(u: dict = Depends(user)) -> dict:
        if ROLES[u["role"]] < ROLES[role]:
            raise HTTPException(403, f"Your role ({u['role']}) cannot do this. Ask an administrator.")
        return u
    return dep


def audit(u, action: str, target: str = "", detail: str = "", request: Request | None = None):
    name = u["username"] if isinstance(u, dict) else str(u or "")
    role = u.get("role", "") if isinstance(u, dict) else ""
    ip = request.client.host if request is not None and request.client else ""
    db.x("INSERT INTO audit(user,role,action,target,detail,ip) VALUES(?,?,?,?,?,?)", (name, role, action, target, detail[:500], ip))
