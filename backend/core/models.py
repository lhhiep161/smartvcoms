from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.core.database import PortalBase


class PortalAuthSetting(PortalBase):
    __tablename__ = "portal_auth_settings"

    setting_key = Column(String, primary_key=True, index=True)
    setting_value = Column(Text)
    description = Column(Text)
    updated_by = Column(String)
    updated_at = Column(String)


class PortalAdGroupMapping(PortalBase):
    __tablename__ = "portal_ad_group_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    mapping_type = Column(String, index=True)
    ad_group_name = Column(String, index=True)
    is_active = Column(Integer, default=1, index=True)
    priority = Column(Integer, default=100)
    position_code = Column(String)
    department_code = Column(String)
    department_name = Column(String)
    first_group = Column(String)
    arr_dm = Column(String)
    function_code = Column(String)
    flag_admin = Column(Integer, default=0)
    flag_bgd = Column(Integer, default=0)
    flag_truong_phong = Column(Integer, default=0)
    flag_lanh_dao_phong = Column(Integer, default=0)
    flag_dau_moi = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(String)
    updated_at = Column(String)
    updated_by = Column(String)


class PortalUserProfile(PortalBase):
    __tablename__ = "portal_user_profiles"

    username = Column(String, primary_key=True, index=True)
    auth_mode = Column(String)
    name_str = Column(String)
    display_name = Column(String)
    email = Column(String)
    ma_cb = Column(String)
    vi_tri = Column(String)
    ma_phong = Column(String)
    department_code = Column(String)
    department_name = Column(String)
    first_group = Column(String)
    arr_dm_json = Column(Text)
    user_groups_json = Column(Text)
    flags_json = Column(Text)
    ad_attributes_json = Column(Text)
    last_login_at = Column(String)
    last_sync_at = Column(String)
    is_active = Column(Integer, default=1)


class PortalUserOverride(PortalBase):
    __tablename__ = "portal_user_overrides"

    username = Column(String, primary_key=True, index=True)
    display_name = Column(String)
    vi_tri = Column(String)
    ma_cb = Column(String)
    ma_phong = Column(String)
    department_code = Column(String)
    department_name = Column(String)
    first_group = Column(String)
    arr_dm = Column(String)
    is_truong_phong = Column(Integer)
    is_lanh_dao_phong = Column(Integer)
    is_dau_moi = Column(Integer)
    is_active = Column(Integer, default=1)
    notes = Column(Text)
    updated_by = Column(String)
    updated_at = Column(String)


class PortalLoginAudit(PortalBase):
    __tablename__ = "portal_login_audit"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    username = Column(String, index=True)
    auth_mode = Column(String)
    success = Column(Integer, default=0)
    error_message = Column(Text)
    profile_json = Column(Text)
    created_at = Column(String)


class PortalPagePermission(PortalBase):
    __tablename__ = "portal_page_permissions"

    page_id = Column(String, primary_key=True, index=True)
    module_id = Column(String, index=True)
    label = Column(String)
    path = Column(String)
    enabled = Column(Integer, default=1, index=True)
    actions_json = Column(Text)
    parts_json = Column(Text)
    matrix_json = Column(Text)
    source_version = Column(Integer, default=1)
    source_tag = Column(String)
    updated_by = Column(String)
    updated_at = Column(String)


class PortalAdminRole(PortalBase):
    __tablename__ = "portal_admin_roles"

    username = Column(String, primary_key=True, index=True)
    admin_level = Column(Integer, default=2, index=True)
    is_active = Column(Integer, default=1, index=True)
    notes = Column(Text)
    granted_by = Column(String)
    updated_at = Column(String)


class PortalAdminGrant(PortalBase):
    __tablename__ = "portal_admin_grants"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    username = Column(String, index=True)
    section_key = Column(String, index=True)
    can_view = Column(Integer, default=1)
    can_edit = Column(Integer, default=0)
    is_active = Column(Integer, default=1, index=True)
    notes = Column(Text)
    granted_by = Column(String)
    updated_at = Column(String)
