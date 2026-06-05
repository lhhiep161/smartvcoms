import copy
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core.models import PortalPagePermission

SEED_PERMISSION_PATH = Path("package_config/seed/page_permissions.json")
LEGACY_PERMISSION_PATH = Path("data/core/page_permissions.json")
TARGET_PAGES = {
    "SmartVCOMS": "smart-vcoms",
    "PortalAdmin": "portal-admin",
}
BUSINESS_ROOMS = ["05", "09", "30", "31", "35", "36", "37"]
OPS_ROOMS = ["03", "13", "18"]


def _now_str() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty_config():
    return {"version": 1, "pages": {}}


def _normalize_permissions(config):
    config = copy.deepcopy(config or _empty_config())
    config.setdefault("version", 1)
    pages = config.setdefault("pages", {})
    for page_id, page_cfg in list(pages.items()):
        if not isinstance(page_cfg, dict):
            pages[page_id] = {
                "label": str(page_id),
                "path": "",
                "enabled": False,
                "actions": {},
                "parts": {},
            }
            continue
        page_cfg.setdefault("label", page_id)
        page_cfg.setdefault("path", "")
        page_cfg["enabled"] = bool(page_cfg.get("enabled", True))
        page_cfg.setdefault("actions", {})
        page_cfg.setdefault("parts", {})
    return config


def _serialize_json(value) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _deserialize_json(value, default):
    try:
        if not value:
            return default
        return json.loads(value)
    except Exception:
        return default


def _page_view_rule_with_managers():
    return {
        "any": [
            {"flags": ["isAdmin"]},
            {"flags": ["isBGD"]},
            {"flags": ["isTruongPhong"]},
            {"flags": ["isLanhDaoPhong"]},
            {"roles": ["D", "C"]},
        ]
    }


def _smartvcoms_admin_rule():
    return {
        "any": [
            {"flags": ["isAdmin"]},
        ]
    }


def _portal_admin_rule():
    return {"allow": False}


def _portal_admin_page_cfg():
    admin_rule = _portal_admin_rule()
    return {
        "label": "Portal Admin",
        "path": "/portal-admin",
        "enabled": True,
        "actions": {
            "view": admin_rule,
        },
        "parts": {
            "overview": {"view": admin_rule},
            "identity_auth": {"view": admin_rule, "edit": admin_rule},
            "ad_mappings": {"view": admin_rule, "edit": admin_rule},
            "user_overrides": {"view": admin_rule, "edit": admin_rule},
            "portal_permissions": {"view": admin_rule, "edit": admin_rule},
            "admin_management": {"view": admin_rule, "edit": admin_rule},
            "auth_policy": {"view": admin_rule, "edit": admin_rule},
        },
        "matrix": {},
    }


def _upgrade_page_cfg(page_id: str, page_cfg: dict) -> dict:
    cfg = copy.deepcopy(page_cfg or {})
    if page_id == "SmartVCOMS":
        cfg.setdefault("actions", {})
        cfg.setdefault("parts", {})
        cfg["actions"]["view"] = _page_view_rule_with_managers()
        cfg.setdefault("parts", {}).setdefault("ban_dieu_phoi", {})["view"] = _page_view_rule_with_managers()
        cfg.setdefault("parts", {}).setdefault("thong_ke", {})["view"] = _page_view_rule_with_managers()
        cfg.setdefault("parts", {}).setdefault("quan_tri_he_thong", {})["view"] = _smartvcoms_admin_rule()
    elif page_id == "PortalAdmin":
        cfg = _portal_admin_page_cfg()
    return cfg


def load_legacy_permission_pages(page_ids: list[str] | None = None) -> dict:
    path = SEED_PERMISSION_PATH if SEED_PERMISSION_PATH.exists() else LEGACY_PERMISSION_PATH
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    normalized = _normalize_permissions(data)
    pages = normalized.get("pages", {})
    page_ids = page_ids or list(TARGET_PAGES.keys())
    result = {}
    for page_id in page_ids:
        legacy_cfg = copy.deepcopy(pages.get(page_id, {}))
        if page_id == "PortalAdmin" and not legacy_cfg:
            legacy_cfg = _portal_admin_page_cfg()
        elif page_id not in pages and not legacy_cfg:
            continue
        result[page_id] = _upgrade_page_cfg(page_id, legacy_cfg)
    return result


def ensure_default_page_permissions(db: Session) -> None:
    existing = db.query(PortalPagePermission).count()
    if existing > 0:
        _upgrade_existing_legacy_page_permissions(db)
        _ensure_missing_target_pages(db)
        return
    import_legacy_page_permissions(db, updated_by="system_seed")


def _ensure_missing_target_pages(db: Session) -> None:
    existing_ids = {
        row[0]
        for row in db.query(PortalPagePermission.page_id).filter(PortalPagePermission.page_id.in_(list(TARGET_PAGES.keys()))).all()
    }
    missing_ids = [page_id for page_id in TARGET_PAGES.keys() if page_id not in existing_ids]
    if not missing_ids:
        return
    pages = load_legacy_permission_pages(missing_ids)
    now = _now_str()
    for page_id in missing_ids:
        page_cfg = pages.get(page_id)
        if not page_cfg:
            continue
        db.add(
            PortalPagePermission(
                page_id=page_id,
                module_id=TARGET_PAGES.get(page_id, ""),
                label=page_cfg.get("label", page_id),
                path=page_cfg.get("path", ""),
                enabled=int(bool(page_cfg.get("enabled", True))),
                actions_json=_serialize_json(page_cfg.get("actions", {})),
                parts_json=_serialize_json(page_cfg.get("parts", {})),
                matrix_json=_serialize_json(page_cfg.get("matrix", {})),
                source_version=1,
                source_tag="system_generated",
                updated_by="system_seed",
                updated_at=now,
            )
        )
    db.commit()


def _upgrade_existing_legacy_page_permissions(db: Session) -> None:
    rows = db.query(PortalPagePermission).filter(PortalPagePermission.page_id.in_(list(TARGET_PAGES.keys()))).all()
    changed = False
    now = _now_str()
    for row in rows:
        if not str(row.source_tag or "").startswith("legacy:"):
            continue
        if str(row.updated_by or "") not in {"system_seed", "system_import"}:
            continue
        upgraded = _upgrade_page_cfg(
            row.page_id,
            {
                "actions": _deserialize_json(row.actions_json, {}),
                "parts": _deserialize_json(row.parts_json, {}),
                "matrix": _deserialize_json(row.matrix_json, {}),
                "label": row.label or row.page_id,
                "path": row.path or "",
                "enabled": bool(row.enabled),
            },
        )
        next_actions = _serialize_json(upgraded.get("actions", {}))
        next_parts = _serialize_json(upgraded.get("parts", {}))
        next_matrix = _serialize_json(upgraded.get("matrix", {}))
        if row.actions_json != next_actions or row.parts_json != next_parts or row.matrix_json != next_matrix:
            row.actions_json = next_actions
            row.parts_json = next_parts
            row.matrix_json = next_matrix
            row.updated_by = "system_upgrade"
            row.updated_at = now
            changed = True
    if changed:
        db.commit()


def list_page_permissions(db: Session, module_id: str | None = None) -> list[dict]:
    ensure_default_page_permissions(db)
    query = db.query(PortalPagePermission)
    if module_id:
        query = query.filter(PortalPagePermission.module_id == module_id)
    rows = query.order_by(PortalPagePermission.page_id.asc()).all()
    return [
        {
            "page_id": row.page_id,
            "module_id": row.module_id or "",
            "label": row.label or "",
            "path": row.path or "",
            "enabled": int(row.enabled or 0),
            "actions": _deserialize_json(row.actions_json, {}),
            "parts": _deserialize_json(row.parts_json, {}),
            "matrix": _deserialize_json(row.matrix_json, {}),
            "source_version": int(row.source_version or 1),
            "source_tag": row.source_tag or "",
            "updated_by": row.updated_by or "",
            "updated_at": row.updated_at or "",
        }
        for row in rows
    ]


def replace_page_permissions(db: Session, rows: list[dict], updated_by: str) -> list[dict]:
    db.query(PortalPagePermission).delete()
    now = _now_str()
    for row in rows:
        page_id = str(row.get("page_id", "")).strip()
        if not page_id:
            continue
        db.add(
            PortalPagePermission(
                page_id=page_id,
                module_id=str(row.get("module_id", TARGET_PAGES.get(page_id, ""))).strip(),
                label=str(row.get("label", page_id)).strip(),
                path=str(row.get("path", "")).strip(),
                enabled=int(bool(row.get("enabled", True))),
                actions_json=_serialize_json(row.get("actions", {})),
                parts_json=_serialize_json(row.get("parts", {})),
                matrix_json=_serialize_json(row.get("matrix", {})),
                source_version=int(row.get("source_version", 1) or 1),
                source_tag=str(row.get("source_tag", "portal_db")).strip(),
                updated_by=updated_by,
                updated_at=now,
            )
        )
    db.commit()
    return list_page_permissions(db)


def import_legacy_page_permissions(db: Session, updated_by: str = "system_import") -> list[dict]:
    pages = load_legacy_permission_pages()
    normalized_rows = []
    for page_id, page_cfg in pages.items():
        normalized_rows.append(
            {
                "page_id": page_id,
                "module_id": TARGET_PAGES.get(page_id, ""),
                "label": page_cfg.get("label", page_id),
                "path": page_cfg.get("path", ""),
                "enabled": bool(page_cfg.get("enabled", True)),
                "actions": page_cfg.get("actions", {}),
                "parts": page_cfg.get("parts", {}),
                "matrix": page_cfg.get("matrix", {}),
                "source_version": 1,
                "source_tag": f"legacy:{LEGACY_PERMISSION_PATH}",
            }
        )
    return replace_page_permissions(db, normalized_rows, updated_by=updated_by)
