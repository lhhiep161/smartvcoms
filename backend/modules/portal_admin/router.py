from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.database import get_portal_db
from backend.core.models import PortalAdminGrant, PortalAdminRole
from backend.core.portal_identity import (
    get_auth_settings,
    list_ad_group_mappings,
    list_login_audit,
    list_user_overrides,
    list_user_profiles,
    replace_ad_group_mappings,
    replace_user_overrides,
    update_auth_settings,
)
from backend.core.portal_permissions import (
    list_page_permissions,
)
from backend.core.portal_permission_engine import assert_permission
from backend.modules.auth.router import get_current_user

router = APIRouter(prefix="/api/portal-admin", tags=["PortalAdmin"])


class AuthSettingsUpdateRequest(BaseModel):
    settings: dict


class RowsUpdateRequest(BaseModel):
    rows: list[dict]


class AdminManagementUpdateRequest(BaseModel):
    roles: list[dict]
    grants: list[dict]


def _assert_portal_admin(current_user: dict, part_id: str, action: str = "view", message: str = "Không có quyền truy cập quản trị hệ thống.") -> None:
    try:
        assert_permission(current_user, "PortalAdmin", action=action, part_id=part_id, message=message)
    except HTTPException:
        raise


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _list_admin_roles(db: Session) -> list[dict]:
    rows = db.query(PortalAdminRole).order_by(PortalAdminRole.admin_level.asc(), PortalAdminRole.username.asc()).all()
    return [
        {
            "username": row.username,
            "admin_level": int(row.admin_level or 2),
            "is_active": int(row.is_active or 0),
            "notes": row.notes or "",
            "granted_by": row.granted_by or "",
            "updated_at": row.updated_at or "",
        }
        for row in rows
    ]


def _list_admin_grants(db: Session) -> list[dict]:
    rows = db.query(PortalAdminGrant).order_by(PortalAdminGrant.username.asc(), PortalAdminGrant.section_key.asc()).all()
    return [
        {
            "id": row.id,
            "username": row.username,
            "section_key": row.section_key,
            "can_view": int(row.can_view or 0),
            "can_edit": int(row.can_edit or 0),
            "is_active": int(row.is_active or 0),
            "notes": row.notes or "",
            "granted_by": row.granted_by or "",
            "updated_at": row.updated_at or "",
        }
        for row in rows
    ]


def _replace_admin_management(db: Session, roles_payload: list[dict], grants_payload: list[dict], updated_by: str) -> dict:
    now = _now_text()

    db.query(PortalAdminGrant).delete()
    db.query(PortalAdminRole).delete()
    db.flush()

    for item in roles_payload:
        username = str(item.get("username", "")).strip()
        if not username:
            continue
        db.add(
            PortalAdminRole(
                username=username,
                admin_level=int(item.get("admin_level", 2) or 2),
                is_active=int(item.get("is_active", 1) or 0),
                notes=str(item.get("notes", "") or ""),
                granted_by=updated_by,
                updated_at=now,
            )
        )

    db.flush()

    for item in grants_payload:
        username = str(item.get("username", "")).strip()
        section_key = str(item.get("section_key", "")).strip()
        if not username or not section_key:
            continue
        db.add(
            PortalAdminGrant(
                username=username,
                section_key=section_key,
                can_view=int(item.get("can_view", 1) or 0),
                can_edit=int(item.get("can_edit", 0) or 0),
                is_active=int(item.get("is_active", 1) or 0),
                notes=str(item.get("notes", "") or ""),
                granted_by=updated_by,
                updated_at=now,
            )
        )

    db.commit()
    return {
        "roles": _list_admin_roles(db),
        "grants": _list_admin_grants(db),
    }


def _is_portal_admin_level1(current_user: dict, db: Session) -> bool:
    user_ids = {
        str(current_user.get("username", "")).strip().lower(),
        str(current_user.get("user", "")).strip().lower(),
        str(current_user.get("nameStr", "")).strip().lower(),
        str(current_user.get("displayName", "")).strip().lower(),
        str(current_user.get("maCB", "")).strip().lower(),
        str(current_user.get("mail", "")).strip().lower(),
    } - {""}
    if not user_ids:
        return False
    role = (
        db.query(PortalAdminRole)
        .filter(PortalAdminRole.is_active == 1, PortalAdminRole.admin_level <= 1)
        .all()
    )
    if any((row.username or "").strip().lower() in user_ids for row in role):
        return True
    return bool(current_user.get("isAdmin", False))


@router.get("/overview")
def get_portal_admin_overview(current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "overview", message="Không có quyền xem tổng quan Portal Admin.")
    auth_settings = get_auth_settings(db)
    mappings = list_ad_group_mappings(db)
    overrides = list_user_overrides(db)
    profiles = list_user_profiles(db, limit=500)
    page_permissions = list_page_permissions(db)
    admin_roles = _list_admin_roles(db)
    admin_grants = _list_admin_grants(db)
    return {
        "status": "success",
        "data": {
            "module_id": "portal-admin",
            "title": "Quản trị hệ thống",
            "sections": [
                {
                    "key": "users",
                    "title": "Người dùng",
                    "description": "Quản lý tài khoản, trạng thái hoạt động và thông tin hiển thị.",
                    "status": "in_progress",
                    "count": len(profiles),
                },
                {
                    "key": "roles",
                    "title": "Vai trò và phân quyền",
                    "description": "Thiết lập quyền truy cập cho SmartVCOMS.",
                    "status": "in_progress",
                    "count": len(page_permissions),
                },
                {
                    "key": "auth-settings",
                    "title": "Cấu hình đăng nhập",
                    "description": "Quản lý cơ chế phiên đăng nhập và chính sách xác thực.",
                    "status": "in_progress",
                    "count": len(auth_settings),
                },
                {
                    "key": "admin-management",
                    "title": "Quản trị Admin",
                    "description": "Quản trị admin cấp 1/cấp 2 và grant theo khu vực quản trị.",
                    "status": "in_progress",
                    "count": len(admin_roles),
                },
            ],
            "auth_settings": auth_settings,
            "ad_mapping_count": len(mappings),
            "user_override_count": len(overrides),
            "page_permission_count": len(page_permissions),
            "admin_role_count": len(admin_roles),
            "admin_grant_count": len(admin_grants),
            "current_user": {
                "username": current_user.get("username", ""),
                "name": current_user.get("nameStr", ""),
                "is_admin": bool(current_user.get("isAdmin")),
            },
        },
    }


@router.get("/auth-settings")
def get_portal_auth_settings(current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "identity_auth", message="Không có quyền xem cấu hình đăng nhập.")
    return {"status": "success", "data": get_auth_settings(db)}


@router.put("/auth-settings")
def save_portal_auth_settings(req: AuthSettingsUpdateRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "identity_auth", action="edit", message="Không có quyền sửa cấu hình đăng nhập.")
    forbidden_keys = {"auth_mode", "dev_login_enabled"} & set((req.settings or {}).keys())
    if forbidden_keys:
        raise HTTPException(status_code=400, detail="Auth mode và DEV login chỉ cấu hình qua file/env.")
    settings = update_auth_settings(db, req.settings, updated_by=str(current_user.get("username", "system")))
    return {"status": "success", "message": "Đã lưu cấu hình đăng nhập.", "data": settings}


@router.get("/ad-group-mappings")
def get_portal_ad_group_mappings(
    mapping_type: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_portal_db),
):
    _assert_portal_admin(current_user, "ad_mappings", message="Không có quyền xem AD mappings.")
    return {"status": "success", "data": list_ad_group_mappings(db, mapping_type=mapping_type)}


@router.put("/ad-group-mappings")
def save_portal_ad_group_mappings(req: RowsUpdateRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "ad_mappings", action="edit", message="Không có quyền sửa AD mappings.")
    rows = replace_ad_group_mappings(db, req.rows, updated_by=str(current_user.get("username", "system")))
    return {"status": "success", "message": "Đã lưu cấu hình nhóm AD.", "data": rows}


@router.get("/user-profiles")
def get_portal_user_profiles(limit: int = 100, current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "identity_auth", message="Không có quyền xem user profiles.")
    return {"status": "success", "data": list_user_profiles(db, limit=limit)}


@router.get("/user-overrides")
def get_portal_user_overrides(current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "user_overrides", message="Không có quyền xem user overrides.")
    return {"status": "success", "data": list_user_overrides(db)}


@router.put("/user-overrides")
def save_portal_user_overrides(req: RowsUpdateRequest, current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "user_overrides", action="edit", message="Không có quyền sửa user overrides.")
    rows = replace_user_overrides(db, req.rows, updated_by=str(current_user.get("username", "system")))
    return {"status": "success", "message": "Đã lưu user override.", "data": rows}


@router.get("/login-audit")
def get_portal_login_audit(limit: int = 100, current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "identity_auth", message="Không có quyền xem login audit.")
    return {"status": "success", "data": list_login_audit(db, limit=limit)}


@router.get("/page-permissions")
def get_portal_page_permissions(
    module_id: str = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_portal_db),
):
    _assert_portal_admin(current_user, "portal_permissions", message="Không có quyền xem quyền portal.")
    return {"status": "success", "data": list_page_permissions(db, module_id=module_id)}


@router.get("/admin-management")
def get_portal_admin_management(current_user: dict = Depends(get_current_user), db: Session = Depends(get_portal_db)):
    _assert_portal_admin(current_user, "admin_management", message="Không có quyền xem quản trị admin.")
    return {
        "status": "success",
        "data": {
            "roles": _list_admin_roles(db),
            "grants": _list_admin_grants(db),
        },
    }


@router.put("/admin-management")
def save_portal_admin_management(
    req: AdminManagementUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_portal_db),
):
    _assert_portal_admin(current_user, "admin_management", action="edit", message="Không có quyền sửa quản trị admin.")
    if not _is_portal_admin_level1(current_user, db):
        raise HTTPException(status_code=403, detail="Chỉ portal admin cấp 1 mới được cấp/thu hồi quản trị admin.")
    data = _replace_admin_management(
        db,
        roles_payload=req.roles,
        grants_payload=req.grants,
        updated_by=str(current_user.get("username", "system")),
    )
    return {"status": "success", "message": "Đã lưu cấu hình quản trị admin.", "data": data}
