import { ref, computed } from 'vue'
import { useAuthStore } from '../../../app/stores/auth'
import { apiFetchJSON } from '../../../shared/api/client'

const cases = ref([])
const loading = ref(true)
const lastUpdate = ref('')

const adminConfig = ref({ cb_config: [], ld_config: [], sla_config: [], room_config: [] })
const adminLoading = ref(false)

const ruleConfig = ref({ routing: [], assignment: [] })
const ruleLoading = ref(false)

const readyOfficers = computed(() => {
    if (!adminConfig.value || !adminConfig.value.cb_config) return [];
    return adminConfig.value.cb_config.filter(cb => cb['Trạng thái'] === 'Ready' && String(cb.is_active) !== '0');
})

export function useSmartVCOMS() {
    const { token, currentUser, permissionSnapshot } = useAuthStore()

    const fetchAPI = async (url, options = {}) => {
        return apiFetchJSON(url, options)
    }

    const loadCases = async () => {
        try {
            const res = await fetchAPI('/api/vcoms/cases')
            if (res.status === 'success') {
                cases.value = res.data
                lastUpdate.value = new Date().toLocaleTimeString('vi-VN')
            }
        } catch (e) {
            console.error("Lỗi tải Kanban:", e)
        } finally {
            loading.value = false
        }
    }

    const loadAdminConfig = async () => {
        adminLoading.value = true
        try {
            const res = await fetchAPI('/api/vcoms/admin/config')
            if (res.status === 'success') {
                adminConfig.value = res.data
            }
        } catch (e) {
            console.error("Lỗi tải cấu hình admin:", e)
        } finally {
            adminLoading.value = false
        }
    }

    const loadRules = async () => {
        ruleLoading.value = true
        try {
            const res = await fetchAPI('/api/vcoms/admin/rules')
            if (res.status === 'success') {
                ruleConfig.value = res.data
            }
        } catch (e) { console.error("Lỗi tải Rules:", e) } 
        finally { ruleLoading.value = false }
    }

    const formatMoneyFull = (val, cur) => {
        const c = cur || 'VNĐ';
        if (!val) return '0 ' + c;
        return new Intl.NumberFormat('vi-VN').format(val) + ' ' + c;
    }

    const formatMoney = (val, cur) => {
        const c = cur || 'VNĐ';
        if (!val) return '0 ' + c;
        if (c === 'USD' || c === 'EUR') {
            if (val >= 1000) return (val / 1000).toLocaleString('vi-VN', {maximumFractionDigits: 1}) + 'k ' + c;
            return new Intl.NumberFormat('vi-VN').format(val) + ' ' + c;
        }
        if (val >= 1000000) return Math.round(val / 1000000).toLocaleString('vi-VN') + ' Trđ';
        return new Intl.NumberFormat('vi-VN').format(val) + ' ' + c;
    }

    return {
        token, currentUser, cases, loading, lastUpdate,
        permissionSnapshot,
        adminConfig, adminLoading, ruleConfig, ruleLoading,
        readyOfficers, fetchAPI, loadCases, loadAdminConfig, loadRules,
        formatMoneyFull, formatMoney 
    }
}
