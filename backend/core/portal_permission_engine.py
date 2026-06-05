from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from backend.core.database import PortalSessionLocal
from backend.core.models import PortalAdminGrant, PortalAdminRole
from backend.core.portal_permissions import list_page_permissions

SMARTVCOMS_ADMIN_GRANT_SECTION = "SmartVCOMS.quan_tri_he_thong"


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        if not value.strip():
            return []
        return [item.strip() for item in value.split(";") if item.strip()]
    return [value]


def _norm(value):
    return str(value or "").strip().upper()


def _user_roles(user):
    roles = {_norm(user.get("viTri"))}
    for key in ["roles", "roleCodes"]:
        roles.update(_norm(item) for item in _as_list(user.get(key)))
    return {item for item in roles if item}


def _user_rooms(user):
    rooms = {
        _norm(user.get("maPhong")),
        _norm(user.get("departmentCode")),
    }
    for key in ["rooms", "roomCodes"]:
        rooms.update(_norm(item) for item in _as_list(user.get(key)))
    return {item for item in rooms if item}


def _user_arr_dm(user):
    return {_norm(item) for item in _as_list(user.get("arrDM")) if _norm(item)}


def _user_groups(user):
    return {_norm(item) for item in _as_list(user.get("userGroups")) if _norm(item)}


def _user_ids(user):
    return {
        _norm(user.get("nameStr")),
        _norm(user.get("displayName")),
        _norm(user.get("username")),
        _norm(user.get("user")),
        _norm(user.get("maCB")),
        _norm(user.get("mail")),
    } - {""}


def _flag_matches(user, flags):
    for flag in _as_list(flags):
        if bool(user.get(str(flag), False)):
            return True
    return False


def _intersects(user_values, rule_values):
    rule_set = {_norm(item) for item in _as_list(rule_values) if _norm(item)}
    if not rule_set:
        return True
    return bool(user_values & rule_set)


def _clause_matches(user, clause):
    if not clause:
        return False

    checks = []
    if clause.get("flags"):
        checks.append(_flag_matches(user, clause.get("flags")))
    if clause.get("roles"):
        checks.append(_intersects(_user_roles(user), clause.get("roles")))
    if clause.get("rooms"):
        checks.append(_intersects(_user_rooms(user), clause.get("rooms")))
    if clause.get("arrDM"):
        checks.append(_intersects(_user_arr_dm(user), clause.get("arrDM")))
    if clause.get("groups"):
        checks.append(_intersects(_user_groups(user), clause.get("groups")))
    if clause.get("users"):
        checks.append(_intersects(_user_ids(user), clause.get("users")))

    if "allow" in clause:
        checks.append(bool(clause.get("allow")))

    return bool(checks) and all(checks)


def rule_allows(user, rule):
    if not rule:
        return False
    if rule.get("deny"):
        return False

    any_clauses = rule.get("any")
    if any_clauses:
        return any(_clause_matches(user, clause) for clause in _as_list(any_clauses))

    return _clause_matches(user, rule)


def load_permission_config() -> dict[str, Any]:
    db = PortalSessionLocal()
    try:
        rows = list_page_permissions(db)
        try:
            admin_roles = db.query(PortalAdminRole).filter(PortalAdminRole.is_active == 1).all()
            admin_grants = db.query(PortalAdminGrant).filter(PortalAdminGrant.is_active == 1).all()
        except OperationalError:
            admin_roles = []
            admin_grants = []
    finally:
        db.close()

    pages = {}
    for row in rows:
        pages[row["page_id"]] = {
            "label": row.get("label", row["page_id"]),
            "path": row.get("path", ""),
            "enabled": bool(row.get("enabled", 1)),
            "actions": row.get("actions", {}),
            "parts": row.get("parts", {}),
            "matrix": row.get("matrix", {}),
            "module_id": row.get("module_id", ""),
        }
    return {
        "version": 1,
        "pages": pages,
        "portal_admin_roles": [
            {
                "username": row.username,
                "admin_level": int(row.admin_level or 2),
                "is_active": int(row.is_active or 0),
            }
            for row in admin_roles
        ],
        "portal_admin_grants": [
            {
                "username": row.username,
                "section_key": row.section_key,
                "can_view": int(row.can_view or 0),
                "can_edit": int(row.can_edit or 0),
                "is_active": int(row.is_active or 0),
            }
            for row in admin_grants
        ],
    }


class PortalPermissionEngine:
    def __init__(self, config=None):
        self.config = config if config is not None else load_permission_config()

    def page_config(self, page_id):
        return self.config.get("pages", {}).get(page_id, {})

    def _portal_admin_role(self, user):
        user_ids = _user_ids(user)
        for row in self.config.get("portal_admin_roles", []):
            username = _norm(row.get("username"))
            if username and username in user_ids and int(row.get("is_active", 0) or 0) == 1:
                return row
        return None

    def _portal_admin_grants(self, user, section_key=None):
        user_ids = _user_ids(user)
        results = []
        for row in self.config.get("portal_admin_grants", []):
            username = _norm(row.get("username"))
            if not username or username not in user_ids:
                continue
            if int(row.get("is_active", 0) or 0) != 1:
                continue
            if section_key and str(row.get("section_key", "")).strip() != section_key:
                continue
            results.append(row)
        return results

    def _portal_admin_grant_allows(self, user, action="view", part_id=None):
        role = self._portal_admin_role(user)
        if role and int(role.get("admin_level", 2) or 2) <= 1:
            return True

        if part_id:
            grants = self._portal_admin_grants(user, section_key=part_id)
            if action == "view":
                return any(int(row.get("can_view", 0) or 0) == 1 for row in grants)
            if action == "edit":
                return any(int(row.get("can_edit", 0) or 0) == 1 for row in grants)
            return False

        grants = self._portal_admin_grants(user)
        if action == "view":
            return bool(grants) and any(int(row.get("can_view", 0) or 0) == 1 for row in grants)
        if action == "edit":
            return any(int(row.get("can_edit", 0) or 0) == 1 for row in grants)
        return False

    def _named_grant_allows(self, user, section_key, action="view"):
        grants = self._portal_admin_grants(user, section_key=section_key)
        if action == "view":
            return any(int(row.get("can_view", 0) or 0) == 1 for row in grants)
        if action == "edit":
            return any(int(row.get("can_edit", 0) or 0) == 1 for row in grants)
        return False

    def _smartvcoms_admin_allows(self, user, action="view"):
        if bool(user.get("isAdmin", False)):
            return True
        return self._named_grant_allows(user, SMARTVCOMS_ADMIN_GRANT_SECTION, action=action)

    def can(self, user, page_id, action="view", part_id=None):
        page_cfg = self.page_config(page_id)
        if not page_cfg or not page_cfg.get("enabled", True):
            return False

        if page_id == "SmartVCOMS" and part_id == "quan_tri_he_thong":
            return self._smartvcoms_admin_allows(user, action=action)

        if page_id == "PortalAdmin" and self._portal_admin_grant_allows(user, action=action, part_id=part_id):
            return True

        if part_id:
            part_cfg = page_cfg.get("parts", {}).get(part_id, {})
            part_rule = part_cfg.get(action)
            if part_rule is not None:
                return rule_allows(user, part_rule)

        rule = page_cfg.get("actions", {}).get(action)
        return rule_allows(user, rule)

    def visible_pages(self, user):
        pages = self.config.get("pages", {})
        return {
            page_id: page_cfg
            for page_id, page_cfg in pages.items()
            if self.can(user, page_id, "view")
        }

    def snapshot(self, user):
        pages = self.config.get("pages", {})
        result = {}
        for page_id, page_cfg in pages.items():
            actions = page_cfg.get("actions", {})
            parts = page_cfg.get("parts", {})
            result[page_id] = {
                "label": page_cfg.get("label", page_id),
                "module_id": page_cfg.get("module_id", ""),
                "path": page_cfg.get("path", ""),
                "enabled": bool(page_cfg.get("enabled", True)),
                "actions": {action: self.can(user, page_id, action) for action in actions.keys()},
                "parts": {
                    part_id: {action: self.can(user, page_id, action, part_id=part_id) for action in part_cfg.keys()}
                    for part_id, part_cfg in parts.items()
                },
            }
            if "view" not in result[page_id]["actions"]:
                result[page_id]["actions"]["view"] = self.can(user, page_id, "view")
        return {
            "pages": result,
            "visible_pages": [page_id for page_id in pages.keys() if self.can(user, page_id, "view")],
        }


def can(user, page_id, action="view", part_id=None, config=None):
    return PortalPermissionEngine(config).can(user, page_id, action, part_id)


def assert_permission(user, page_id, action="view", part_id=None, message="Không có quyền truy cập."):
    if not can(user, page_id, action, part_id):
        raise HTTPException(status_code=403, detail=message)


def get_permission_snapshot(user):
    return PortalPermissionEngine().snapshot(user)
