import json
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core.env_loader import load_app_env
from backend.core.auth_providers.ad_runtime import (
    LoginConfig,
    get_user_groups_from_ad,
    setup_ad_logger,
    validate_ad_user,
)
from backend.core.database import PortalSessionLocal
from backend.core.models import (
    PortalAdminGrant,
    PortalAdminRole,
    PortalAdGroupMapping,
    PortalAuthSetting,
    PortalLoginAudit,
    PortalUserOverride,
    PortalUserProfile,
)

AD_GROUP_MAPPINGS_SEED_PATH = Path(__file__).resolve().parents[2] / "package_config" / "seed" / "ad_group_mappings.json"
PORTAL_ADMIN_BOOTSTRAP_SEED_PATH = Path(__file__).resolve().parents[2] / "package_config" / "seed" / "portal_admin_bootstrap.json"
AUTH_POLICY_SEED_PATH = Path(__file__).resolve().parents[2] / "package_config" / "seed" / "auth_policy.json"
AUTH_SETTINGS_EDITABLE_KEYS = {"ad_strict_mapping", "ma_cb_ad_attribute"}

load_app_env()

def _now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_room_code(value) -> str:
    value = str(value or "").strip()
    if value.upper() == "AL":
        return "AL"
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-2:].zfill(2) if digits else ""


def _first_non_empty(*values) -> str:
    for value in values:
        value = str(value or "").strip()
        if value and value.lower() not in {"none", "nan", "null", "[]"}:
            return value
    return ""


def _parse_arr_dm(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"nan", "none", "null"}:
        return []
    return [item.strip().upper() for item in raw.split(";") if item.strip()]


def _serialize_json(value) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _deserialize_json(value, default):
    try:
        if not value:
            return default
        return json.loads(value)
    except Exception:
        return default


def _group_set(user_groups) -> set[str]:
    return {str(group).strip().upper() for group in (user_groups or []) if str(group).strip()}


def _has_any_group(current_groups: set[str], configured_groups: list[str]) -> bool:
    return any(str(group).strip().upper() in current_groups for group in configured_groups)


def _ad_value(ad_extra_info: dict, key: str) -> str:
    value = ad_extra_info.get(key, "")
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value or "").strip()


def _extract_ma_cb(ma_cb_attribute: str, username: str, ad_extra_info: dict) -> str:
    candidate = _first_non_empty(
        _ad_value(ad_extra_info, ma_cb_attribute),
        _ad_value(ad_extra_info, "employeeID"),
        _ad_value(ad_extra_info, "employeeNumber"),
        _ad_value(ad_extra_info, "extensionAttribute1"),
        _ad_value(ad_extra_info, "description"),
    )
    digits = "".join(ch for ch in candidate if ch.isdigit())
    if digits:
        return digits[-8:].zfill(8)
    return str(username).strip()


def build_default_ad_group_mappings() -> list[dict]:
    try:
        if not AD_GROUP_MAPPINGS_SEED_PATH.exists():
            return []
        with AD_GROUP_MAPPINGS_SEED_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            return []
        return [row for row in data if isinstance(row, dict)]
    except Exception:
        return []


def build_default_auth_settings() -> dict:
    try:
        if not AUTH_POLICY_SEED_PATH.exists():
            return {}
        with AUTH_POLICY_SEED_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {}
        return {
            key: value
            for key, value in data.items()
            if isinstance(value, dict) and "value" in value
        }
    except Exception:
        return {}


def build_default_portal_admin_bootstrap() -> dict:
    try:
        if not PORTAL_ADMIN_BOOTSTRAP_SEED_PATH.exists():
            return {"roles": [], "grants": []}
        with PORTAL_ADMIN_BOOTSTRAP_SEED_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {"roles": [], "grants": []}
        roles = data.get("roles", [])
        grants = data.get("grants", [])
        return {
            "roles": roles if isinstance(roles, list) else [],
            "grants": grants if isinstance(grants, list) else [],
        }
    except Exception:
        return {"roles": [], "grants": []}


def _ensure_default_auth_settings(db: Session) -> None:
    default_settings = build_default_auth_settings()
    changed = False
    for key, cfg in default_settings.items():
        row = db.query(PortalAuthSetting).filter(PortalAuthSetting.setting_key == key).one_or_none()
        if row:
            continue
        db.merge(
            PortalAuthSetting(
                setting_key=key,
                setting_value=str(cfg.get("value", "")),
                description=cfg.get("description", ""),
                updated_by="system_seed",
                updated_at=_now_str(),
            ),
        )
        changed = True
    if changed:
        db.commit()


def _ensure_default_ad_group_mappings(db: Session) -> None:
    if db.query(PortalAdGroupMapping).count() > 0:
        return
    default_rows = build_default_ad_group_mappings()
    if not default_rows:
        return
    now = _now_str()
    for row in default_rows:
        db.add(
            PortalAdGroupMapping(
                mapping_type=row.get("mapping_type", ""),
                ad_group_name=row.get("ad_group_name", ""),
                is_active=int(row.get("is_active", 1)),
                priority=int(row.get("priority", 100)),
                position_code=row.get("position_code", ""),
                department_code=row.get("department_code", ""),
                department_name=row.get("department_name", ""),
                first_group=row.get("first_group", ""),
                arr_dm=row.get("arr_dm", ""),
                function_code=row.get("function_code", ""),
                flag_admin=int(row.get("flag_admin", 0)),
                flag_bgd=int(row.get("flag_bgd", 0)),
                flag_truong_phong=int(row.get("flag_truong_phong", 0)),
                flag_lanh_dao_phong=int(row.get("flag_lanh_dao_phong", 0)),
                flag_dau_moi=int(row.get("flag_dau_moi", 0)),
                notes=row.get("notes", ""),
                created_at=now,
                updated_at=now,
                updated_by="system_seed",
            )
        )
    db.commit()


def _ensure_default_portal_admin_bootstrap(db: Session) -> None:
    has_roles = db.query(PortalAdminRole).count() > 0
    has_grants = db.query(PortalAdminGrant).count() > 0
    if has_roles or has_grants:
        return

    seed = build_default_portal_admin_bootstrap()
    roles = seed.get("roles", [])
    grants = seed.get("grants", [])
    now = _now_str()

    for row in roles:
        username = str(row.get("username", "")).strip().lower()
        if not username:
            continue
        db.add(
            PortalAdminRole(
                username=username,
                admin_level=int(row.get("admin_level", 1) or 1),
                is_active=int(row.get("is_active", 1) or 0),
                notes=str(row.get("notes", "") or ""),
                granted_by="system_seed",
                updated_at=now,
            )
        )

    db.flush()

    for row in grants:
        username = str(row.get("username", "")).strip().lower()
        section_key = str(row.get("section_key", "")).strip()
        if not username or not section_key:
            continue
        db.add(
            PortalAdminGrant(
                username=username,
                section_key=section_key,
                can_view=int(row.get("can_view", 1) or 0),
                can_edit=int(row.get("can_edit", 0) or 0),
                is_active=int(row.get("is_active", 1) or 0),
                notes=str(row.get("notes", "") or ""),
                granted_by="system_seed",
                updated_at=now,
            )
        )

    db.commit()


def import_ad_group_mappings_from_legacy_source(db: Session, updated_by: str = "system_import") -> list[dict]:
    rows = build_default_ad_group_mappings()
    if not rows:
        return []
    return replace_ad_group_mappings(db, rows, updated_by=updated_by)


def ensure_portal_identity_seed(db: Session) -> None:
    _ensure_default_auth_settings(db)
    _ensure_default_ad_group_mappings(db)
    _ensure_default_portal_admin_bootstrap(db)


def get_auth_settings(db: Session) -> dict:
    ensure_portal_identity_seed(db)
    rows = db.query(PortalAuthSetting).all()
    settings = {}
    for row in rows:
        settings[row.setting_key] = {
            "value": row.setting_value,
            "description": row.description or "",
            "updated_by": row.updated_by or "",
            "updated_at": row.updated_at or "",
        }
    env_auth_mode = str(os.environ.get("PORTAL_AUTH_MODE", "")).strip().upper() or "DEV"
    env_dev_login_enabled = _parse_bool(os.environ.get("PORTAL_DEV_LOGIN_ENABLED", "1"), True)
    settings["auth_mode"] = {
        "value": env_auth_mode,
        "description": "Che do dang nhap runtime. Chi doc tu file/env, khong sua qua Portal Admin.",
        "updated_by": "env",
        "updated_at": "",
    }
    settings["dev_login_enabled"] = {
        "value": "1" if env_dev_login_enabled else "0",
        "description": "Co cho phep DEV login hay khong. Chi doc tu file/env, khong sua qua Portal Admin.",
        "updated_by": "env",
        "updated_at": "",
    }
    return settings


def get_auth_runtime_config(db: Session) -> dict:
    settings = get_auth_settings(db)
    return {
        "auth_mode": str(os.environ.get("PORTAL_AUTH_MODE", "")).strip().upper() or "DEV",
        "dev_login_enabled": _parse_bool(os.environ.get("PORTAL_DEV_LOGIN_ENABLED", "1"), True),
        "ad_strict_mapping": _parse_bool(settings.get("ad_strict_mapping", {}).get("value", "1"), True),
        "ma_cb_ad_attribute": str(settings.get("ma_cb_ad_attribute", {}).get("value", "employeeID")).strip() or "employeeID",
        "settings": settings,
    }


def update_auth_settings(db: Session, settings: dict, updated_by: str) -> dict:
    ensure_portal_identity_seed(db)
    now = _now_str()
    for key, value in settings.items():
        if key not in AUTH_SETTINGS_EDITABLE_KEYS:
            continue
        row = db.query(PortalAuthSetting).filter(PortalAuthSetting.setting_key == key).one_or_none()
        if not row:
            row = PortalAuthSetting(setting_key=key, description="")
            db.add(row)
        row.setting_value = str(value)
        row.updated_by = updated_by
        row.updated_at = now
    db.commit()
    return get_auth_settings(db)


def list_ad_group_mappings(db: Session, mapping_type: str | None = None) -> list[dict]:
    ensure_portal_identity_seed(db)
    query = db.query(PortalAdGroupMapping)
    if mapping_type:
        query = query.filter(PortalAdGroupMapping.mapping_type == mapping_type)
    rows = query.order_by(PortalAdGroupMapping.mapping_type, PortalAdGroupMapping.priority, PortalAdGroupMapping.id).all()
    return [
        {
            "id": row.id,
            "mapping_type": row.mapping_type,
            "ad_group_name": row.ad_group_name,
            "is_active": int(row.is_active or 0),
            "priority": int(row.priority or 100),
            "position_code": row.position_code or "",
            "department_code": row.department_code or "",
            "department_name": row.department_name or "",
            "first_group": row.first_group or "",
            "arr_dm": row.arr_dm or "",
            "function_code": row.function_code or "",
            "flag_admin": int(row.flag_admin or 0),
            "flag_bgd": int(row.flag_bgd or 0),
            "flag_truong_phong": int(row.flag_truong_phong or 0),
            "flag_lanh_dao_phong": int(row.flag_lanh_dao_phong or 0),
            "flag_dau_moi": int(row.flag_dau_moi or 0),
            "notes": row.notes or "",
            "updated_at": row.updated_at or "",
            "updated_by": row.updated_by or "",
        }
        for row in rows
    ]


def replace_ad_group_mappings(db: Session, rows: list[dict], updated_by: str) -> list[dict]:
    db.query(PortalAdGroupMapping).delete()
    now = _now_str()
    for row in rows:
        db.add(
            PortalAdGroupMapping(
                mapping_type=str(row.get("mapping_type", "")).strip(),
                ad_group_name=str(row.get("ad_group_name", "")).strip(),
                is_active=int(row.get("is_active", 1)),
                priority=int(row.get("priority", 100)),
                position_code=str(row.get("position_code", "")).strip(),
                department_code=str(row.get("department_code", "")).strip(),
                department_name=str(row.get("department_name", "")).strip(),
                first_group=str(row.get("first_group", "")).strip(),
                arr_dm=str(row.get("arr_dm", "")).strip(),
                function_code=str(row.get("function_code", "")).strip(),
                flag_admin=int(row.get("flag_admin", 0)),
                flag_bgd=int(row.get("flag_bgd", 0)),
                flag_truong_phong=int(row.get("flag_truong_phong", 0)),
                flag_lanh_dao_phong=int(row.get("flag_lanh_dao_phong", 0)),
                flag_dau_moi=int(row.get("flag_dau_moi", 0)),
                notes=str(row.get("notes", "")).strip(),
                created_at=now,
                updated_at=now,
                updated_by=updated_by,
            )
        )
    db.commit()
    return list_ad_group_mappings(db)


def list_user_profiles(db: Session, limit: int = 100) -> list[dict]:
    rows = (
        db.query(PortalUserProfile)
        .order_by(PortalUserProfile.last_login_at.desc(), PortalUserProfile.username.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "username": row.username,
            "auth_mode": row.auth_mode or "",
            "name_str": row.name_str or "",
            "display_name": row.display_name or "",
            "email": row.email or "",
            "ma_cb": row.ma_cb or "",
            "vi_tri": row.vi_tri or "",
            "ma_phong": row.ma_phong or "",
            "department_code": row.department_code or "",
            "department_name": row.department_name or "",
            "first_group": row.first_group or "",
            "arr_dm": _deserialize_json(row.arr_dm_json, []),
            "user_groups": _deserialize_json(row.user_groups_json, []),
            "flags": _deserialize_json(row.flags_json, {}),
            "last_login_at": row.last_login_at or "",
            "last_sync_at": row.last_sync_at or "",
            "is_active": int(row.is_active or 0),
        }
        for row in rows
    ]


def list_user_overrides(db: Session) -> list[dict]:
    rows = db.query(PortalUserOverride).order_by(PortalUserOverride.username.asc()).all()
    return [
        {
            "username": row.username,
            "display_name": row.display_name or "",
            "vi_tri": row.vi_tri or "",
            "ma_cb": row.ma_cb or "",
            "ma_phong": row.ma_phong or "",
            "department_code": row.department_code or "",
            "department_name": row.department_name or "",
            "first_group": row.first_group or "",
            "arr_dm": row.arr_dm or "",
            "is_truong_phong": row.is_truong_phong,
            "is_lanh_dao_phong": row.is_lanh_dao_phong,
            "is_dau_moi": row.is_dau_moi,
            "is_active": int(row.is_active or 0),
            "notes": row.notes or "",
            "updated_by": row.updated_by or "",
            "updated_at": row.updated_at or "",
        }
        for row in rows
    ]


def replace_user_overrides(db: Session, rows: list[dict], updated_by: str) -> list[dict]:
    db.query(PortalUserOverride).delete()
    now = _now_str()
    for row in rows:
        username = str(row.get("username", "")).strip().lower()
        if not username:
            continue
        db.add(
            PortalUserOverride(
                username=username,
                display_name=str(row.get("display_name", "")).strip(),
                vi_tri=str(row.get("vi_tri", "")).strip().upper(),
                ma_cb=str(row.get("ma_cb", "")).strip(),
                ma_phong=_normalize_room_code(row.get("ma_phong", "")),
                department_code=_normalize_room_code(row.get("department_code", "")),
                department_name=str(row.get("department_name", "")).strip(),
                first_group=str(row.get("first_group", "")).strip(),
                arr_dm=str(row.get("arr_dm", "")).strip(),
                is_truong_phong=row.get("is_truong_phong"),
                is_lanh_dao_phong=row.get("is_lanh_dao_phong"),
                is_dau_moi=row.get("is_dau_moi"),
                is_active=int(row.get("is_active", 1)),
                notes=str(row.get("notes", "")).strip(),
                updated_by=updated_by,
                updated_at=now,
            )
        )
    db.commit()
    return list_user_overrides(db)


def list_login_audit(db: Session, limit: int = 100) -> list[dict]:
    rows = db.query(PortalLoginAudit).order_by(PortalLoginAudit.id.desc()).limit(limit).all()
    return [
        {
            "id": row.id,
            "username": row.username or "",
            "auth_mode": row.auth_mode or "",
            "success": int(row.success or 0),
            "error_message": row.error_message or "",
            "profile": _deserialize_json(row.profile_json, {}),
            "created_at": row.created_at or "",
        }
        for row in rows
    ]


def _load_active_overrides(db: Session) -> dict:
    rows = db.query(PortalUserOverride).filter(PortalUserOverride.is_active == 1).all()
    return {row.username.lower(): row for row in rows}


def _load_active_mappings(db: Session) -> list[PortalAdGroupMapping]:
    ensure_portal_identity_seed(db)
    return (
        db.query(PortalAdGroupMapping)
        .filter(PortalAdGroupMapping.is_active == 1)
        .order_by(PortalAdGroupMapping.priority.asc(), PortalAdGroupMapping.id.asc())
        .all()
    )


def _apply_override(user_data: dict, override_row: PortalUserOverride | None) -> dict:
    if not override_row:
        return user_data

    if override_row.display_name:
        user_data["nameStr"] = override_row.display_name
        user_data["displayName"] = override_row.display_name
    if override_row.vi_tri:
        user_data["viTri"] = override_row.vi_tri
    if override_row.ma_cb:
        user_data["maCB"] = override_row.ma_cb
    if override_row.ma_phong:
        user_data["maPhong"] = override_row.ma_phong
    if override_row.department_code:
        user_data["departmentCode"] = override_row.department_code
    if override_row.department_name:
        user_data["departmentName"] = override_row.department_name
    if override_row.first_group:
        user_data["firstGroup"] = override_row.first_group
    if override_row.arr_dm:
        user_data["arrDM"] = _parse_arr_dm(override_row.arr_dm)
    if override_row.is_truong_phong is not None:
        user_data["isTruongPhong"] = bool(override_row.is_truong_phong)
    if override_row.is_lanh_dao_phong is not None:
        user_data["isLanhDaoPhong"] = bool(override_row.is_lanh_dao_phong)
    if override_row.is_dau_moi is not None:
        user_data["isDauMoi"] = bool(override_row.is_dau_moi)
    return user_data


def validate_portal_profile(user_data: dict) -> tuple[bool, str]:
    vi_tri = str(user_data.get("viTri", "")).upper().strip()
    ma_phong = str(user_data.get("maPhong", "")).upper().strip()
    ma_cb = str(user_data.get("maCB", "")).strip()

    if vi_tri not in ["A", "G", "P", "D", "C", "T"]:
        return False, "User chua duoc mapping nhom chuc danh hop le A/G/P/D/C/T."
    if not ma_cb:
        return False, "User chua co Ma can bo. Kiem tra AD attribute hoac user override."
    if vi_tri not in ["A", "G"] and not ma_phong:
        return False, "User chua thuoc group phong/ban/PGD nao trong cau hinh AD mapping."
    if vi_tri in ["P", "D", "C", "T"] and not user_data.get("firstGroup"):
        return False, "User chua xac dinh duoc ten phong/ban/PGD."
    return True, ""


def build_ad_user_profile(db: Session, username: str, user_groups: list[str], ad_extra_info: dict, runtime_config: dict) -> dict:
    mappings = _load_active_mappings(db)
    overrides = _load_active_overrides(db)
    override_row = overrides.get(str(username).strip().lower())
    group_set = _group_set(user_groups)

    login_groups = [row.ad_group_name for row in mappings if row.mapping_type == "login_access"]
    allowed_login = _has_any_group(group_set, login_groups)

    position_rows = [row for row in mappings if row.mapping_type == "position" and row.ad_group_name.strip().upper() in group_set]
    department_rows = [row for row in mappings if row.mapping_type == "department" and row.ad_group_name.strip().upper() in group_set]
    function_rows = [row for row in mappings if row.mapping_type == "function" and row.ad_group_name.strip().upper() in group_set]

    is_admin = any(bool(row.flag_admin) for row in position_rows)
    is_bgd = any(bool(row.flag_bgd) for row in position_rows)
    is_lanh_dao_phong = any(bool(row.flag_lanh_dao_phong) for row in position_rows)
    is_truong_phong = any(bool(row.flag_truong_phong) for row in position_rows)
    is_explicit_dau_moi = any(bool(row.flag_dau_moi) for row in position_rows + department_rows)

    arr_dm = []
    for row in department_rows:
        arr_dm.extend(_parse_arr_dm(row.arr_dm))
    for row in function_rows:
        if row.function_code:
            arr_dm.append(str(row.function_code).strip().upper())
    arr_dm = list(dict.fromkeys(arr_dm))

    user_data = {
        "success": True,
        "authMode": "AD",
        "username": str(username).strip(),
        "nameStr": _first_non_empty(_ad_value(ad_extra_info, "displayName"), username),
        "displayName": _ad_value(ad_extra_info, "displayName"),
        "mail": _ad_value(ad_extra_info, "mail"),
        "viTri": "C",
        "maPhong": "",
        "departmentCode": "",
        "departmentName": "",
        "maCB": _extract_ma_cb(runtime_config["ma_cb_ad_attribute"], username, ad_extra_info),
        "firstGroup": "",
        "arrDM": arr_dm,
        "isAdmin": is_admin,
        "isBGD": is_bgd,
        "isTruongPhong": is_truong_phong,
        "isLanhDaoPhong": is_lanh_dao_phong,
        "isDauMoi": is_explicit_dau_moi,
        "userGroups": user_groups,
        "adAttributes": ad_extra_info,
    }

    if is_admin:
        user_data["viTri"] = "A"
    elif is_bgd:
        user_data["viTri"] = "G"
    elif is_lanh_dao_phong:
        user_data["viTri"] = "P"
    elif is_explicit_dau_moi:
        user_data["viTri"] = "D"

    if department_rows:
        first_department = department_rows[0]
        department_code = _normalize_room_code(first_department.department_code)
        department_name = first_department.department_name or first_department.first_group or ""
        first_group = first_department.first_group or department_name
        user_data["departmentCode"] = department_code
        user_data["departmentName"] = department_name
        user_data["firstGroup"] = first_group
        if not is_admin and not is_bgd:
            user_data["maPhong"] = department_code
    elif is_admin:
        user_data["departmentCode"] = "AL"
        user_data["departmentName"] = "Admin"
        user_data["firstGroup"] = "Admin"
    elif is_bgd:
        user_data["departmentCode"] = "AL"
        user_data["departmentName"] = "Ban Giam doc"
        user_data["firstGroup"] = "Ban Giam doc"

    if is_admin or is_bgd:
        user_data["maPhong"] = "AL"
    elif user_data["viTri"] not in ["P", "D"]:
        user_data["viTri"] = "D" if user_data["departmentCode"] in ["03", "13", "18"] else "C"

    real_department_code = user_data.get("departmentCode") or user_data.get("maPhong")
    user_data["isDauMoi"] = bool(
        is_explicit_dau_moi or real_department_code in ["03", "13", "18"] or user_data["viTri"] == "D"
    )

    if is_admin:
        user_data["arrDM"] = ["ALL"]
    elif is_bgd:
        user_data["arrDM"] = []

    user_data = _apply_override(user_data, override_row)

    is_mapped, mapping_error = validate_portal_profile(user_data)
    user_data["isAllowedToLogin"] = allowed_login
    user_data["isMappedForPortal"] = is_mapped
    user_data["mappingError"] = mapping_error
    return user_data


def sync_user_profile(db: Session, user_data: dict) -> None:
    username = str(user_data.get("username", "")).strip().lower()
    if not username:
        return
    now = _now_str()
    row = db.query(PortalUserProfile).filter(PortalUserProfile.username == username).one_or_none()
    if not row:
        row = PortalUserProfile(username=username)
        db.add(row)
    row.auth_mode = str(user_data.get("authMode", "")).strip()
    row.name_str = user_data.get("nameStr", "")
    row.display_name = user_data.get("displayName", "") or user_data.get("nameStr", "")
    row.email = user_data.get("mail", "")
    row.ma_cb = user_data.get("maCB", "")
    row.vi_tri = user_data.get("viTri", "")
    row.ma_phong = user_data.get("maPhong", "")
    row.department_code = user_data.get("departmentCode", "")
    row.department_name = user_data.get("departmentName", "")
    row.first_group = user_data.get("firstGroup", "")
    row.arr_dm_json = _serialize_json(user_data.get("arrDM", []))
    row.user_groups_json = _serialize_json(user_data.get("userGroups", []))
    row.flags_json = _serialize_json(
        {
            "isAdmin": bool(user_data.get("isAdmin")),
            "isBGD": bool(user_data.get("isBGD")),
            "isTruongPhong": bool(user_data.get("isTruongPhong")),
            "isLanhDaoPhong": bool(user_data.get("isLanhDaoPhong")),
            "isDauMoi": bool(user_data.get("isDauMoi")),
            "isAllowedToLogin": bool(user_data.get("isAllowedToLogin")),
            "isMappedForPortal": bool(user_data.get("isMappedForPortal")),
        }
    )
    row.ad_attributes_json = _serialize_json(user_data.get("adAttributes", {}))
    row.last_login_at = now
    row.last_sync_at = now
    row.is_active = 1
    db.commit()


def record_login_audit(db: Session, username: str, auth_mode: str, success: bool, error_message: str = "", profile: dict | None = None) -> None:
    db.add(
        PortalLoginAudit(
            username=str(username or "").strip().lower(),
            auth_mode=str(auth_mode or "").strip().upper(),
            success=1 if success else 0,
            error_message=str(error_message or "").strip(),
            profile_json=_serialize_json(profile or {}),
            created_at=_now_str(),
        )
    )
    db.commit()


def authenticate_ad_user(username: str, password: str, runtime_config: dict) -> dict:
    username = str(username or "").strip()
    config = LoginConfig()
    logger = setup_ad_logger()

    is_valid, validation_error = validate_ad_user(config, logger, username, password)
    if not is_valid:
        return {"error": validation_error or "Dang nhap AD that bai.", "username": username}

    user_groups, ad_extra_info, group_error = get_user_groups_from_ad(config, logger, username, password)
    if group_error:
        return {"error": group_error, "username": username}

    with PortalSessionLocal() as db:
        user_data = build_ad_user_profile(db, username, user_groups, ad_extra_info, runtime_config)

    if not user_data.get("isAllowedToLogin"):
        return {
            "error": "User khong thuoc nhom duoc phep dang nhap portal.",
            "username": username,
            "userGroups": user_groups,
            "adAttributes": ad_extra_info,
        }

    strict_mapping = bool(runtime_config.get("ad_strict_mapping", True))
    if strict_mapping and not user_data.get("isMappedForPortal"):
        return {
            "error": user_data.get("mappingError") or "User AD chua duoc mapping day du cho portal.",
            "username": username,
            "userGroups": user_groups,
            "adAttributes": ad_extra_info,
            "profile": user_data,
        }

    return user_data
