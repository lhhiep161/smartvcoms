import json
import secrets
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import text

from backend.core.database import PortalSessionLocal
from backend.core.portal_identity import record_login_audit, sync_user_profile
from backend.core.database import portal_engine

router = APIRouter(prefix="/api", tags=["Auth"])

def _ensure_auth_sessions_table() -> None:
    with portal_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                user_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))


def _save_session(token: str, user: dict) -> None:
    _ensure_auth_sessions_table()
    with portal_engine.begin() as conn:
        conn.execute(
            text("""
                INSERT OR REPLACE INTO auth_sessions (token, user_json, created_at)
                VALUES (:token, :user_json, CURRENT_TIMESTAMP)
            """),
            {"token": token, "user_json": json.dumps(user, ensure_ascii=False)},
        )


def _load_session(token: str) -> dict | None:
    _ensure_auth_sessions_table()
    with portal_engine.begin() as conn:
        row = conn.execute(
            text("SELECT user_json FROM auth_sessions WHERE token = :token"),
            {"token": token},
        ).fetchone()
    if not row or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _delete_session(token: str) -> None:
    _ensure_auth_sessions_table()
    with portal_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM auth_sessions WHERE token = :token"),
            {"token": token},
        )

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Chưa đăng nhập hoặc thiếu Token")
    token = authorization.split(" ")[1]
    user = _load_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập đã hết hạn")
    return user

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(req: LoginRequest):
    from backend.core.auth import authenticate_user
    result = authenticate_user(req.username, req.password)
    if result.get("success"):
        token = secrets.token_hex(24)
        _save_session(token, result)
        db = PortalSessionLocal()
        try:
            sync_user_profile(db, result)
            record_login_audit(
                db,
                username=result.get("username", req.username),
                auth_mode=result.get("authMode", ""),
                success=True,
                profile=result,
            )
        finally:
            db.close()
        return {"status": "success", "token": token, "user": result}
    else:
        db = PortalSessionLocal()
        try:
            record_login_audit(
                db,
                username=req.username,
                auth_mode="UNKNOWN",
                success=False,
                error_message=result.get("error", "Đăng nhập thất bại."),
            )
        finally:
            db.close()
        return {"status": "error", "message": result.get("error", "Đăng nhập thất bại.")}


@router.post("/logout")
def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        _delete_session(token)
    return {"status": "success", "message": "Đăng xuất thành công."}
