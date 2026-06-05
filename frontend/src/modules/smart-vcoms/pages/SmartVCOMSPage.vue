<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useSmartVCOMS } from '../composables/useSmartVCOMS'
import TabStatistics from '../components/TabStatistics.vue'
import TabAdminConfig from '../components/TabAdminConfig.vue'
import TabRuleEngine from '../components/TabRuleEngine.vue'

const {
    currentUser, permissionSnapshot, cases, loading, lastUpdate,
    adminConfig, readyOfficers, fetchAPI, loadCases, loadLookupConfig, loadAdminConfig, loadRules,
    formatMoneyFull, formatMoney
} = useSmartVCOMS()

let refreshInterval = null
const activeTab = ref('BAN_DIEU_PHOI')

// --- SIÊU POPUP CHI TIẾT HỒ SƠ ---
const showStatDetailModal = ref(false)
const statFilters = ref({ cb: [], ldp: [], status: [], room: [], progress: [], sla: [], khung_gio: [], tg_cho_gn: [] })
const activeStatDropdown = ref(null)

const toggleStatDropdown = (type) => {
    activeStatDropdown.value = activeStatDropdown.value === type ? null : type
}

const openStatDetail = (initialFilters = {}) => {
    statFilters.value = { cb: [], ldp: [], status: [], room: [], progress: [], sla: [], khung_gio: [], tg_cho_gn: [], ...initialFilters }
    showStatDetailModal.value = true
}

const statFilterOptions = computed(() => {
    const cbs = new Set(); const ldps = new Set(); const rooms = new Set(); const progresses = new Set();
    cases.value.forEach(c => {
        if (c.cb_id || c.cb_httd) cbs.add(c.cb_id || c.cb_httd)
        if (c.ldp_ksv) ldps.add(c.ldp_ksv)
        if (c.room_short) rooms.add(c.room_short)
        if (c.stage_label_base) progresses.add(c.stage_label_base)
    })
    return {
        cb: Array.from(cbs).sort(),
        ldp: Array.from(ldps).sort(),
        status: ["Chưa hoàn thành", "Hoàn thành"],
        room: Array.from(rooms).sort(),
        progress: Array.from(progresses).sort(),
        sla: ["Đạt SLA", "Vượt SLA"],
        khung_gio: ['<08h', '08h-09h', '09h-10h', '10h-11h', '11h-13h', '13h-14h', '14h-15h', '15h-16h', '16h-17h', '>17h'],
        tg_cho_gn: ["< 15p", "15-30p", "30-45p", "45-60p", "> 60p"]
    }
})

const filteredStatCases = computed(() => {
    return cases.value.filter(c => {
        if (statFilters.value.cb.length > 0) {
            const cb = c.cb_id || c.cb_httd
            if (!statFilters.value.cb.includes(cb)) return false
        }
        if (statFilters.value.ldp.length > 0 && !statFilters.value.ldp.includes(c.ldp_ksv)) return false
        if (statFilters.value.status.length > 0) {
            const st = c.kanban_column === 'CLOSED' ? 'Hoàn thành' : 'Chưa hoàn thành'
            if (!statFilters.value.status.includes(st)) return false
        }
        if (statFilters.value.room.length > 0 && !statFilters.value.room.includes(c.room_short)) return false
        if (statFilters.value.progress.length > 0) {
            const baseLabel = c.stage_label_base || (c.stage_label || '').split(' (')[0];
            if (!statFilters.value.progress.includes(baseLabel)) return false;
        }
        if (statFilters.value.sla.length > 0) {
            let isSLA = 'Đạt SLA';
            if (c.kanban_column === 'CLOSED') {
                isSLA = (c.time_display === 'Đã xong' || c.time_display.startsWith('Sớm')) ? 'Đạt SLA' : 'Vượt SLA';
            } else {
                isSLA = c.mins_left >= 0 ? 'Đạt SLA' : 'Vượt SLA';
            }
            if (!statFilters.value.sla.includes(isSLA)) return false
        }
        if (statFilters.value.khung_gio.length > 0 && !statFilters.value.khung_gio.includes(c.khung_gio)) return false
        if (statFilters.value.tg_cho_gn.length > 0 && !statFilters.value.tg_cho_gn.includes(c.tg_cho_gn)) return false
        return true
    })
})

const exportExcel = () => {
    const headers = ["STT", "Trạng thái", "Phòng", "CIF", "Tên KH", "STK", "Số tiền GN", "CB HTTD", "LĐP/KSV", "Tiến độ", "Thời gian"];
    const rows = filteredStatCases.value.map((c, i) => [
        i + 1,
        c.kanban_column === 'CLOSED' ? 'Hoàn thành' : 'Đang xử lý',
        c.room_short,
        c.cif,
        c.customer_name,
        c.stk,
        c.amount,
        c.cb_id || c.cb_httd || '',
        c.ldp_ksv || '',
        c.stage_label,
        c.time_display
    ]);
    
    let csvContent = "\uFEFF" + headers.join(",") + "\n";
    rows.forEach(r => {
        const rowString = r.map(field => `"${String(field || '').replace(/"/g, '""')}"`).join(",");
        csvContent += rowString + "\n";
    });
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `DanhSachHoSo_VCOMS_${new Date().getTime()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

const activeDropdown = ref(null)
const toggleDropdown = (idx) => {
    activeDropdown.value = activeDropdown.value === idx ? null : idx
}

const smartTruncate = (name, maxLen) => {
    if (!name) return "";
    let n = name.trim();
    let up = n.toUpperCase();
    const prefixes = ["CÔNG TY TNHH MTV ", "CONG TY TNHH MTV ", "CTY TNHH MTV ", "CT TNHH MTV ", "CÔNG TY TNHH ", "CONG TY TNHH ", "CTY TNHH ", "CT TNHH ", "CÔNG TY CỔ PHẦN ", "CONG TY CO PHAN ", "CTCP ", "CÔNG TY CP ", "CONG TY CP ", "CÔNG TY ", "CONG TY ", "CTY ", "CT ", "DNTN ", "DOANH NGHIEP "];
    let isKHDN = false;
    for (let p of prefixes) {
        if (up.startsWith(p)) {
            isKHDN = true;
            n = n.substring(p.length).trim();
            break;
        }
    }
    
    if (name.length <= maxLen) return name;
    
    if (isKHDN) {
        let allowed_len = maxLen - 7; // Trừ 7 ký tự cho cụm "CT ... "
        if (n.length <= allowed_len) return "CT ... " + n;
        
        let cutIdx = n.length - allowed_len;
        let suffix = n.substring(cutIdx);
        
        // Nếu lưỡi dao cắt ngang giữa một chữ -> Tìm dấu cách đầu tiên để bỏ phần chữ rác đi
        if (cutIdx > 0 && n.charAt(cutIdx - 1) !== ' ' && suffix.charAt(0) !== ' ') {
            let firstSpaceIdx = suffix.indexOf(' ');
            if (firstSpaceIdx !== -1) {
                suffix = suffix.substring(firstSpaceIdx + 1);
            }
        }
        return "CT ... " + suffix.trim();
    } else {
        let words = name.split(/\s+/);
        if (words.length <= 2) {
            let allowed_len = maxLen - 3;
            let prefix_cn = name.substring(0, allowed_len);
            if (name.length > allowed_len && name.charAt(allowed_len) !== ' ' && prefix_cn.charAt(prefix_cn.length - 1) !== ' ') {
                let lastSpaceIdx = prefix_cn.lastIndexOf(' ');
                if (lastSpaceIdx !== -1) prefix_cn = prefix_cn.substring(0, lastSpaceIdx);
            }
            return prefix_cn.trim() + "...";
        }
        
        let ho = words[0];
        let tail = "";
        for (let i = words.length - 1; i >= 1; i--) {
            let current_tail = (tail === "") ? words[i] : words[i] + " " + tail;
            if (ho.length + 5 + current_tail.length <= maxLen) {
                tail = current_tail;
            } else {
                break;
            }
        }
        
        if (tail === "") {
            let allowed_len = maxLen - 3;
            let prefix_cn = name.substring(0, allowed_len);
            if (name.length > allowed_len && name.charAt(allowed_len) !== ' ' && prefix_cn.charAt(prefix_cn.length - 1) !== ' ') {
                let lastSpaceIdx = prefix_cn.lastIndexOf(' ');
                if (lastSpaceIdx !== -1) prefix_cn = prefix_cn.substring(0, lastSpaceIdx);
            }
            return prefix_cn.trim() + "...";
        }
        return ho + " ... " + tail;
    }
}

const canViewKanban = computed(() => Boolean(permissionSnapshot.value?.pages?.SmartVCOMS?.parts?.ban_dieu_phoi?.view))
const canViewStatistics = computed(() => Boolean(permissionSnapshot.value?.pages?.SmartVCOMS?.parts?.thong_ke?.view))
const canViewAdmin = computed(() => Boolean(permissionSnapshot.value?.pages?.SmartVCOMS?.parts?.quan_tri_he_thong?.view))

watch(
    [canViewKanban, canViewStatistics, canViewAdmin],
    ([kanban, stats, admin]) => {
        if (activeTab.value === 'BAN_DIEU_PHOI' && !kanban) {
            activeTab.value = stats ? 'THONG_KE' : admin ? 'QUAN_TRI' : 'BAN_DIEU_PHOI'
        }
        if (activeTab.value === 'THONG_KE' && !stats) {
            activeTab.value = kanban ? 'BAN_DIEU_PHOI' : admin ? 'QUAN_TRI' : 'THONG_KE'
        }
        if ((activeTab.value === 'QUAN_TRI' || activeTab.value === 'RULE_ENGINE') && !admin) {
            activeTab.value = kanban ? 'BAN_DIEU_PHOI' : stats ? 'THONG_KE' : 'BAN_DIEU_PHOI'
        }
    },
    { immediate: true }
)

onMounted(() => {
    if (canViewKanban.value || canViewStatistics.value || canViewAdmin.value) {
        loadLookupConfig()
    }
    if (canViewAdmin.value) {
        loadRules()
    }
    if (canViewKanban.value) {
        loadCases()
    }
    refreshInterval = setInterval(() => {
        if (activeTab.value === 'BAN_DIEU_PHOI' && canViewKanban.value && !showCaseDetail.value) {
            loadCases()
        }
    }, 1000)
})

onUnmounted(() => {
    if (refreshInterval) clearInterval(refreshInterval)
})

watch(activeTab, (newTab) => {
    if ((newTab === 'BAN_DIEU_PHOI' || newTab === 'THONG_KE') && adminConfig.value.room_config.length === 0) {
        loadLookupConfig()
    }
    if (newTab === 'QUAN_TRI' && canViewAdmin.value) {
        loadAdminConfig()
    }
    if (newTab === 'RULE_ENGINE' && canViewAdmin.value) {
        if (adminConfig.value.cb_config.length === 0) {
            loadLookupConfig() // Load ké dữ liệu CB và Phòng ban nếu chưa có
        }
        loadRules()
    }
})

// --- LOGIC MODAL CHI TIẾT & GHI ĐÈ THỦ CÔNG ---
const showCaseDetail = ref(false)
const selectedCase = ref(null)
const editCaseData = ref({})

const resolveCaseOfficerId = (caseData) => {
    const rawCandidates = [
        caseData?.cb_httd,
        caseData?.cb_id,
        caseData?.assigned_officer,
    ]
    const officers = readyOfficers.value || []

    for (const raw of rawCandidates) {
        const value = String(raw || '').trim()
        if (!value || value === '---') continue

        const matched = officers.find(cb => {
            const id = String(cb.ID_CB || '').trim()
            const name = String(cb['Tên Cán bộ'] || '').trim()
            return id.toUpperCase() === value.toUpperCase()
                || name.toUpperCase() === value.toUpperCase()
        })

        if (matched) return String(matched.ID_CB || '').trim()
    }

    return String(caseData?.cb_id || caseData?.cb_httd || '').trim()
}

const openCaseDetail = (c) => {
    selectedCase.value = c
    editCaseData.value = { ...c, cb_httd: resolveCaseOfficerId(c) }
    showCaseDetail.value = true
}

const isOverridden = (field) => {
    return selectedCase.value?.overridden_fields?.includes(field)
}

const saveOverride = async (field, value) => {
    try {
        const res = await fetchAPI('/api/vcoms/manual-override', {
            method: 'POST',
            body: JSON.stringify({ case_key: selectedCase.value.case_key, field_name: field, manual_value: String(value) })
        })
        if (res.status === 'success') { await loadCases(); updateSelectedCase(); }
        else { alert("Lỗi ghi đè: " + res.message); }
    } catch(e) { console.error(e) }
}

const removeOverride = async (field) => {
    try {
        const res = await fetchAPI(`/api/vcoms/manual-override/${selectedCase.value.case_key}/${field}`, { method: 'DELETE' })
        if (res.status === 'success') { await loadCases(); updateSelectedCase(); }
        else { alert("Lỗi mở khóa: " + res.message); }
    } catch(e) { console.error(e) }
}

const updateSelectedCase = () => {
    const updated = cases.value.find(c => c.case_key === selectedCase.value.case_key)
    if (updated) { selectedCase.value = updated; editCaseData.value = { ...updated, cb_httd: resolveCaseOfficerId(updated) } }
}

const manualNote = ref('')
const doManualAction = async (actionType) => {
    if(!confirm("Bạn có chắc chắn muốn đẩy thẻ hồ sơ này sang trạng thái mới?")) return;
    try {
        const res = await fetchAPI('/api/vcoms/manual-action', {
            method: 'POST',
            body: JSON.stringify({ 
                case_key: selectedCase.value.case_key, 
                action_type: actionType, 
                note: manualNote.value 
            })
        })
        if(res.status === 'success') {
            alert("Cập nhật thẻ Kanban thành công!");
            showCaseDetail.value = false;
            manualNote.value = '';
            loadCases();
        } else { alert("Lỗi: " + res.message); }
    } catch(e) { console.error(e) }
}

const undoManualAction = async () => {
    if(!confirm("Bạn có chắc chắn muốn HỦY thao tác thủ công, trả hồ sơ về luồng máy tính tự động?")) return;
    try {
        const res = await fetchAPI(`/api/vcoms/manual-action/${selectedCase.value.case_key}`, { method: 'DELETE' })
        if(res.status === 'success') {
            alert(res.message);
            showCaseDetail.value = false;
            loadCases();
        } else { alert("Lỗi: " + res.message); }
    } catch(e) { console.error(e) }
}

const currentDate = computed(() => new Date().toLocaleDateString('vi-VN'))

const totalCases = computed(() => cases.value.length)
const closedCases = computed(() => cases.value.filter(c => c.kanban_column === 'CLOSED'))
const openCasesCount = computed(() => totalCases.value - closedCases.value.length)
const completionRate = computed(() => totalCases.value ? ((closedCases.value.length / totalCases.value) * 100).toFixed(1) : 0)

const chartData = computed(() => {
    const cbMap = {};
    
    // Initialize map from adminConfig
    if (adminConfig.value && adminConfig.value.cb_config) {
        adminConfig.value.cb_config.forEach(config => {
            if (config.is_active === 0) return;
            const cbId = config.ID_CB;
            if (cbId) {
                cbMap[cbId] = { 
                    name: cbId, 
                    closed: 0, 
                    processing: 0, 
                    status: config['Trạng thái'] || 'Ready' 
                };
            }
        });
    }

    // Count cases
    cases.value.forEach(c => {
        const cb = c.cb_id || c.cb_httd;
        if (!cb || cb.trim() === '' || cb === '---') return;
        
        if (!cbMap[cb]) {
            cbMap[cb] = { name: cb, closed: 0, processing: 0, status: 'Ready' };
        }
        
        if (c.kanban_column === 'CLOSED') {
            cbMap[cb].closed++;
        } else {
            cbMap[cb].processing++;
        }
    });

    let arr = Object.values(cbMap).sort((a, b) => {
        const totalA = a.closed + a.processing;
        const totalB = b.closed + b.processing;
        if (totalB !== totalA) {
            return totalB - totalA;
        }
        return a.name.localeCompare(b.name);
    });
    
    let maxVal = 20;
    arr.forEach(a => {
        const tot = a.closed + a.processing;
        if (tot > maxVal) maxVal = tot;
    });
    arr.forEach(a => { a._max = maxVal; });
    return arr;
});

const arrivalCases = computed(() => {
    let filtered = cases.value.filter(c => c.kanban_column === 'ARRIVAL_ACCEPT');
    const orderMap = { 'ARRIVAL': 0, 'WAIT_ACCEPT': 1 };
    return filtered.sort((a, b) => {
        let oA = orderMap[a.stage_code] !== undefined ? orderMap[a.stage_code] : 99;
        let oB = orderMap[b.stage_code] !== undefined ? orderMap[b.stage_code] : 99;
        if (oA !== oB) return oA - oB;
        return a.mins_left - b.mins_left;
    });
});
const processingCases = computed(() => {
    let filtered = cases.value.filter(c => c.kanban_column === 'PROCESSING');
    const orderMap = { 'PROCESSING': 0, 'WAIT_SIGN': 1, 'WAIT_MANUAL_DONE': 2 };
    return filtered.sort((a, b) => {
        let oA = orderMap[a.stage_code] !== undefined ? orderMap[a.stage_code] : 99;
        let oB = orderMap[b.stage_code] !== undefined ? orderMap[b.stage_code] : 99;
        if (oA !== oB) return oA - oB;
        return a.mins_left - b.mins_left;
    });
});
const waitCases = computed(() => cases.value.filter(c => c.kanban_column === 'WAIT_DISBURSE'))

// Chia đôi cột hoàn tất để tiết kiệm không gian
const closedCasesPairs = computed(() => {
    const pairs = []
    const arr = closedCases.value
    for (let i = 0; i < arr.length; i += 2) {
        pairs.push([arr[i], arr[i + 1] || null])
    }
    return pairs
})
</script>

<template>
  <div class="vcoms-container">
    <div :class="['vcoms-header-shell', activeTab === 'BAN_DIEU_PHOI' ? 'has-kpi-row' : 'compact-header']">
        <div class="vcoms-identity-panel">
            <div class="vcoms-brand-area">
                <div class="vcoms-brand-title">SmartVCOMS</div>
                <div class="vcoms-brand-subtitle">Điều phối &amp; Giám sát SLA</div>
            </div>
        </div>
        <div :class="['vcoms-header-main', activeTab === 'BAN_DIEU_PHOI' ? 'has-kpi-row' : 'compact-header']">
            <div class="vcoms-topbar">
                <div class="vcoms-tabs-area">
                    <button v-if="canViewKanban" :class="['tv-tab', activeTab === 'BAN_DIEU_PHOI' ? 'active' : '']" @click="activeTab = 'BAN_DIEU_PHOI'">📍 BÀN ĐIỀU PHỐI</button>
                    <button v-if="canViewStatistics" :class="['tv-tab', activeTab === 'THONG_KE' ? 'active' : '']" @click="activeTab = 'THONG_KE'">📊 THỐNG KÊ</button>
                    <button v-if="canViewAdmin" :class="['tv-tab', activeTab === 'QUAN_TRI' ? 'active' : '']" @click="activeTab = 'QUAN_TRI'">⚙️ QUẢN TRỊ</button>
                    <button v-if="canViewAdmin" :class="['tv-tab', activeTab === 'RULE_ENGINE' ? 'active' : '']" @click="activeTab = 'RULE_ENGINE'">🧠 RULE ENGINE</button>
                </div>
                <div class="vcoms-actions-area">
                    <span class="vcoms-meta-pill vcoms-date-badge">🕒 {{ currentDate }}</span>
                    <span class="vcoms-meta-pill vcoms-update-pill">🔄 Cập nhật: <strong>{{ lastUpdate }}</strong></span>
                </div>
            </div>

            <div v-if="activeTab === 'BAN_DIEU_PHOI'" class="vcoms-kpi-row">
                <div class="vcoms-kpi-cards">
                    <div class="kpi-card bg-total">
                        <div class="kpi-icon">📋</div>
                        <div class="kpi-content"><div class="kpi-title">TỔNG HỒ SƠ</div><div class="kpi-val">{{ totalCases }}</div></div>
                    </div>
                    <div class="kpi-card bg-open">
                        <div class="kpi-icon">⏳</div>
                        <div class="kpi-content"><div class="kpi-title">ĐANG MỞ</div><div class="kpi-val">{{ openCasesCount }}</div></div>
                    </div>
                    <div class="kpi-card bg-closed">
                        <div class="kpi-icon">✅</div>
                        <div class="kpi-content"><div class="kpi-title">HOÀN TẤT</div><div class="kpi-val">{{ closedCases.length }}</div></div>
                    </div>
                    <div class="kpi-card bg-rate">
                        <div class="kpi-icon">📈</div>
                        <div class="kpi-content"><div class="kpi-title">TỶ LỆ HOÀN THÀNH</div><div class="kpi-val">{{ completionRate }}%</div></div>
                    </div>
                </div>
                <div class="vcoms-officer-card">
                    <div v-for="cb in chartData" :key="cb.name" class="vcoms-officer-row" @click="openStatDetail({ cb: [cb.name] })">
                        <span class="vcoms-officer-name">{{ cb.name }}</span>
                        <span class="vcoms-officer-status">{{ cb.status }}</span>
                        <div class="vcoms-officer-progress">
                            <div class="officer-progress-processing" :style="{ width: (cb.processing / cb._max * 100) + '%' }" :title="'Đang xử lý: ' + cb.processing">{{ cb.processing > 0 ? cb.processing : '' }}</div>
                            <div class="officer-progress-closed" :style="{ width: (cb.closed / cb._max * 100) + '%' }" :title="'Hoàn thành: ' + cb.closed">{{ cb.closed > 0 ? cb.closed : '' }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div v-if="loading && activeTab === 'BAN_DIEU_PHOI'" style="text-align:center; padding: 50px; color:#005993;">Đang tải dữ liệu SmartVCOMS...</div>

    <div v-else-if="activeTab === 'BAN_DIEU_PHOI'" class="vcoms-tab-pane">
        <div class="kanban-board">
            <div class="kanban-col col-open">
                <div class="kb-header">📌 BẢNG HỒ SƠ ĐANG MỞ ({{ openCasesCount }})</div>

                <div class="kb-title-sub">📥 HỒ SƠ ĐẾN / CHỜ TIẾP NHẬN ({{ arrivalCases.length }})</div>
                <div class="kb-scroll" style="max-height: 25vh;">
                    <table class="main-table">
                        <thead>
                            <tr>
                                <th style="width:12%;">Phòng</th>
                                <th style="width:36%;" class="text-left">Tên Khách Hàng</th>
                                <th style="width:20%;" class="text-right">Số Tiền GN</th>
                                <th style="width:10%;">CB</th>
                                <th style="width:22%;">Tiến độ</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="c in arrivalCases" :key="c.case_key" class="clickable-row" @click="openCaseDetail(c)">
                                <td>{{ c.room_short }}</td>
                                <td class="text-left"><span class="truncate" :title="c.customer_name">{{ smartTruncate(c.customer_name, 34) }}</span></td>
                                <td class="text-right">{{ formatMoneyFull(c.amount, c.currency) }}</td>
                                <td>{{ c.cb_id || c.cb_httd || '---' }}</td>
                                <td>
                                    <span
                                        class="truncate"
                                        :title="c.stage_label"
                                        :class="{ 'time-red': c.wait_mins > 45, 'time-orange': c.wait_mins > 30 && c.wait_mins <= 45, 'time-yellow': c.wait_mins > 15 && c.wait_mins <= 30 }"
                                    >
                                        {{ c.stage_label }}
                                    </span>
                                </td>
                            </tr>
                            <tr v-if="arrivalCases.length === 0"><td colspan="5" class="empty-state">Chưa có hồ sơ</td></tr>
                        </tbody>
                    </table>
                </div>

                <div class="kb-title-sub" style="margin-top: 10px;">⏳ ĐANG TÁC NGHIỆP / CHỜ BGĐ KÝ SỐ / CHỜ HOÀN TẤT ({{ processingCases.length }})</div>
                <div class="kb-scroll">
                    <table class="main-table">
                        <thead>
                            <tr>
                                <th style="width:11%;">Phòng</th>
                                <th style="width:34%;" class="text-left">Tên Khách Hàng</th>
                                <th style="width:19%;" class="text-right">Số Tiền GN</th>
                                <th style="width:9%;">CB</th>
                                <th style="width:18%;">Tiến độ</th>
                                <th style="width:9%;">SLA</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr
                                v-for="c in processingCases"
                                :key="c.case_key"
                                :class="[c.sla_status === 'DANGER' ? 'sla-red' : c.sla_status === 'WARNING' || c.sla_status === 'YELLOW' ? 'sla-yellow' : 'sla-green', 'clickable-row']"
                                @click="openCaseDetail(c)"
                            >
                                <td>{{ c.room_short }}</td>
                                <td class="text-left"><span class="truncate" :title="c.customer_name">{{ smartTruncate(c.customer_name, 34) }}</span></td>
                                <td class="text-right">{{ formatMoneyFull(c.amount, c.currency) }}</td>
                                <td>{{ c.cb_id || c.cb_httd || '---' }}</td>
                                <td><span class="truncate" :title="c.stage_label">{{ c.stage_label }}</span></td>
                                <td><b :class="c.sla_status === 'DANGER' ? 'time-red' : c.sla_status === 'WARNING' || c.sla_status === 'YELLOW' ? 'time-orange' : 'time-green'">{{ c.time_display }}</b></td>
                            </tr>
                            <tr v-if="processingCases.length === 0"><td colspan="6" class="empty-state">Chưa có hồ sơ</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="kanban-col col-wait">
                <div class="kb-header">✍️ CHỜ GIẢI NGÂN ({{ waitCases.length }})</div>
                <div class="kb-scroll">
                    <table class="main-table">
                        <thead>
                            <tr>
                                <th style="width:15%;">Phòng</th>
                                <th style="width:32%;" class="text-left">Khách hàng</th>
                                <th style="width:26%;" class="text-right">Số tiền</th>
                                <th style="width:15%;">Thời gian</th>
                                <th style="width:12%;">CB</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr
                                v-for="c in waitCases"
                                :key="c.case_key"
                                :class="[c.sla_status === 'DANGER' ? 'row-wait-red' : c.sla_status === 'WARNING' || c.sla_status === 'YELLOW' ? 'row-wait-yellow' : '', 'clickable-row']"
                                @click="openCaseDetail(c)"
                            >
                                <td>{{ c.room_short }}</td>
                                <td class="text-left"><span class="truncate" :title="c.customer_name">{{ smartTruncate(c.customer_name, 24) }}</span></td>
                                <td class="text-right">{{ formatMoneyFull(c.amount, c.currency) }}</td>
                                <td>Chờ {{ c.wait_mins }}p</td>
                                <td>{{ c.cb_id || c.cb_httd || '---' }}</td>
                            </tr>
                            <tr v-if="waitCases.length === 0"><td colspan="5" class="empty-state">Chưa có hồ sơ</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="kanban-col col-done">
                <div class="kb-header">✅ HOÀN TẤT ({{ closedCases.length }})</div>
                <div class="kb-scroll">
                    <table class="sub-table" style="table-layout: fixed; width: 100%;">
                        <thead>
                            <tr>
                                <th style="width:33%;" class="text-left">Khách hàng</th>
                                <th style="width:16%;" class="text-right">Số tiền</th>
                                <th style="width:2%;" class="gap-col"></th>
                                <th style="width:33%;" class="text-left">Khách hàng</th>
                                <th style="width:16%;" class="text-right">Số tiền</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="(pair, idx) in closedCasesPairs" :key="idx">
                                <td class="text-left" style="border-right: none;"><span class="truncate" :title="pair[0].customer_name">{{ smartTruncate(pair[0].customer_name, 25) }}</span></td>
                                <td class="text-right" style="border-right: 1px solid #edf2f7;">{{ formatMoney(pair[0].amount, pair[0].currency) }}</td>
                                <td class="gap-col"></td>
                                <td class="text-left" style="border-left: 1px solid #edf2f7;"><span v-if="pair[1]" class="truncate" :title="pair[1].customer_name">{{ smartTruncate(pair[1].customer_name, 25) }}</span></td>
                                <td class="text-right"><span v-if="pair[1]">{{ formatMoney(pair[1].amount, pair[1].currency) }}</span></td>
                            </tr>
                            <tr v-if="closedCases.length === 0"><td colspan="5" class="empty-state">Chưa có hồ sơ</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <div v-if="activeTab === 'THONG_KE'" class="vcoms-tab-pane vcoms-statistics-pane">
        <TabStatistics @open-stat-detail="openStatDetail" />
    </div>
    <div v-if="activeTab === 'QUAN_TRI' && canViewAdmin" class="vcoms-tab-pane">
        <TabAdminConfig />
    </div>
    <div v-if="activeTab === 'RULE_ENGINE' && canViewAdmin" class="vcoms-tab-pane">
        <TabRuleEngine />
    </div>

    <div v-if="showStatDetailModal" class="modal-overlay" style="z-index: 9999;" @click.self="showStatDetailModal = false">
        <div class="modal-content" style="width: 95vw; height: 90vh; display: flex; flex-direction: column; padding: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h2 style="margin: 0; color: #005993; text-transform: uppercase;">📋 CHI TIẾT HỒ SƠ ({{ filteredStatCases.length }} HS)</h2>
                <div style="display: flex; gap: 10px;">
                    <button @click="exportExcel" style="background: #27ae60; color: white; border: none; font-size: 14px; font-weight: bold; cursor: pointer; padding: 6px 15px; border-radius: 6px;">📥 XUẤT EXCEL</button>
                    <button @click="showStatDetailModal = false" style="background: #c0392b; color: white; border: none; font-size: 14px; font-weight: bold; cursor: pointer; padding: 6px 15px; border-radius: 6px;">ĐÓNG ❌</button>
                </div>
            </div>

            <div style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
                <div style="flex: 1.4; position: relative;">
                    <div @click="toggleStatDropdown('cb')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.cb.length > 0 ? statFilters.cb.join(', ') : 'Cán bộ (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'cb' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'cb'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.cb" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'cb_'+opt" :value="opt" v-model="statFilters.cb">
                            <label :for="'cb_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
                <div style="flex: 1.4; position: relative;">
                    <div @click="toggleStatDropdown('ldp')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.ldp.length > 0 ? statFilters.ldp.join(', ') : 'LĐP/KSV (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'ldp' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'ldp'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.ldp" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'ldp_'+opt" :value="opt" v-model="statFilters.ldp">
                            <label :for="'ldp_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
                <div style="flex: 1.4; position: relative;">
                    <div @click="toggleStatDropdown('status')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.status.length > 0 ? statFilters.status.join(', ') : 'Trạng thái (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'status' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'status'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.status" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'st_'+opt" :value="opt" v-model="statFilters.status">
                            <label :for="'st_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
                <div style="flex: 1.4; position: relative;">
                    <div @click="toggleStatDropdown('room')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.room.length > 0 ? statFilters.room.join(', ') : 'Phòng ban (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'room' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'room'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.room" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'rm_'+opt" :value="opt" v-model="statFilters.room">
                            <label :for="'rm_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
                <div style="flex: 1.8; position: relative;">
                    <div @click="toggleStatDropdown('progress')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.progress.length > 0 ? statFilters.progress.join(', ') : 'Tiến độ (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'progress' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'progress'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.progress" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'pg_'+opt" :value="opt" v-model="statFilters.progress">
                            <label :for="'pg_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
                <div style="flex: 1.4; position: relative;">
                    <div @click="toggleStatDropdown('sla')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.sla.length > 0 ? statFilters.sla.join(', ') : 'Thời gian SLA (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'sla' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'sla'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.sla" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'sla_'+opt" :value="opt" v-model="statFilters.sla">
                            <label :for="'sla_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
                <div style="flex: 1.4; position: relative;">
                    <div @click="toggleStatDropdown('khung_gio')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.khung_gio.length > 0 ? statFilters.khung_gio.join(', ') : 'Khung giờ (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'khung_gio' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'khung_gio'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.khung_gio" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'kg_'+opt" :value="opt" v-model="statFilters.khung_gio">
                            <label :for="'kg_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
                <div style="flex: 1.4; position: relative;">
                    <div @click="toggleStatDropdown('tg_cho_gn')" class="table-input" style="cursor: pointer; background: #fff; min-height: 32px; display: flex; align-items: center; justify-content: space-between;">
                        <span class="truncate" style="font-size: 13px; font-weight: bold; color: #005993;">
                            {{ statFilters.tg_cho_gn.length > 0 ? statFilters.tg_cho_gn.join(', ') : 'TG Giải ngân (Tất cả)' }}
                        </span>
                        <span style="font-size: 10px;">{{ activeStatDropdown === 'tg_cho_gn' ? '▲' : '▼' }}</span>
                    </div>
                    <div v-if="activeStatDropdown === 'tg_cho_gn'" class="stat-dropdown">
                        <div v-for="opt in statFilterOptions.tg_cho_gn" :key="opt" class="stat-dropdown-item">
                            <input type="checkbox" :id="'gn_'+opt" :value="opt" v-model="statFilters.tg_cho_gn">
                            <label :for="'gn_'+opt">{{ opt }}</label>
                        </div>
                        <div class="stat-dropdown-footer" @click="activeStatDropdown = null">XONG</div>
                    </div>
                </div>
            </div>

            <div class="kb-scroll" style="flex-grow: 1; border: 1px solid #dce4ed; border-radius: 8px;">
                <table class="main-table">
                    <thead style="position: sticky; top: 0; z-index: 10;">
                        <tr>
                            <th style="width:3%;">STT</th>
                            <th style="width:6%;">Hoàn thành</th>
                            <th style="width:8%;">Phòng</th>
                            <th style="width:6%;">CIF</th>
                            <th style="width:23%;" class="text-left">Tên KH</th>
                            <th style="width:8%;">STK</th>
                            <th style="width:9%;" class="text-right">Số tiền GN</th>
                            <th style="width:8%;">CB HTTD</th>
                            <th style="width:8%;">LĐP/KSV</th>
                            <th style="width:12%;">Tiến độ</th>
                            <th style="width:9%;">Thời gian</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="(c, idx) in filteredStatCases" :key="c.case_key" class="clickable-row" @click="openCaseDetail(c)">
                            <td>{{ idx + 1 }}</td>
                            <td>{{ c.kanban_column === 'CLOSED' ? '✅' : '' }}</td>
                            <td class="no-wrap">{{ c.room_short }}</td>
                            <td>{{ c.cif }}</td>
                            <td class="text-left"><span class="truncate" :title="c.customer_name">{{ smartTruncate(c.customer_name, 50) }}</span></td>
                            <td>{{ c.stk }}</td>
                            <td class="text-right">{{ formatMoneyFull(c.amount, c.currency) }}</td>
                            <td><span class="truncate" :title="c.cb_id || c.cb_httd">{{ c.cb_id || c.cb_httd || '---' }}</span></td>
                            <td><span class="truncate" :title="c.ldp_ksv">{{ c.ldp_ksv || '---' }}</span></td>
                            <td><span class="truncate" :title="c.stage_label">{{ c.stage_label }}</span></td>
                            <td>
                                <span v-if="c.time_display === 'Đã xong' || c.time_display.startsWith('Sớm')" class="time-green">{{ c.time_display }}</span>
                                <span v-else-if="c.time_display.startsWith('+') || c.time_display.startsWith('Vượt')" class="time-red">{{ c.time_display }}</span>
                                <span v-else class="time-orange">{{ c.time_display }}</span>
                            </td>
                        </tr>
                        <tr v-if="filteredStatCases.length === 0"><td colspan="11" class="empty-state">Không có hồ sơ nào khớp điều kiện lọc.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <div v-if="showCaseDetail" class="modal-overlay" style="z-index: 10000;" @click.self="showCaseDetail = false">
        <div class="modal-content" style="width: 650px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                <h2 style="margin: 0; color: #005993;">Chi tiết Hồ sơ</h2>
                <button @click="showCaseDetail = false" style="background: none; border: none; font-size: 20px; cursor: pointer;">❌</button>
            </div>
            <div style="background-color: #e8f4f8; padding: 12px; border-radius: 8px; border-left: 5px solid #005993; margin-bottom: 20px;">
                <p style="margin: 0; font-weight: bold;">Mã HS: {{ selectedCase.case_key }}</p>
                <p style="margin: 0; font-size: 13px; color: #666;">Trạng thái hệ thống: {{ selectedCase.stage_code }} | CIF: {{ selectedCase.cif }}</p>
            </div>

            <div style="font-size: 13px; color: #d35400; margin-bottom: 15px; background: #fff3e0; padding: 10px; border-radius: 6px; border: 1px dashed #f39c12;">
                💡 Chỉnh sửa thông tin bên dưới và bấm nút 💾 để "Ghi đè" (Khóa dữ liệu).<br> Bấm nút 🔓 để "Mở khóa", hệ thống sẽ tự động cập nhật lại theo luồng máy tính.
            </div>

            <div v-if="selectedCase.kanban_column === 'PROCESSING' || selectedCase.kanban_column !== 'CLOSED' || selectedCase.has_manual_action" style="margin-bottom: 20px; padding: 15px; background: #fff5f5; border: 1px dashed #ed1c24; border-radius: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                    <h4 style="margin: 0; color: #ed1c24;">⚡ Chuyển trạng thái thẻ Kanban thủ công</h4>
                    <button v-if="selectedCase.has_manual_action" class="btn" style="background: white; border: 1px solid #c0392b; color: #c0392b; font-size: 11px; padding: 4px 8px; border-radius: 4px; font-weight: bold; cursor: pointer;" @click="undoManualAction">🔓 HỦY THỦ CÔNG</button>
                </div>
                <p style="font-size: 13px; margin-bottom: 10px; color: #666;">Dành cho các hồ sơ cần can thiệp bước hoặc luồng Thông thường/LC.</p>
                <div style="display: flex; gap: 10px;">
                    <input v-model="manualNote" type="text" class="table-input" placeholder="Ghi chú (Tùy chọn)..." style="flex: 2;">
                    <button v-if="selectedCase.kanban_column === 'PROCESSING'" class="btn btn-secondary" style="flex: 1; background: #f39c12; border-color: #f39c12; font-size: 12px; padding: 8px;" @click="doManualAction('MANUAL_WAIT_DISBURSE')">Chuyển sang Chờ GN</button>
                    <button v-if="selectedCase.kanban_column !== 'CLOSED'" class="btn btn-primary" style="flex: 1; background: #27ae60; border-color: #27ae60; font-size: 12px; padding: 8px;" @click="doManualAction('MANUAL_DONE')">Hoàn tất hồ sơ</button>
                </div>
            </div>

            <table style="width: 100%; box-shadow: none; border: 1px solid #dce4ed;">
                <tbody>
                    <tr>
                        <td style="width: 30%; font-weight: bold; background: #f8fafc;">Tên Khách hàng</td>
                        <td>
                            <div style="display: flex; gap: 5px;">
                                <input type="text" :value="selectedCase.customer_name" class="table-input" disabled style="background: #e2e8f0; color: #64748b;">
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; background: #f8fafc;">Số tài khoản</td>
                        <td>
                            <div style="display: flex; gap: 5px;">
                                <input type="text" :value="selectedCase.stk || ''" class="table-input" disabled style="background: #e2e8f0; color: #64748b;">
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; background: #f8fafc;">Số tiền GN</td>
                        <td>
                            <div style="display: flex; gap: 5px;">
                                <input type="text" :value="formatMoneyFull(selectedCase.amount, selectedCase.currency)" class="table-input" disabled style="background: #e2e8f0; color: #64748b;">
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; background: #f8fafc;">Phòng</td>
                        <td>
                            <div style="display: flex; gap: 5px;">
                                <input type="text" :value="selectedCase.room_short" class="table-input" disabled style="background: #e2e8f0; color: #64748b;">
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; background: #f8fafc;">Cán bộ HTTD</td>
                        <td>
                            <div style="display: flex; gap: 5px;">
                                <select v-model="editCaseData.cb_httd" class="table-input" :class="{ 'override-input': isOverridden('cb_httd') }">
                                    <option v-if="!readyOfficers.some(cb => String(cb.ID_CB || '').trim().toUpperCase() === String(resolveCaseOfficerId(selectedCase) || '').trim().toUpperCase())" :value="String(resolveCaseOfficerId(selectedCase) || '').trim()">{{ selectedCase.cb_id || selectedCase.cb_httd || 'Chưa phân công' }} (Hiện tại)</option>
                                    <option v-for="cb in readyOfficers" :key="cb.ID_CB" :value="String(cb.ID_CB || '').trim()">{{ cb.ID_CB }} - {{ cb['Tên Cán bộ'] }} {{ String(cb.ID_CB || '').trim().toUpperCase() === String(resolveCaseOfficerId(selectedCase) || '').trim().toUpperCase() ? '(Hiện tại)' : '' }}</option>
                                </select>
                                <button v-if="isOverridden('cb_httd') && String(editCaseData.cb_httd || '').trim().toUpperCase() === String(resolveCaseOfficerId(selectedCase) || '').trim().toUpperCase()" class="input-action-btn" title="Mở khóa" @click="removeOverride('cb_httd')">🔓</button>
                                <button v-else class="input-action-btn" title="Lưu phân giao thủ công" @click="saveOverride('cb_httd', editCaseData.cb_httd)">💾</button>
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; background: #f8fafc;">LĐP/KSV HTTD</td>
                        <td>
                            <div style="display: flex; gap: 5px;">
                                <input type="text" :value="selectedCase.ldp_ksv || ''" class="table-input" disabled style="background: #e2e8f0; color: #64748b;">
                            </div>
                        </td>
                    </tr>
                    <tr>
                        <td style="font-weight: bold; background: #f8fafc;">Tiến độ (Nhãn)</td>
                        <td>
                            <div style="display: flex; gap: 5px;">
                                <input type="text" :value="selectedCase.stage_label" class="table-input" disabled style="background: #e2e8f0; color: #64748b;">
                            </div>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
  </div>
</template>

<style scoped>
.input-action-btn { background: white; border: 1px solid #dce4ed; border-radius: 4px; padding: 4px 8px; cursor: pointer; font-size: 16px; }
.input-action-btn:hover { background: #f1f5f9; border-color: #005993; }

.table-input { width: 100%; padding: 6px; border: 1px solid #dce4ed; border-radius: 4px; background: #f8fafc; font-family: inherit; font-size: 14px; color: #005993; }
.table-input:focus { background: white; border-color: #005993; outline: none; }

.vcoms-container { height: calc(100vh - 20px); display: flex; flex-direction: column; overflow: hidden; background: linear-gradient(180deg, #eef8ff 0%, #def6ff 100%); margin: -10px; padding: 12px 14px 12px; }
.vcoms-header-shell { display: grid; grid-template-columns: minmax(220px, 245px) minmax(0, 1fr); gap: 12px; margin-bottom: 8px; overflow: hidden; }
.vcoms-header-shell.has-kpi-row { min-height: 151px; max-height: 151px; }
.vcoms-header-shell.compact-header { min-height: 68px; max-height: none; }
.vcoms-identity-panel { min-width: 0; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 4px; padding: 8px 10px 8px 42px; overflow: hidden; text-align: left; }
.vcoms-header-main { min-width: 0; display: grid; gap: 8px; }
.vcoms-header-main.has-kpi-row { grid-template-rows: 48px 95px; }
.vcoms-header-main.compact-header { grid-template-rows: 48px; }
.vcoms-topbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-width: 0; padding-right: 4px; }
.vcoms-brand-area { min-width: 0; display: flex; flex-direction: column; justify-content: center; align-items: flex-start; gap: 2px; overflow: hidden; }
.vcoms-brand-title { font-size: 28px; font-weight: 900; color: #c8102e; line-height: 1; letter-spacing: -0.45px; white-space: nowrap; }
.vcoms-brand-subtitle { font-size: 15px; font-weight: 700; color: #005993; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vcoms-tabs-area { display: flex; align-items: center; justify-content: flex-start; gap: 10px; min-width: 0; overflow: hidden; }
.vcoms-actions-area { display: flex; align-items: center; justify-content: flex-end; gap: 8px; min-width: 0; }
.vcoms-meta-pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; background: rgba(255,255,255,0.82); border: 1px solid #d8e4ef; color: #4b5563; font-size: 13px; box-shadow: 0 4px 10px rgba(15, 23, 42, 0.04); white-space: nowrap; }
.vcoms-date-badge { color: #0f4c81; font-weight: 700; border-color: #cfe1f1; box-shadow: 0 4px 10px rgba(0, 89, 147, 0.06); }
.vcoms-update-pill { position: relative; }
.vcoms-update-pill::before { content: ""; width: 7px; height: 7px; border-radius: 999px; background: #22c55e; box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.14); }

.tv-tab { background: rgba(255,255,255,0.86); border: 1px solid #d8e4ef; padding: 7px 14px; border-radius: 10px; font-size: 14px; font-weight: 700; color: #4b6480; cursor: pointer; transition: 0.2s; box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04); line-height: 1.1; }
.tv-tab:hover { background: #f8fbff; border-color: #b8d1e6; color: #005993; }
.tv-tab.active { background: linear-gradient(135deg, #005993, #0b6bb0); color: white; border-color: transparent; box-shadow: 0 6px 14px rgba(0,89,147,0.18); }

.vcoms-tab-pane { display: flex; flex-direction: column; flex-grow: 1; overflow: hidden; }
.vcoms-statistics-pane { flex: 1; min-height: 0; }
.vcoms-kpi-row { display: grid; grid-template-columns: minmax(0, 4fr) minmax(260px, 1.35fr); gap: 12px; height: 95px; max-height: 95px; overflow: hidden; }
.vcoms-kpi-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; height: 100%; min-width: 0; }
.kpi-card { height: 100%; min-height: 0; box-sizing: border-box; border: 1px solid rgba(226, 232, 240, 0.9); border-radius: 14px; box-shadow: 0 4px 12px rgba(0, 59, 115, 0.06); padding: 9px 12px; display: grid; grid-template-columns: 42px 1fr; align-items: center; gap: 10px; overflow: hidden; position: relative; }
.kpi-card::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; }
.kpi-icon { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 19px; flex-shrink: 0; background: #f8fafc; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.55); }
.kpi-content { min-width: 0; text-align: left; display: flex; flex-direction: column; justify-content: center; }
.kpi-title { font-size: 12.75px; font-weight: 800; line-height: 1.1; text-transform: uppercase; letter-spacing: 0.15px; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-val { font-size: 31px; font-weight: 900; line-height: 1; margin-top: 1px; }

.bg-total { background: linear-gradient(135deg, #e9f4ff 0%, #d7ebff 100%); }
.bg-open { background: linear-gradient(135deg, #fff4e4 0%, #ffe6c4 100%); }
.bg-closed { background: linear-gradient(135deg, #ebfaef 0%, #d7f2de 100%); }
.bg-rate { background: linear-gradient(135deg, #f3ecff 0%, #e3d6ff 100%); }

.bg-total::before { background: #005993; }
.bg-open::before { background: #f39c12; }
.bg-closed::before { background: #2e7d32; }
.bg-rate::before { background: #7c3aed; }

.bg-total .kpi-title,
.bg-total .kpi-val { color: #003B73; }
.bg-open .kpi-title,
.bg-open .kpi-val { color: #d97706; }
.bg-closed .kpi-title,
.bg-closed .kpi-val { color: #2e7d32; }
.bg-rate .kpi-title,
.bg-rate .kpi-val { color: #7c3aed; }

.bg-total .kpi-icon { background: #edf6ff; color: #005993; }
.bg-open .kpi-icon { background: #fff5e8; color: #d97706; }
.bg-closed .kpi-icon { background: #ecfdf3; color: #2e7d32; }
.bg-rate .kpi-icon { background: #f5efff; color: #7c3aed; }

.vcoms-officer-card { height: 100%; max-height: 95px; box-sizing: border-box; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px; box-shadow: 0 4px 12px rgba(0, 59, 115, 0.06); padding: 8px 12px; overflow: hidden; min-width: 0; display: flex; flex-direction: column; justify-content: center; gap: 5px; }
.vcoms-officer-row { display: grid; grid-template-columns: minmax(76px, 104px) minmax(72px, 84px) minmax(72px, 1fr); align-items: center; gap: 8px; height: 18px; cursor: pointer; min-width: 0; }
.vcoms-officer-name { font-size: 12px; font-weight: 800; color: #003B73; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vcoms-officer-status { font-size: 11px; font-weight: 700; color: #64748b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left; }
.vcoms-officer-progress { height: 8px; border-radius: 999px; overflow: hidden; background: #e2e8f0; display: flex; box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.06); max-width: 118px; width: 100%; }
.officer-progress-processing, .officer-progress-closed { display: flex; justify-content: center; align-items: center; color: white; font-size: 10px; font-weight: 800; }
.officer-progress-processing { background: linear-gradient(90deg, #f5a623, #f39c12); }
.officer-progress-closed { background: linear-gradient(90deg, #22a861, #27ae60); }

.kanban-board {
    display: grid;
    grid-template-columns: minmax(0, 58fr) minmax(360px, 42fr);
    grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
    gap: 15px;
    flex-grow: 1;
    min-height: 0;
    overflow: hidden;
    padding-bottom: 5px;
}

.kanban-col {
    background: #ffffff;
    border-radius: 12px;
    padding: 9px 13px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 0 5px 15px rgba(0, 89, 147, 0.08);
    min-width: 0;
    min-height: 0;
}

.col-open {
    grid-column: 1;
    grid-row: 1 / 3;
    border-top: 5px solid #005993;
}

.col-wait {
    grid-column: 2;
    grid-row: 1;
    border-top: 5px solid #f39c12;
}

.col-done {
    grid-column: 2;
    grid-row: 2;
    border-top: 5px solid #27ae60;
}

.kb-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
}

@media (max-width: 1180px) {
    .kanban-board {
        grid-template-columns: 1fr;
        grid-template-rows: auto auto auto;
        overflow-y: auto;
    }

    .col-open,
    .col-wait,
    .col-done {
        grid-column: 1;
        grid-row: auto;
        min-height: 260px;
    }
}

.kb-header { font-size: 17px; font-weight: 800; color: #005993; text-transform: uppercase; margin-bottom: 6px; display: flex; align-items: center; gap: 7px; }
.kb-title-sub { font-size: 14px; font-weight: 700; color: #d35400; text-transform: uppercase; margin-top: 4px; margin-bottom: 5px; background-color: #fff3e0; padding: 3px 9px; border-radius: 6px; display: inline-block; }

.kb-scroll { overflow-y: auto; padding-right: 2px; }
.kb-scroll::-webkit-scrollbar { width: 5px; }
.kb-scroll::-webkit-scrollbar-thumb { background-color: #cbd5e1; border-radius: 5px; }

.main-table, .sub-table { width: 100%; border-collapse: collapse; border-spacing: 0; font-size: 14px; table-layout: fixed; }
.main-table th, .sub-table th { background-color: #005993; color: #ffffff; font-weight: bold; padding: 6px 5px; text-align: center; font-size: 14px; line-height: 1.15; }
.main-table th:first-child, .sub-table th:first-child { border-top-left-radius: 6px; }
.main-table th:last-child, .sub-table th:last-child { border-top-right-radius: 6px; }

.main-table td, .sub-table td { padding: 6px 5px; border-bottom: 1px solid #edf2f7; text-align: center; font-weight: 500; color: #005993; line-height: 1.15; }
.main-table tr:nth-child(even), .sub-table tr:nth-child(even) { background-color: #f8fafc; }
.main-table tr:hover, .sub-table tr:hover { background-color: #e2e8f0; }

.text-left { text-align: left !important; }
.text-right { text-align: right !important; padding-right: 8px !important; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.no-wrap { white-space: nowrap; }
.clickable-row { cursor: pointer; transition: background-color 0.2s; }
.clickable-row:hover td { background-color: #cbd5e1 !important; }
.empty-state { text-align: center; color: #94a3b8 !important; font-style: italic; padding: 20px; }

/* Cảnh báo SLA */
.sla-green td { background-color: #d4edda !important; border-color: #c3e6cb !important; }
.sla-yellow td { background-color: #fff3cd !important; border-color: #ffe8a1 !important; }
.sla-orange td { background-color: #ffe8cc !important; border-color: #ffd199 !important; }
.sla-red td { background-color: #f8d7da !important; color: #a00000 !important; font-weight: bold; border-color: #f5c6cb !important; }
.row-wait-red td, .row-wait-red td span { color: #c0392b !important; font-weight: bold; }
.row-wait-yellow td, .row-wait-yellow td span { color: #f39c12 !important; font-weight: bold; }

.time-green { color: #27ae60 !important; }
.time-red { color: #c0392b !important; }
.time-orange { color: #f39c12 !important; }
.time-yellow { color: #d4ac0d !important; font-weight: bold; }
.sub-table th.gap-col, .sub-table td.gap-col { background-color: #ffffff !important; border-top: 1px solid #ffffff !important; border-bottom: 1px solid #ffffff !important; }
.sub-table tr:nth-child(even) td.gap-col, .sub-table tr:hover td.gap-col { background-color: #ffffff !important; }

.chart-bar-hover:hover { opacity: 0.8; }
.stat-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: white; border: 1px solid #005993; border-radius: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); z-index: 100; max-height: 250px; overflow-y: auto; margin-top: 2px; }
.stat-dropdown-item { padding: 6px 10px; border-bottom: 1px solid #f1f5f9; display: flex; align-items: center; gap: 8px; cursor: pointer; }
.stat-dropdown-item input[type="checkbox"] { cursor: pointer; width: 14px; height: 14px; accent-color: #005993; }
.stat-dropdown-item label { cursor: pointer; margin: 0; font-size: 13px; flex: 1; user-select: none; color: #333; }
.stat-dropdown-footer { padding: 8px; text-align: center; background: #f8fafc; position: sticky; bottom: 0; cursor: pointer; font-size: 12px; font-weight: bold; color: #005993; border-top: 1px solid #e2e8f0; }
.stat-dropdown-footer:hover { background: #e2e8f0; }
.override-input { background-color: #fff3cd !important; border-color: #ffe8a1 !important; color: #b71c1c !important; font-weight: bold; }
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.modal-content { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); overflow: hidden; }
.btn-primary { background: #005993; color: white; border: none; padding: 8px 15px; border-radius: 6px; cursor: pointer; font-weight: 600; }
.btn-success { background: #27ae60; color: white; border: none; padding: 8px 15px; border-radius: 6px; cursor: pointer; font-weight: 600; }
.btn-warning { background: #f39c12; color: white; border: none; padding: 8px 15px; border-radius: 6px; cursor: pointer; font-weight: 600; }
</style>
