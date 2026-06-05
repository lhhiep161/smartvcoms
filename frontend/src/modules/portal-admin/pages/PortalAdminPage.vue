<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { apiFetchJSON } from '../../../shared/api/client'
import { useAuthStore } from '../../../app/stores/auth'

const loading = ref(true)
const error = ref('')
const notice = ref('')
const noticeType = ref('success')
const activeSection = ref('overview')
const { permissionSnapshot } = useAuthStore()

const overview = ref({
  title: 'Quản trị hệ thống',
  sections: [],
  current_user: null,
  auth_settings: {},
  ad_mapping_count: 0,
  user_override_count: 0,
  page_permission_count: 0,
})

const authSettings = ref({
  auth_mode: 'DEV',
  dev_login_enabled: '1',
  ad_strict_mapping: '1',
  ma_cb_ad_attribute: 'employeeID',
})
const authDescriptions = ref({})
const savingAuthSettings = ref(false)

const adMappings = ref([])
const savingMappings = ref(false)

const userProfiles = ref([])
const userOverrides = ref([])
const loginAudit = ref([])
const savingOverrides = ref(false)
const pagePermissions = ref([])
const adminRoles = ref([])
const adminGrants = ref([])
const savingAdminManagement = ref(false)

const mappingTypeOptions = ['login_access', 'position', 'department', 'function']
const positionOptions = ['', 'A', 'G', 'P', 'T', 'D', 'C']
const adminLevelOptions = [1, 2]
const portalAdminGrantSections = [
  'overview',
  'identity_auth',
  'ad_mappings',
  'user_overrides',
  'portal_permissions',
  'admin_management',
  'auth_policy',
  'SmartVCOMS.quan_tri_he_thong',
]

const sectionPermissionMap = {
  overview: 'overview',
  identity: 'identity_auth',
  'ad-mappings': 'ad_mappings',
  'user-overrides': 'user_overrides',
  'portal-permissions': 'portal_permissions',
  'admin-management': 'admin_management',
  'auth-policy': 'auth_policy',
}

const canAccessPortalAdminSection = (sectionKey, action = 'view') => {
  const partId = sectionPermissionMap[sectionKey]
  return Boolean(permissionSnapshot.value?.pages?.PortalAdmin?.parts?.[partId]?.[action])
}

const portalSections = computed(() =>
  [
    {
      key: 'overview',
      title: 'Tổng quan',
      subtitle: 'Nhìn nhanh trạng thái quản trị hệ thống',
      badge: `${overview.value.sections?.length || 0}`,
    },
    {
      key: 'identity',
      title: 'Danh tính & Đăng nhập',
      subtitle: 'Auth settings, user profiles, login audit',
      badge: `${userProfiles.value.length}`,
    },
    {
      key: 'ad-mappings',
      title: 'AD Mappings',
      subtitle: 'Mapping nhóm AD vào vai trò và phòng ban',
      badge: `${adMappings.value.length}`,
    },
    {
      key: 'user-overrides',
      title: 'User Overrides',
      subtitle: 'Ghi đè hồ sơ người dùng theo từng user',
      badge: `${userOverrides.value.length}`,
    },
    {
      key: 'portal-permissions',
      title: 'Quyền Portal',
      subtitle: 'Quyền truy cập cấp portal cho các page',
      badge: `${pagePermissions.value.length}`,
    },
    {
      key: 'admin-management',
      title: 'Quản trị Admin',
      subtitle: 'Khu dành cho admin cấp 1 / cấp 2',
      badge: 'Planned',
    },
    {
      key: 'auth-policy',
      title: 'Auth Policy',
      subtitle: 'Emergency access và policy xác thực hệ thống',
      badge: 'Planned',
    },
  ].filter((section) => canAccessPortalAdminSection(section.key))
)

const canEditIdentityAuth = computed(() => canAccessPortalAdminSection('identity', 'edit'))
const canEditAdMappings = computed(() => canAccessPortalAdminSection('ad-mappings', 'edit'))
const canEditUserOverrides = computed(() => canAccessPortalAdminSection('user-overrides', 'edit'))

watch(
  portalSections,
  (sections) => {
    if (!sections.length) {
      return
    }
    if (!sections.some((section) => section.key === activeSection.value)) {
      activeSection.value = sections[0].key
    }
  },
  { immediate: true }
)

const showNotice = (message, type = 'success') => {
  notice.value = message
  noticeType.value = type
}

const clearNotice = () => {
  notice.value = ''
}

const normalizeAuthSettings = (data) => {
  authDescriptions.value = {}
  const nextSettings = {}
  Object.entries(data || {}).forEach(([key, value]) => {
    authDescriptions.value[key] = value?.description || ''
    nextSettings[key] = value?.value ?? ''
  })
  authSettings.value = {
    auth_mode: nextSettings.auth_mode || 'DEV',
    dev_login_enabled: nextSettings.dev_login_enabled || '0',
    ad_strict_mapping: nextSettings.ad_strict_mapping || '1',
    ma_cb_ad_attribute: nextSettings.ma_cb_ad_attribute || 'employeeID',
  }
}

const normalizeMappingRow = (row = {}) => ({
  id: row.id || null,
  mapping_type: row.mapping_type || 'department',
  ad_group_name: row.ad_group_name || '',
  is_active: Number(row.is_active ?? 1),
  priority: Number(row.priority ?? 100),
  position_code: row.position_code || '',
  department_code: row.department_code || '',
  department_name: row.department_name || '',
  first_group: row.first_group || '',
  arr_dm: row.arr_dm || '',
  function_code: row.function_code || '',
  flag_admin: Number(row.flag_admin ?? 0),
  flag_bgd: Number(row.flag_bgd ?? 0),
  flag_truong_phong: Number(row.flag_truong_phong ?? 0),
  flag_lanh_dao_phong: Number(row.flag_lanh_dao_phong ?? 0),
  flag_dau_moi: Number(row.flag_dau_moi ?? 0),
  notes: row.notes || '',
})

const normalizeOverrideRow = (row = {}) => ({
  username: row.username || '',
  display_name: row.display_name || '',
  vi_tri: row.vi_tri || '',
  ma_cb: row.ma_cb || '',
  ma_phong: row.ma_phong || '',
  department_code: row.department_code || '',
  department_name: row.department_name || '',
  first_group: row.first_group || '',
  arr_dm: row.arr_dm || '',
  is_truong_phong: row.is_truong_phong === null || row.is_truong_phong === undefined ? '' : Number(row.is_truong_phong),
  is_lanh_dao_phong: row.is_lanh_dao_phong === null || row.is_lanh_dao_phong === undefined ? '' : Number(row.is_lanh_dao_phong),
  is_dau_moi: row.is_dau_moi === null || row.is_dau_moi === undefined ? '' : Number(row.is_dau_moi),
  is_active: Number(row.is_active ?? 1),
  notes: row.notes || '',
  updated_by: row.updated_by || '',
  updated_at: row.updated_at || '',
})

const normalizeAdminRoleRow = (row = {}) => ({
  username: row.username || '',
  admin_level: Number(row.admin_level ?? 2),
  is_active: Number(row.is_active ?? 1),
  notes: row.notes || '',
  granted_by: row.granted_by || '',
  updated_at: row.updated_at || '',
})

const normalizeAdminGrantRow = (row = {}) => ({
  id: row.id || null,
  username: row.username || '',
  section_key: row.section_key || 'overview',
  can_view: Number(row.can_view ?? 1),
  can_edit: Number(row.can_edit ?? 0),
  is_active: Number(row.is_active ?? 1),
  notes: row.notes || '',
  granted_by: row.granted_by || '',
  updated_at: row.updated_at || '',
})

const loadOverview = async () => {
  const response = await apiFetchJSON('/api/portal-admin/overview')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được dữ liệu tổng quan quản trị hệ thống')
  }
  overview.value = response.data || overview.value
}

const loadAuthSettings = async () => {
  const response = await apiFetchJSON('/api/portal-admin/auth-settings')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được cấu hình đăng nhập')
  }
  normalizeAuthSettings(response.data || {})
}

const loadAdMappings = async () => {
  const response = await apiFetchJSON('/api/portal-admin/ad-group-mappings')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được cấu hình nhóm AD')
  }
  adMappings.value = (response.data || []).map(normalizeMappingRow)
}

const loadUserProfiles = async () => {
  const response = await apiFetchJSON('/api/portal-admin/user-profiles?limit=200')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được user profiles')
  }
  userProfiles.value = response.data || []
}

const loadUserOverrides = async () => {
  const response = await apiFetchJSON('/api/portal-admin/user-overrides')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được user overrides')
  }
  userOverrides.value = (response.data || []).map(normalizeOverrideRow)
}

const loadLoginAudit = async () => {
  const response = await apiFetchJSON('/api/portal-admin/login-audit?limit=200')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được login audit')
  }
  loginAudit.value = response.data || []
}

const loadPagePermissions = async () => {
  const response = await apiFetchJSON('/api/portal-admin/page-permissions')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được permission store')
  }
  pagePermissions.value = response.data || []
}

const loadAdminManagement = async () => {
  const response = await apiFetchJSON('/api/portal-admin/admin-management')
  if (response.status !== 'success') {
    throw new Error(response.message || 'Không tải được cấu hình quản trị admin')
  }
  adminRoles.value = (response.data?.roles || []).map(normalizeAdminRoleRow)
  adminGrants.value = (response.data?.grants || []).map(normalizeAdminGrantRow)
}

const loadPageData = async () => {
  loading.value = true
  error.value = ''
  clearNotice()
  try {
    const tasks = [loadOverview()]
    if (canAccessPortalAdminSection('identity')) {
      tasks.push(loadAuthSettings(), loadUserProfiles(), loadLoginAudit())
    }
    if (canAccessPortalAdminSection('ad-mappings')) {
      tasks.push(loadAdMappings())
    }
    if (canAccessPortalAdminSection('user-overrides')) {
      tasks.push(loadUserOverrides())
    }
    if (canAccessPortalAdminSection('portal-permissions')) {
      tasks.push(loadPagePermissions())
    }
    if (canAccessPortalAdminSection('admin-management')) {
      tasks.push(loadAdminManagement())
    }
    await Promise.all(tasks)
  } catch (err) {
    error.value = err.message || 'Không tải được dữ liệu quản trị hệ thống'
  } finally {
    loading.value = false
  }
}

const saveAuthSettings = async () => {
  if (!canEditIdentityAuth.value) {
    showNotice('Bạn không có quyền sửa khu Danh tính & Đăng nhập.', 'error')
    return
  }
  savingAuthSettings.value = true
  clearNotice()
  try {
    const response = await apiFetchJSON('/api/portal-admin/auth-settings', {
      method: 'PUT',
      body: JSON.stringify({ settings: authSettings.value }),
    })
    if (response.status !== 'success') {
      throw new Error(response.message || 'Không lưu được cấu hình đăng nhập')
    }
    normalizeAuthSettings(response.data || {})
    await loadOverview()
    showNotice(response.message || 'Đã lưu cấu hình đăng nhập.')
  } catch (err) {
    showNotice(err.message || 'Không lưu được cấu hình đăng nhập', 'error')
  } finally {
    savingAuthSettings.value = false
  }
}

const addMappingRow = () => {
  adMappings.value.push(normalizeMappingRow())
}

const removeMappingRow = (index) => {
  adMappings.value.splice(index, 1)
}

const saveAdMappings = async () => {
  if (!canEditAdMappings.value) {
    showNotice('Bạn không có quyền sửa khu AD Mappings.', 'error')
    return
  }
  savingMappings.value = true
  clearNotice()
  try {
    const payload = adMappings.value
      .map((row) => normalizeMappingRow(row))
      .filter((row) => row.mapping_type && row.ad_group_name.trim())

    const response = await apiFetchJSON('/api/portal-admin/ad-group-mappings', {
      method: 'PUT',
      body: JSON.stringify({ rows: payload }),
    })
    if (response.status !== 'success') {
      throw new Error(response.message || 'Không lưu được cấu hình nhóm AD')
    }
    adMappings.value = (response.data || []).map(normalizeMappingRow)
    await loadOverview()
    showNotice(response.message || 'Đã lưu cấu hình nhóm AD.')
  } catch (err) {
    showNotice(err.message || 'Không lưu được cấu hình nhóm AD', 'error')
  } finally {
    savingMappings.value = false
  }
}

const addOverrideRow = () => {
  userOverrides.value.push(normalizeOverrideRow())
}

const removeOverrideRow = (index) => {
  userOverrides.value.splice(index, 1)
}

const saveUserOverrides = async () => {
  if (!canEditUserOverrides.value) {
    showNotice('Bạn không có quyền sửa khu User Overrides.', 'error')
    return
  }
  savingOverrides.value = true
  clearNotice()
  try {
    const payload = userOverrides.value
      .map((row) => normalizeOverrideRow(row))
      .filter((row) => row.username.trim())

    const response = await apiFetchJSON('/api/portal-admin/user-overrides', {
      method: 'PUT',
      body: JSON.stringify({ rows: payload }),
    })
    if (response.status !== 'success') {
      throw new Error(response.message || 'Không lưu được user overrides')
    }
    userOverrides.value = (response.data || []).map(normalizeOverrideRow)
    await loadOverview()
    showNotice(response.message || 'Đã lưu user override.')
  } catch (err) {
    showNotice(err.message || 'Không lưu được user overrides', 'error')
  } finally {
    savingOverrides.value = false
  }
}

const canEditAdminManagement = computed(() => canAccessPortalAdminSection('admin-management', 'edit'))

const addAdminRoleRow = () => {
  adminRoles.value.push(normalizeAdminRoleRow())
}

const removeAdminRoleRow = (index) => {
  adminRoles.value.splice(index, 1)
}

const addAdminGrantRow = () => {
  adminGrants.value.push(normalizeAdminGrantRow())
}

const removeAdminGrantRow = (index) => {
  adminGrants.value.splice(index, 1)
}

const saveAdminManagement = async () => {
  if (!canEditAdminManagement.value) {
    showNotice('Bạn không có quyền sửa khu Quản trị Admin.', 'error')
    return
  }
  savingAdminManagement.value = true
  clearNotice()
  try {
    const payload = {
      roles: adminRoles.value
        .map((row) => normalizeAdminRoleRow(row))
        .filter((row) => row.username.trim()),
      grants: adminGrants.value
        .map((row) => normalizeAdminGrantRow(row))
        .filter((row) => row.username.trim() && row.section_key.trim()),
    }
    const response = await apiFetchJSON('/api/portal-admin/admin-management', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    if (response.status !== 'success') {
      throw new Error(response.message || 'Không lưu được cấu hình quản trị admin')
    }
    adminRoles.value = (response.data?.roles || []).map(normalizeAdminRoleRow)
    adminGrants.value = (response.data?.grants || []).map(normalizeAdminGrantRow)
    await loadOverview()
    showNotice(response.message || 'Đã lưu cấu hình quản trị admin.')
  } catch (err) {
    showNotice(err.message || 'Không lưu được cấu hình quản trị admin', 'error')
  } finally {
    savingAdminManagement.value = false
  }
}

onMounted(loadPageData)
</script>

<template>
  <div style="padding: 24px 28px 32px;">
    <div style="margin-bottom: 24px;">
      <div class="portal-title">QUẢN TRỊ HỆ THỐNG</div>
      <div class="portal-subtitle">KHUNG ĐIỀU HÀNH CHO USER, PHÂN QUYỀN, XÁC THỰC VÀ CÁC PHÂN HỆ PORTAL</div>
    </div>

    <div style="margin-bottom: 24px; padding: 18px 20px; border-radius: 18px; background: linear-gradient(135deg, #0f172a, #005993); color: white; box-shadow: 0 18px 38px rgba(0, 0, 0, 0.12);">
      <div style="font-size: 13px; opacity: 0.82; text-transform: uppercase; letter-spacing: 0.08em;">Phiên hiện tại</div>
      <div style="margin-top: 8px; font-size: 24px; font-weight: 800;">
        {{ overview.current_user?.name || 'Người dùng hệ thống' }}
      </div>
      <div style="margin-top: 6px; font-size: 14px; opacity: 0.92;">
        {{ overview.current_user?.username || '' }}
        <span v-if="overview.current_user?.is_admin">· Quản trị viên</span>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 24px;">
      <button
        v-for="section in portalSections"
        :key="section.key"
        type="button"
        @click="activeSection = section.key"
        :style="{
          padding: '18px 18px',
          borderRadius: '16px',
          border: activeSection === section.key ? '2px solid #005993' : '1px solid #dce4ed',
          background: activeSection === section.key ? '#f8fbff' : 'white',
          boxShadow: activeSection === section.key ? '0 10px 24px rgba(0, 89, 147, 0.10)' : '0 8px 18px rgba(15, 23, 42, 0.05)',
          textAlign: 'left',
          cursor: 'pointer'
        }"
      >
        <div style="display: flex; justify-content: space-between; gap: 12px; align-items: start;">
          <div>
            <div style="font-size: 12px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Portal Admin</div>
            <div style="margin-top: 8px; font-size: 18px; font-weight: 900; color: #0f172a;">{{ section.title }}</div>
            <div style="margin-top: 8px; font-size: 13px; line-height: 1.5; color: #475569;">{{ section.subtitle }}</div>
          </div>
          <div style="padding: 6px 10px; border-radius: 999px; background: #eef5ff; color: #005993; font-size: 12px; font-weight: 800; white-space: nowrap;">
            {{ section.badge }}
          </div>
        </div>
      </button>
    </div>

    <div v-if="notice" :style="{ marginBottom: '20px', padding: '14px 16px', borderRadius: '14px', fontWeight: 700, background: noticeType === 'error' ? '#fff1f2' : '#ecfdf3', color: noticeType === 'error' ? '#be123c' : '#047857' }">
      {{ notice }}
    </div>

    <div v-if="loading" style="padding: 36px 0; color: #475569; font-weight: 600;">
      Đang tải khung quản trị hệ thống...
    </div>

    <div v-else-if="error" style="padding: 18px 20px; border-radius: 14px; background: #fff1f2; color: #be123c; font-weight: 600;">
      {{ error }}
    </div>

    <template v-else>
      <div v-if="activeSection === 'overview'">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px;">
          <div style="padding: 18px 20px; border-radius: 16px; background: #f8fbff; border: 1px solid #dce4ed;">
            <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Auth mode</div>
            <div style="margin-top: 10px; font-size: 28px; font-weight: 900; color: #0f172a;">{{ authSettings.auth_mode || '---' }}</div>
          </div>
          <div style="padding: 18px 20px; border-radius: 16px; background: #f8fbff; border: 1px solid #dce4ed;">
            <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">AD group mappings</div>
            <div style="margin-top: 10px; font-size: 28px; font-weight: 900; color: #0f172a;">{{ adMappings.length || 0 }}</div>
          </div>
          <div style="padding: 18px 20px; border-radius: 16px; background: #f8fbff; border: 1px solid #dce4ed;">
            <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">User overrides</div>
            <div style="margin-top: 10px; font-size: 28px; font-weight: 900; color: #0f172a;">{{ overview.user_override_count || 0 }}</div>
          </div>
          <div style="padding: 18px 20px; border-radius: 16px; background: #f8fbff; border: 1px solid #dce4ed;">
            <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Portal pages</div>
            <div style="margin-top: 10px; font-size: 28px; font-weight: 900; color: #0f172a;">{{ pagePermissions.length || 0 }}</div>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px;">
          <div
            v-for="section in overview.sections"
            :key="section.key"
            style="min-height: 190px; padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08); display: flex; flex-direction: column; justify-content: space-between;"
          >
            <div>
              <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">{{ section.status === 'planned' ? 'Planned' : section.status }}</div>
              <div v-if="section.count !== undefined" style="margin-top: 8px; font-size: 34px; font-weight: 900; color: #005993;">{{ section.count }}</div>
              <div style="margin-top: 10px; font-size: 22px; font-weight: 800; color: #0f172a;">{{ section.title }}</div>
              <div style="margin-top: 10px; font-size: 14px; line-height: 1.6; color: #475569;">{{ section.description }}</div>
            </div>
            <div style="margin-top: 16px; font-size: 13px; font-weight: 700; color: #005993;">Sẵn sàng để triển khai sâu hơn</div>
          </div>
        </div>
      </div>

      <div v-else-if="activeSection === 'identity'" style="display: grid; grid-template-columns: 1fr; gap: 20px;">
        <div style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div>
              <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Cấu hình đăng nhập</div>
              <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">Cấu hình xác thực và hồ sơ truy cập</div>
            </div>
            <button type="button" :disabled="savingAuthSettings || !canEditIdentityAuth" @click="saveAuthSettings" style="height: 42px; padding: 0 18px; border-radius: 12px; border: none; background: #005993; color: white; font-weight: 800; cursor: pointer;">
              {{ savingAuthSettings ? 'Đang lưu...' : 'Lưu cấu hình' }}
            </button>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;">
            <label style="display: grid; gap: 8px;">
              <span style="font-size: 13px; font-weight: 800; color: #334155;">Auth mode</span>
              <input :value="authSettings.auth_mode" type="text" readonly style="height: 42px; border-radius: 12px; border: 1px solid #dce4ed; padding: 0 12px; color: #0f172a; font-weight: 700; background: #f8fafc;" />
              <span style="font-size: 12px; color: #64748b;">{{ authDescriptions.auth_mode || '' }}</span>
            </label>
            <label style="display: grid; gap: 8px;">
              <span style="font-size: 13px; font-weight: 800; color: #334155;">DEV login enabled</span>
              <input :value="authSettings.dev_login_enabled === '1' ? 'Bật' : 'Tắt'" type="text" readonly style="height: 42px; border-radius: 12px; border: 1px solid #dce4ed; padding: 0 12px; color: #0f172a; font-weight: 700; background: #f8fafc;" />
              <span style="font-size: 12px; color: #64748b;">{{ authDescriptions.dev_login_enabled || '' }}</span>
            </label>
            <label style="display: grid; gap: 8px;">
              <span style="font-size: 13px; font-weight: 800; color: #334155;">AD strict mapping</span>
              <select v-model="authSettings.ad_strict_mapping" style="height: 42px; border-radius: 12px; border: 1px solid #dce4ed; padding: 0 12px; color: #0f172a; font-weight: 700;">
                <option value="1">Bật</option>
                <option value="0">Tắt</option>
              </select>
              <span style="font-size: 12px; color: #64748b;">{{ authDescriptions.ad_strict_mapping || '' }}</span>
            </label>
            <label style="display: grid; gap: 8px;">
              <span style="font-size: 13px; font-weight: 800; color: #334155;">Mã CB AD attribute</span>
              <input v-model="authSettings.ma_cb_ad_attribute" type="text" style="height: 42px; border-radius: 12px; border: 1px solid #dce4ed; padding: 0 12px; color: #0f172a; font-weight: 700;" />
              <span style="font-size: 12px; color: #64748b;">{{ authDescriptions.ma_cb_ad_attribute || '' }}</span>
            </label>
          </div>
        </div>

        <div style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08); overflow: hidden;">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div>
              <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Người dùng</div>
              <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">User Profiles Snapshot</div>
            </div>
            <div style="font-size: 14px; font-weight: 800; color: #005993;">{{ userProfiles.length }} bản ghi</div>
          </div>
          <div style="overflow: auto; border: 1px solid #e2e8f0; border-radius: 14px;">
            <table style="width: 100%; min-width: 1240px; border-collapse: collapse;">
              <thead style="background: #f8fbff;">
                <tr>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Username</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Name</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Auth</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Vị trí</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Mã CB</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Mã phòng</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">First Group</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">ArrDM</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Flags</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Last login</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="profile in userProfiles" :key="profile.username">
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; font-weight: 800;">{{ profile.username }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ profile.name_str || profile.display_name || '' }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ profile.auth_mode }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ profile.vi_tri }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ profile.ma_cb }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ profile.ma_phong }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ profile.first_group }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ (profile.arr_dm || []).join('; ') }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; color: #475569; font-size: 12px;">{{ profile.flags }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ profile.last_login_at }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08); overflow: hidden;">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div>
              <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Nhật ký đăng nhập</div>
              <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">Login Audit</div>
            </div>
            <div style="font-size: 14px; font-weight: 800; color: #005993;">{{ loginAudit.length }} bản ghi gần nhất</div>
          </div>
          <div style="overflow: auto; border: 1px solid #e2e8f0; border-radius: 14px;">
            <table style="width: 100%; min-width: 980px; border-collapse: collapse;">
              <thead style="background: #f8fbff;">
                <tr>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Time</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Username</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Auth</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Kết quả</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Lỗi</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Profile</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="audit in loginAudit" :key="audit.id">
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ audit.created_at }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; font-weight: 800;">{{ audit.username }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ audit.auth_mode }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">
                    <span :style="{ display: 'inline-flex', padding: '4px 10px', borderRadius: '999px', fontWeight: 800, background: audit.success ? '#ecfdf3' : '#fff1f2', color: audit.success ? '#047857' : '#be123c' }">
                      {{ audit.success ? 'Success' : 'Fail' }}
                    </span>
                  </td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; color: #be123c;">{{ audit.error_message }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; color: #64748b; font-size: 12px;">{{ audit.profile }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else-if="activeSection === 'ad-mappings'" style="display: grid; grid-template-columns: 1fr; gap: 20px;">
        <div style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08); overflow: hidden;">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div>
              <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Cấu hình nhóm AD</div>
              <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">AD Group Mappings</div>
            </div>
            <div style="display: flex; gap: 10px;">
              <button type="button" :disabled="!canEditAdMappings" @click="addMappingRow" style="height: 42px; padding: 0 18px; border-radius: 12px; border: 1px solid #005993; background: white; color: #005993; font-weight: 800; cursor: pointer;">+ Thêm dòng</button>
              <button type="button" :disabled="savingMappings || !canEditAdMappings" @click="saveAdMappings" style="height: 42px; padding: 0 18px; border-radius: 12px; border: none; background: #005993; color: white; font-weight: 800; cursor: pointer;">
                {{ savingMappings ? 'Đang lưu...' : 'Lưu mappings' }}
              </button>
            </div>
          </div>
          <div style="overflow: auto; border: 1px solid #e2e8f0; border-radius: 14px;">
            <table style="width: 100%; min-width: 1560px; border-collapse: collapse;">
              <thead style="background: #f8fbff;">
                <tr>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Type</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">AD Group</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Priority</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Position</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Dept Code</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Dept Name</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">First Group</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">ArrDM</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Function</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">Admin</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">BGD</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">TP</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">LDP</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">ĐM</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">On</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Notes</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in adMappings" :key="`${row.id || 'new'}-${index}`">
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><select v-model="row.mapping_type" style="width: 120px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;"><option v-for="option in mappingTypeOptions" :key="option" :value="option">{{ option }}</option></select></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.ad_group_name" type="text" style="width: 210px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model.number="row.priority" type="number" style="width: 88px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.position_code" type="text" style="width: 80px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.department_code" type="text" style="width: 90px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.department_name" type="text" style="width: 160px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.first_group" type="text" style="width: 150px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.arr_dm" type="text" style="width: 120px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.function_code" type="text" style="width: 90px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.flag_admin" type="checkbox" true-value="1" false-value="0" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.flag_bgd" type="checkbox" true-value="1" false-value="0" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.flag_truong_phong" type="checkbox" true-value="1" false-value="0" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.flag_lanh_dao_phong" type="checkbox" true-value="1" false-value="0" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.flag_dau_moi" type="checkbox" true-value="1" false-value="0" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.is_active" type="checkbox" true-value="1" false-value="0" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.notes" type="text" style="width: 220px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><button type="button" :disabled="!canEditAdMappings" @click="removeMappingRow(index)" style="height: 36px; width: 36px; border-radius: 10px; border: none; background: #fff1f2; color: #be123c; font-weight: 900; cursor: pointer;">×</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else-if="activeSection === 'user-overrides'" style="display: grid; grid-template-columns: 1fr; gap: 20px;">
        <div style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08); overflow: hidden;">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div>
              <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">User Overrides</div>
              <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">Ghi đè profile theo từng user</div>
            </div>
            <div style="display: flex; gap: 10px;">
              <button type="button" :disabled="!canEditUserOverrides" @click="addOverrideRow" style="height: 42px; padding: 0 18px; border-radius: 12px; border: 1px solid #005993; background: white; color: #005993; font-weight: 800; cursor: pointer;">+ Thêm user</button>
              <button type="button" :disabled="savingOverrides || !canEditUserOverrides" @click="saveUserOverrides" style="height: 42px; padding: 0 18px; border-radius: 12px; border: none; background: #005993; color: white; font-weight: 800; cursor: pointer;">
                {{ savingOverrides ? 'Đang lưu...' : 'Lưu overrides' }}
              </button>
            </div>
          </div>
          <div style="overflow: auto; border: 1px solid #e2e8f0; border-radius: 14px;">
            <table style="width: 100%; min-width: 1700px; border-collapse: collapse;">
              <thead style="background: #f8fbff;">
                <tr>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Username</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Display name</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Vị trí</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Mã CB</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Mã phòng</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Dept code</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Dept name</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">First Group</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">ArrDM</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">TP</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">LDP</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">ĐM</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">On</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Notes</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Updated</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in userOverrides" :key="`${row.username || 'new'}-${index}`">
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.username" type="text" style="width: 120px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.display_name" type="text" style="width: 170px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><select v-model="row.vi_tri" style="width: 80px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;"><option v-for="option in positionOptions" :key="option" :value="option">{{ option }}</option></select></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.ma_cb" type="text" style="width: 110px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.ma_phong" type="text" style="width: 90px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.department_code" type="text" style="width: 90px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.department_name" type="text" style="width: 150px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.first_group" type="text" style="width: 150px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.arr_dm" type="text" style="width: 120px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><select v-model="row.is_truong_phong" style="width: 70px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;"><option value="">--</option><option :value="1">1</option><option :value="0">0</option></select></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><select v-model="row.is_lanh_dao_phong" style="width: 70px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;"><option value="">--</option><option :value="1">1</option><option :value="0">0</option></select></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><select v-model="row.is_dau_moi" style="width: 70px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;"><option value="">--</option><option :value="1">1</option><option :value="0">0</option></select></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.is_active" type="checkbox" true-value="1" false-value="0" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.notes" type="text" style="width: 220px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; color: #64748b; font-size: 12px;">{{ row.updated_by }}<br />{{ row.updated_at }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><button type="button" :disabled="!canEditUserOverrides" @click="removeOverrideRow(index)" style="height: 36px; width: 36px; border-radius: 10px; border: none; background: #fff1f2; color: #be123c; font-weight: 900; cursor: pointer;">×</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else-if="activeSection === 'portal-permissions'" style="display: grid; grid-template-columns: 1fr; gap: 20px;">
        <div style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08); overflow: hidden;">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div>
              <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Vai trò và phân quyền</div>
              <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">Permission Store</div>
            </div>
            <div style="font-size: 14px; font-weight: 800; color: #005993;">{{ pagePermissions.length }} page quyền</div>
          </div>
          <div style="overflow: auto; border: 1px solid #e2e8f0; border-radius: 14px;">
            <table style="width: 100%; min-width: 1080px; border-collapse: collapse;">
              <thead style="background: #f8fbff;">
                <tr>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Page ID</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Module</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Nhãn</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Path cũ</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">Bật</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">Actions</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">Parts</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">Matrix</th>
                  <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Cập nhật</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!pagePermissions.length">
                  <td colspan="9" style="padding: 14px; color: #64748b;">Chưa có dữ liệu permission store.</td>
                </tr>
                <tr v-for="row in pagePermissions" :key="row.page_id">
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; font-weight: 800;">{{ row.page_id }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ row.module_id }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ row.label }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8;">{{ row.path }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;">{{ Number(row.enabled) ? 'Có' : 'Không' }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;">{{ Object.keys(row.actions || {}).length }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;">{{ Object.keys(row.parts || {}).length }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;">{{ Object.keys(row.matrix || {}).length ? 'Có' : 'Không' }}</td>
                  <td style="padding: 10px; border-top: 1px solid #eef3f8; color: #64748b; font-size: 12px;">{{ row.updated_by }}<br />{{ row.updated_at }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-else-if="activeSection === 'admin-management'" style="display: grid; grid-template-columns: 1fr; gap: 20px;">
        <div style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 16px;">
            <div>
              <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Quản trị Admin</div>
              <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">Admin cấp 1 / Admin cấp 2</div>
            </div>
            <div style="display: flex; gap: 10px;">
              <button type="button" :disabled="!canEditAdminManagement" @click="addAdminRoleRow" style="height: 42px; padding: 0 18px; border-radius: 12px; border: 1px solid #005993; background: white; color: #005993; font-weight: 800; cursor: pointer;">+ Thêm admin</button>
              <button type="button" :disabled="!canEditAdminManagement" @click="addAdminGrantRow" style="height: 42px; padding: 0 18px; border-radius: 12px; border: 1px solid #005993; background: white; color: #005993; font-weight: 800; cursor: pointer;">+ Thêm grant</button>
              <button type="button" :disabled="savingAdminManagement || !canEditAdminManagement" @click="saveAdminManagement" style="height: 42px; padding: 0 18px; border-radius: 12px; border: none; background: #005993; color: white; font-weight: 800; cursor: pointer;">
                {{ savingAdminManagement ? 'Đang lưu...' : 'Lưu quản trị admin' }}
              </button>
            </div>
          </div>
          <div style="margin-bottom: 16px; color: #475569; line-height: 1.7;">
            Dữ liệu khu này được lưu riêng để tránh trộn vai trò admin hệ thống vào <code>User Overrides</code> hoặc <code>Page Permissions</code>.
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px;">
            <div style="padding: 18px 20px; border-radius: 16px; background: #f8fbff; border: 1px solid #dce4ed;">
              <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Admin roles</div>
              <div style="margin-top: 10px; font-size: 28px; font-weight: 900; color: #0f172a;">{{ adminRoles.length }}</div>
            </div>
            <div style="padding: 18px 20px; border-radius: 16px; background: #f8fbff; border: 1px solid #dce4ed;">
              <div style="font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Admin grants</div>
              <div style="margin-top: 10px; font-size: 28px; font-weight: 900; color: #0f172a;">{{ adminGrants.length }}</div>
            </div>
          </div>
          <div style="display: grid; grid-template-columns: 1fr; gap: 18px;">
            <div style="overflow: auto; border: 1px solid #e2e8f0; border-radius: 14px;">
              <table style="width: 100%; min-width: 760px; border-collapse: collapse;">
                <thead style="background: #f8fbff;">
                  <tr>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Username</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Level</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">On</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Notes</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Updated</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!adminRoles.length">
                    <td colspan="6" style="padding: 14px; color: #64748b;">Chưa có admin role nào.</td>
                  </tr>
                  <tr v-for="(row, index) in adminRoles" :key="`${row.username || 'new'}-${index}`">
                    <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.username" type="text" style="width: 180px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8;"><select v-model.number="row.admin_level" style="width: 100px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;"><option v-for="level in adminLevelOptions" :key="level" :value="level">Cấp {{ level }}</option></select></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.is_active" type="checkbox" true-value="1" false-value="0" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.notes" type="text" style="width: 220px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; color: #64748b; font-size: 12px;">{{ row.granted_by }}<br />{{ row.updated_at }}</td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><button type="button" :disabled="!canEditAdminManagement" @click="removeAdminRoleRow(index)" style="height: 36px; width: 36px; border-radius: 10px; border: none; background: #fff1f2; color: #be123c; font-weight: 900; cursor: pointer;">×</button></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div style="overflow: auto; border: 1px solid #e2e8f0; border-radius: 14px;">
              <table style="width: 100%; min-width: 980px; border-collapse: collapse;">
                <thead style="background: #f8fbff;">
                  <tr>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Username</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Section</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">View</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">Edit</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;">On</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Notes</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: left;">Updated</th>
                    <th style="padding: 12px; border-bottom: 1px solid #dce4ed; text-align: center;"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!adminGrants.length">
                    <td colspan="8" style="padding: 14px; color: #64748b;">Chưa có admin grant nào.</td>
                  </tr>
                  <tr v-for="(row, index) in adminGrants" :key="`${row.id || 'new'}-${index}`">
                    <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.username" type="text" style="width: 180px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8;"><select v-model="row.section_key" style="width: 180px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;"><option v-for="section in portalAdminGrantSections" :key="section" :value="section">{{ section }}</option></select></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.can_view" type="checkbox" true-value="1" false-value="0" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.can_edit" type="checkbox" true-value="1" false-value="0" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><input v-model="row.is_active" type="checkbox" true-value="1" false-value="0" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8;"><input v-model="row.notes" type="text" style="width: 220px; height: 38px; border-radius: 10px; border: 1px solid #dce4ed; padding: 0 10px;" /></td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; color: #64748b; font-size: 12px;">{{ row.granted_by }}<br />{{ row.updated_at }}</td>
                    <td style="padding: 10px; border-top: 1px solid #eef3f8; text-align: center;"><button type="button" :disabled="!canEditAdminManagement" @click="removeAdminGrantRow(index)" style="height: 36px; width: 36px; border-radius: 10px; border: none; background: #fff1f2; color: #be123c; font-weight: 900; cursor: pointer;">×</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="activeSection === 'auth-policy'" style="padding: 22px; border-radius: 18px; background: white; border: 1px solid #dce4ed; box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);">
        <div style="font-size: 13px; font-weight: 900; letter-spacing: 0.08em; color: #64748b; text-transform: uppercase;">Auth Policy</div>
        <div style="margin-top: 8px; font-size: 24px; font-weight: 900; color: #0f172a;">Emergency Access & Chính sách xác thực</div>
        <div style="margin-top: 12px; color: #475569; line-height: 1.7;">
          Khu này được giữ riêng cho cấu hình production auth, fallback khẩn cấp, và các chính sách xác thực mức hệ thống.
          Ở giai đoạn này, phần UI được tách riêng để tránh trộn vào khu cấu hình user thường.
        </div>
      </div>
    </template>
  </div>
</template>
