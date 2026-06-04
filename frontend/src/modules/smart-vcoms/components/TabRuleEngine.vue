<script setup>
import { ref } from 'vue'
import { useSmartVCOMS } from '../composables/useSmartVCOMS'

const { ruleConfig, adminConfig, adminLoading, fetchAPI, loadRules } = useSmartVCOMS()
const isSavingRules = ref(false)

const getOfficerId = (cb) => String(cb?.ID_CB ?? cb?.id_cb ?? '').trim()
const getOfficerName = (cb) => String(cb?.['Tên Cán bộ'] ?? cb?.ten_can_bo ?? '').trim()

const saveRules = async () => {
    isSavingRules.value = true
    try {
        const res = await fetchAPI('/api/vcoms/admin/rules', {
            method: 'PUT',
            body: JSON.stringify(ruleConfig.value)
        })
        if (res.status === 'success') {
            alert('Đã lưu Cấu hình Rule Engine thành công!')
            loadRules()
        } else {
            alert('Lỗi: ' + res.message)
        }
    } catch(e) { console.error(e) }
    finally { isSavingRules.value = false }
}
</script>

<template>
    <div style="display: block; width: 100%; overflow-y: auto; padding-right: 5px; padding-bottom: 200px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <h3 style="color: #005993; margin: 0; text-transform: uppercase;">Bộ Quy Tắc Nhận Diện Và Phân Giao Luồng</h3>
            <button class="btn btn-secondary" @click="saveRules" :disabled="isSavingRules" style="background: #005993; color: white; border: none; padding: 8px 15px; border-radius: 6px; font-weight: bold; cursor: pointer;">
                {{ isSavingRules ? 'Đang lưu...' : '💾 LƯU BỘ QUY TẮC' }}
            </button>
        </div>
        
        <div style="display: flex; gap: 20px; align-items: flex-start;">
            <!-- Bảng Routing Rules -->
            <div style="flex: 1; display: flex; flex-direction: column; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: visible;">
                <div style="display: flex; justify-content: space-between; align-items: center; background: #e8f4f8; padding: 12px 15px; border-bottom: 2px solid #005993; border-radius: 8px 8px 0 0;">
                    <h4 style="margin: 0; color: #005993;">1. QUY TẮC NHẬN DIỆN LUỒNG (ROUTING)</h4>
                    <button class="btn btn-primary" style="background: #ed1c24; color: white; border: none; padding: 4px 10px; font-size: 12px; border-radius: 4px; cursor: pointer;" @click="ruleConfig.routing.push({keyword: '', flow_type: 'LUONG_THUONG', is_active: 1})">➕ THÊM TỪ KHÓA</button>
                </div>
                <div style="padding: 15px; overflow: visible;">
                    <table class="main-table">
                        <thead><tr><th>Từ khóa Subject</th><th>Loại Luồng</th><th>Tự động đóng tại</th><th style="width: 60px;">Active</th><th style="width: 40px;"></th></tr></thead>
                        <tbody>
                            <tr v-for="(rule, idx) in ruleConfig.routing" :key="'rt'+idx">
                                <td><input type="text" v-model="rule.keyword" class="table-input" placeholder="VD: lc, bảo lãnh, rút gọn..."></td>
                                <td>
                                    <select v-model="rule.flow_type" class="table-input">
                                        <option value="GN_ONLINE_KHDN">GN Online KHDN</option><option value="GN_ONLINE_KHCN">GN Online KHCN</option>
                                        <option value="GN_THONG_THUONG">GN Thông thường</option><option value="GN_SCAN">GN Scan</option>
                                        <option value="BAO_LANH">Luồng Bảo lãnh</option><option value="LC_ONLINE">Luồng LC Online</option>
                                    </select>
                                </td>
                                <td>
                                    <select v-model="rule.auto_close_at_stage" class="table-input">
                                        <option value="">-- Không --</option><option value="WAIT_SIGN">Sau khi Ký số</option>
                                        <option value="WAIT_MANUAL_DONE">Sau khi Phê duyệt</option>
                                    </select>
                                </td>
                                <td><input type="checkbox" v-model="rule.is_active" :true-value="1" :false-value="0"></td>
                                <td><button @click="ruleConfig.routing.splice(idx, 1)" class="input-action-btn" style="color:red; border:none;">🗑️</button></td>
                            </tr>
                            <tr v-if="ruleConfig.routing.length === 0"><td colspan="4" class="empty-state">Chưa có quy tắc nhận diện.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Bảng Assignment Rules -->
            <div style="flex: 1; display: flex; flex-direction: column; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: visible;">
                <div style="display: flex; justify-content: space-between; align-items: center; background: #e8f4f8; padding: 12px 15px; border-bottom: 2px solid #005993; border-radius: 8px 8px 0 0;">
                    <h4 style="margin: 0; color: #005993;">2. QUY TẮC PHÂN GIAO CB (ASSIGNMENT)</h4>
                    <button class="btn btn-primary" style="background: #ed1c24; color: white; border: none; padding: 4px 10px; font-size: 12px; border-radius: 4px; cursor: pointer;" @click="ruleConfig.assignment.push({flow_type: 'LUONG_THUONG', room_name: '', assigned_officers: '', is_active: 1})">➕ THÊM QUY TẮC</button>
                </div>
                <div style="padding: 15px; overflow: visible;">
                    <table class="main-table">
                        <thead><tr><th style="width: 25%;">Loại Luồng</th><th style="width: 30%;">Phòng Yêu cầu</th><th>Cán bộ chính (Mặc định)</th><th style="width: 60px;">Active</th><th style="width: 40px;"></th></tr></thead>
                        <tbody>
                            <tr v-for="(rule, idx) in ruleConfig.assignment" :key="'as'+idx">
                                <td>
                                    <select v-model="rule.flow_type" class="table-input">
                                        <option value="GN_ONLINE_KHDN">GN Online KHDN</option><option value="GN_ONLINE_KHCN">GN Online KHCN</option>
                                        <option value="GN_THONG_THUONG">GN Thông thường</option><option value="GN_SCAN">GN Scan</option>
                                        <option value="BAO_LANH">Luồng Bảo lãnh</option><option value="LC_ONLINE">Luồng LC Online</option>
                                    </select>
                                </td>
                                <td>
                                    <select v-model="rule.room_name" class="table-input">
                                        <option value="">-- Tất cả các phòng --</option>
                                        <option v-for="rm in adminConfig.room_config" :key="rm.room_name" :value="rm.room_name">{{ rm.room_name }}</option>
                                    </select>
                                </td>
                                <td>
                                    <select v-model="rule.assigned_officers" class="table-input" :disabled="adminLoading">
                                        <option value="">-- Chọn cán bộ --</option>
                                        <option
                                            v-if="!adminLoading && (!adminConfig.cb_config || adminConfig.cb_config.length === 0)"
                                            disabled
                                            value="__empty__"
                                        >
                                            Chưa tải được danh sách cán bộ
                                        </option>
                                        <option
                                            v-for="cb in adminConfig.cb_config"
                                            :key="getOfficerId(cb)"
                                            :value="getOfficerId(cb)"
                                        >
                                            {{ getOfficerId(cb) }} - {{ getOfficerName(cb) }}
                                        </option>
                                    </select>
                                </td>
                                <td><input type="checkbox" v-model="rule.is_active" :true-value="1" :false-value="0"></td>
                                <td><button @click="ruleConfig.assignment.splice(idx, 1)" class="input-action-btn" style="color:red; border:none; background: transparent;">🗑️</button></td>
                            </tr>
                            <tr v-if="ruleConfig.assignment.length === 0"><td colspan="5" class="empty-state">Chưa có quy tắc phân giao.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.input-action-btn { background: white; border: 1px solid #dce4ed; border-radius: 4px; padding: 4px 8px; cursor: pointer; font-size: 16px; }
.input-action-btn:hover { background: #f1f5f9; border-color: #005993; }
.table-input { width: 100%; padding: 6px; border: 1px solid #dce4ed; border-radius: 4px; background: #f8fafc; font-family: inherit; font-size: 14px; color: #005993; }
.table-input:focus { background: white; border-color: #005993; outline: none; }
.main-table { width: 100%; border-collapse: collapse; border-spacing: 0; font-size: 15px; table-layout: fixed; }
.main-table th { background-color: #005993; color: #ffffff; font-weight: bold; padding: 8px 6px; text-align: center; font-size: 15px; }
.main-table td { padding: 8px 6px; border-bottom: 1px solid #edf2f7; text-align: center; font-weight: 500; color: #005993; }
.main-table tr:nth-child(even) { background-color: #f8fafc; }
.main-table tr:hover { background-color: #e2e8f0; }
.empty-state { text-align: center; color: #94a3b8 !important; font-style: italic; padding: 20px; }
</style>
