import json
import hmac
import os
from pathlib import Path

from backend.core.database import PortalSessionLocal
from backend.core.env_loader import load_app_env
from backend.core.models import PortalAdminRole, PortalUserProfile
from backend.core.portal_identity import authenticate_ad_user, get_auth_runtime_config

load_app_env()

DEV_USERS_SEED_PATH = Path(__file__).resolve().parents[2] / "package_config" / "seed" / "dev_users.json"


def load_dev_users() -> dict:
    try:
        if not DEV_USERS_SEED_PATH.exists():
            return {}
        with DEV_USERS_SEED_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {}
        return {str(key).strip().lower(): value for key, value in data.items() if isinstance(value, dict)}
    except Exception:
        return {}


def _build_emergency_user_profile(username: str) -> dict:
    user_key = str(username or "").strip().lower()
    with PortalSessionLocal() as db:
        profile = db.query(PortalUserProfile).filter(PortalUserProfile.username == user_key).one_or_none()
        role = db.query(PortalAdminRole).filter(PortalAdminRole.username == user_key, PortalAdminRole.is_active == 1).one_or_none()

    is_admin = bool(role and int(role.admin_level or 99) <= 1)
    if not profile:
        return {
            "success": True,
            "username": user_key,
            "maCB": user_key,
            "authMode": "EMERGENCY",
            "userGroups": [],
            "departmentCode": "AL" if is_admin else "",
            "departmentName": "Admin" if is_admin else "",
            "displayName": user_key,
            "nameStr": user_key,
            "mail": "",
            "arrDM": ["ALL"] if is_admin else [],
            "isAllowedToLogin": True,
            "isMappedForPortal": True,
            "mappingError": "",
            "isAdmin": is_admin,
            "isBGD": False,
            "isTruongPhong": False,
            "isLanhDaoPhong": False,
            "isDauMoi": is_admin,
            "viTri": "A" if is_admin else "",
            "maPhong": "AL" if is_admin else "",
            "firstGroup": "Admin" if is_admin else "",
            "adAttributes": {},
        }

    flags = json.loads(profile.flags_json or "{}") if profile.flags_json else {}
    user_groups = json.loads(profile.user_groups_json or "[]") if profile.user_groups_json else []
    arr_dm = json.loads(profile.arr_dm_json or "[]") if profile.arr_dm_json else []
    return {
        "success": True,
        "username": user_key,
        "maCB": profile.ma_cb or user_key,
        "authMode": "EMERGENCY",
        "userGroups": user_groups if isinstance(user_groups, list) else [],
        "departmentCode": profile.department_code or "",
        "departmentName": profile.department_name or "",
        "displayName": profile.display_name or profile.name_str or user_key,
        "nameStr": profile.name_str or profile.display_name or user_key,
        "mail": profile.email or "",
        "arrDM": arr_dm if isinstance(arr_dm, list) else [],
        "isAllowedToLogin": True,
        "isMappedForPortal": True,
        "mappingError": "",
        "isAdmin": bool(flags.get("isAdmin", False)) or is_admin,
        "isBGD": bool(flags.get("isBGD", False)),
        "isTruongPhong": bool(flags.get("isTruongPhong", False)),
        "isLanhDaoPhong": bool(flags.get("isLanhDaoPhong", False)),
        "isDauMoi": bool(flags.get("isDauMoi", False)),
        "viTri": profile.vi_tri or "",
        "maPhong": profile.ma_phong or "",
        "firstGroup": profile.first_group or "",
        "adAttributes": {},
    }


def _try_emergency_login(username: str, password: str) -> dict | None:
    enabled = str(os.environ.get("PORTAL_EMERGENCY_LOGIN_ENABLED", "0")).strip().lower() in {"1", "true", "yes", "on"}
    fallback_user = str(os.environ.get("PORTAL_EMERGENCY_USER", "lh.hiep")).strip().lower()
    fallback_password = os.environ.get("PORTAL_EMERGENCY_PASSWORD", "")
    user_key = str(username or "").strip().lower()
    password_text = str(password or "")
    if not enabled or not fallback_password or user_key != fallback_user:
        return None
    if not hmac.compare_digest(password_text, fallback_password):
        return None
    return _build_emergency_user_profile(user_key)

def authenticate_user(username, password):
    """
    Hàm xác thực người dùng cho hệ mới.
    Chỉ hỗ trợ DEV và AD. Tuyệt đối không lưu mật khẩu.
    """
    db = PortalSessionLocal()
    try:
        runtime_config = get_auth_runtime_config(db)
    finally:
        db.close()

    mode = str(os.environ.get("PORTAL_AUTH_MODE", "")).strip().upper() or "DEV"
    dev_login_enabled = str(os.environ.get("PORTAL_DEV_LOGIN_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
    
    if mode == "DEV":
        if not dev_login_enabled:
            return {"error": "Che do DEV dang bi khoa trong cau hinh he thong."}
        dev_users = load_dev_users()
        user_key = str(username).strip().lower()
        if user_key in dev_users:
            # Chế độ DEV không kiểm tra mật khẩu để tiện test
            user_data = dict(dev_users[user_key])
            user_data["success"] = True
            user_data["username"] = user_key
            user_data["maCB"] = user_key
            user_data["authMode"] = "DEV"
            user_data["userGroups"] = user_data.get("userGroups", [])
            user_data["departmentCode"] = user_data.get("maPhong", "")
            user_data["departmentName"] = user_data.get("firstGroup", "")
            user_data["displayName"] = user_data.get("nameStr", "")
            user_data["mail"] = ""
            user_data["arrDM"] = user_data.get("arrDM", [])
            user_data["isAllowedToLogin"] = True
            user_data["isMappedForPortal"] = True
            user_data["mappingError"] = ""
            return user_data
        else:
            supported_users = ", ".join(dev_users.keys())
            return {"error": f"User DEV không tồn tại. Vui lòng dùng: {supported_users}"}
            
    elif mode in {"AD", "LDAP"}:
        result = authenticate_ad_user(username, password, runtime_config)
        if result.get("success"):
            return result
        emergency_result = _try_emergency_login(username, password)
        if emergency_result:
            return emergency_result
        return result
    
    return {"error": f"Che do xac thuc {mode} chua duoc ho tro. He thong moi chi ho tro DEV va AD."}
