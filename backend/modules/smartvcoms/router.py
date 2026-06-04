from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.portal_permission_engine import assert_permission
from backend.modules.auth.router import get_current_user
from backend.modules.smartvcoms.services.actions_service import (
    apply_manual_action,
    delete_manual_override,
    remove_manual_action,
    save_rule_engine_config,
    set_manual_override,
)
from backend.modules.smartvcoms.services.admin_service import (
    load_admin_config,
    update_cb_config,
    update_ld_config,
    update_room_config,
    update_sla_config,
)
from backend.modules.smartvcoms.services.kanban_service import fetch_vcoms_cases
from backend.modules.smartvcoms.services.stats_service import load_statistics

router = APIRouter(prefix="/api/vcoms", tags=["SmartVCOMS"])


class RuleUpdatePayload(BaseModel):
    routing: List[dict]
    assignment: List[dict]


class VcomsOverride(BaseModel):
    case_key: str
    field_name: str
    manual_value: str


class ManualActionReq(BaseModel):
    case_key: str
    action_type: str
    note: str = ""


class ConfigUpdateRequest(BaseModel):
    rows: List[dict]


@router.get("/cases")
def get_vcoms_cases(current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="ban_dieu_phoi", message="Không có quyền xem Bàn điều phối SmartVCOMS.")
    return fetch_vcoms_cases(current_user)


@router.put("/admin/rules")
def update_vcoms_rules(req: RuleUpdatePayload, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền quản trị SmartVCOMS.")
    return save_rule_engine_config(req.routing, req.assignment)


@router.post("/manual-action")
def apply_manual_action_route(req: ManualActionReq, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền thao tác thủ công.")
    return apply_manual_action(req.case_key, req.action_type, req.note, current_user)


@router.delete("/manual-action/{case_key}")
def remove_manual_action_route(case_key: str, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền thao tác thủ công.")
    return remove_manual_action(case_key)


@router.post("/manual-override")
def set_vcoms_override(req: VcomsOverride, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền ghi đè thủ công.")
    return set_manual_override(req.case_key, req.field_name, req.manual_value, current_user)


@router.delete("/manual-override/{case_key}/{field_name}")
def delete_vcoms_override(case_key: str, field_name: str, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền xóa ghi đè thủ công.")
    return delete_manual_override(case_key, field_name)


@router.get("/admin/config")
def get_vcoms_admin_config(current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền xem cấu hình quản trị SmartVCOMS.")
    return load_admin_config()


@router.put("/admin/config/cb")
def update_vcoms_cb_config(req: ConfigUpdateRequest, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền cập nhật cấu hình SmartVCOMS.")
    return update_cb_config(req.rows, current_user)


@router.put("/admin/config/room")
def update_vcoms_room_config(req: ConfigUpdateRequest, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền cập nhật cấu hình SmartVCOMS.")
    return update_room_config(req.rows)


@router.put("/admin/config/ld")
def update_vcoms_ld_config(req: ConfigUpdateRequest, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền cập nhật cấu hình SmartVCOMS.")
    return update_ld_config(req.rows, current_user)


@router.put("/admin/config/sla")
def update_vcoms_sla_config(req: ConfigUpdateRequest, current_user: dict = Depends(get_current_user)):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="quan_tri_he_thong", message="Không có quyền cập nhật cấu hình SmartVCOMS.")
    return update_sla_config(req.rows, current_user)


@router.get("/statistics")
def get_vcoms_statistics(
    mode: str = "today",
    year: int = None,
    month: int = None,
    day: int = None,
    room: str = None,
    current_user: dict = Depends(get_current_user),
):
    assert_permission(current_user, "SmartVCOMS", "view", part_id="thong_ke", message="Không có quyền xem thống kê SmartVCOMS.")
    return load_statistics(mode=mode, year=year, month=month, day=day, room=room, current_user=current_user)
