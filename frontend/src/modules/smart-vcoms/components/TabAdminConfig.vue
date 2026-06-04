<script setup>
import { ref } from 'vue'
import { useSmartVCOMS } from '../composables/useSmartVCOMS'

const { adminConfig, adminLoading, fetchAPI, loadAdminConfig } = useSmartVCOMS()

const isSavingAdmin = ref(false)
const adminValidStatuses = ["Ready", "Biztrip", "Off"]

const saveAdminCbConfig = async () => {
    isSavingAdmin.value = true
    try {
        const payload = { rows: adminConfig.value.cb_config }
        const res = await fetchAPI('/api/vcoms/admin/config/cb', { method: 'PUT', body: JSON.stringify(payload) })
        if (res.status === 'success') { 
            alert(res.message);
            await loadAdminConfig();
        } 
        else { alert('Lỗi: ' + res.message) }
    } catch(e) { console.error(e) }
    finally { isSavingAdmin.value = false }
}

const saveAdminRoomConfig = async () => {
    isSavingAdmin.value = true
    try {
        const payload = { rows: adminConfig.value.room_config }
        const res = await fetchAPI('/api/vcoms/admin/config/room', { method: 'PUT', body: JSON.stringify(payload) })
        if (res.status === 'success') { alert('Lưu cấu hình Phòng ban thành công!') } 
        else { alert('Lỗi: ' + res.message) }
    } catch(e) { console.error(e) }
    finally { isSavingAdmin.value = false }
}

const saveAdminLdConfig = async () => {
    isSavingAdmin.value = true
    try {
        const payload = { rows: adminConfig.value.ld_config }
        const res = await fetchAPI('/api/vcoms/admin/config/ld', { method: 'PUT', body: JSON.stringify(payload) })
        if (res.status === 'success') { alert('Lưu cấu hình LĐP/KSV thành công!') } 
        else { alert('Lỗi: ' + res.message) }
    } catch(e) { console.error(e) }
    finally { isSavingAdmin.value = false }
}

const saveAdminSlaConfig = async () => {
    isSavingAdmin.value = true
    try {
        const payload = { rows: adminConfig.value.sla_config }
        const res = await fetchAPI('/api/vcoms/admin/config/sla', { method: 'PUT', body: JSON.stringify(payload) })
        if (res.status === 'success') { alert('Lưu cấu hình SLA thành công!') } 
        else { alert('Lỗi: ' + res.message) }
    } catch(e) { console.error(e) }
    finally { isSavingAdmin.value = false }
}
</script>

<template>
    <div style="display: block; width: 100%; overflow-y: auto; padding-right: 5px; padding-bottom: 20px;">
        <div v-if="adminLoading" style="text-align: center;">
            <h2 style="color: #666;">Đang tải dữ liệu cấu hình...</h2>
        </div>
        <div v-else style="width: 100%;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <h3 style="color: #005993; margin: 0;">BẢNG THÔNG TIN CÁN BỘ</h3>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-primary" style="padding: 4px 10px; font-size: 12px; background: #ed1c24; color: white; border: none; border-radius: 4px; cursor: pointer;" @click="adminConfig.cb_config.push({'ID_CB': '', 'Tên Cán bộ': '', 'Trạng thái': 'Ready', 'Tổng phút SLA': 0, 'Phút Bù Trừ': 0, 'Điểm Phân Giao': 0, 'is_active': 1})">➕ THÊM CÁN BỘ</button>
                    <button class="btn btn-secondary" @click="saveAdminCbConfig" :disabled="isSavingAdmin" style="background: #005993; color: white; border: none; padding: 4px 15px; border-radius: 4px; font-weight: bold; cursor: pointer;">
                        {{ isSavingAdmin ? 'Đang lưu...' : '💾 LƯU BẢNG CÁN BỘ' }}
                    </button>
                </div>
            </div>
            <div class="kb-scroll" style="max-height: 40vh; margin-bottom: 20px;">
                <table class="main-table">
                    <thead><tr><th>ID_CB</th><th class="text-left">Tên Cán bộ</th><th>Trạng thái</th><th style="width: 90px;" title="Tổng SLA các hồ sơ đang ôm">Tổng SLA</th><th style="width: 90px;">Phút Bù Trừ</th><th style="width: 110px;" title="Tổng SLA + Bù Trừ">Điểm phân giao</th><th>Active</th><th style="width: 50px;"></th></tr></thead>
                    <tbody>
                        <tr v-for="(cb, idx) in adminConfig.cb_config" :key="'cb'+idx">
                            <td><input type="text" v-model="cb.ID_CB" class="table-input" /></td>
                            <td class="text-left"><input type="text" v-model="cb['Tên Cán bộ']" class="table-input" /></td>
                            <td><select v-model="cb['Trạng thái']" class="table-input"><option v-for="s in adminValidStatuses" :key="s" :value="s">{{ s }}</option></select></td>
                            <td><input type="text" :value="cb['Tổng phút SLA'] || 0" class="table-input" disabled style="background: #e2e8f0; color: #64748b; text-align: center;" /></td>
                            <td><input type="number" v-model="cb['Phút Bù Trừ']" class="table-input" /></td>
                            <td><input type="text" :value="cb['Điểm Phân Giao'] || 0" class="table-input" disabled style="background: #e2e8f0; color: #64748b; text-align: center; font-weight: bold;" /></td>
                            <td><input type="checkbox" v-model="cb.is_active" :true-value="1" :false-value="0" /></td>
                            <td><button @click="adminConfig.cb_config.splice(idx, 1)" class="input-action-btn" style="color:red; border:none; background: transparent; cursor: pointer;">🗑️</button></td>
                        </tr>
                        <tr v-if="adminConfig.cb_config.length === 0"><td colspan="8" class="empty-state">Chưa có cán bộ. Bấm ➕ Thêm Cán Bộ để tạo mới.</td></tr>
                    </tbody>
                </table>
            </div>
            
            <div style="display: flex; gap: 15px; align-items: flex-start;">
                <!-- CỘT 1: PHÒNG BAN -->
                <div style="flex: 1; min-width: 250px; display: flex; flex-direction: column; overflow: hidden; background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <h3 style="color: #005993; margin: 0; font-size: 14px;">CẤU HÌNH PHÒNG BAN</h3>
                        <div style="display: flex; gap: 5px;">
                            <button class="btn btn-primary" style="padding: 4px 8px; font-size: 11px; background: #ed1c24; color: white; border: none; border-radius: 4px; cursor: pointer;" @click="adminConfig.room_config.push({room_name: '', is_restricted: 1})">➕ THÊM</button>
                            <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px; background: #005993; color: white; border: none; border-radius: 4px; cursor: pointer;" @click="saveAdminRoomConfig" :disabled="isSavingAdmin">{{ isSavingAdmin ? '...' : '💾 LƯU' }}</button>
                        </div>
                    </div>
                    <div class="kb-scroll" style="max-height: 40vh; margin-bottom: 5px; overflow-x: auto;">
                        <table class="main-table">
                            <thead><tr><th class="text-left">Tên Phòng Ban</th><th style="width: 90px;">Tên viết tắt</th><th style="width: 70px;">Giới hạn</th><th style="width: 40px;"></th></tr></thead>
                            <tbody>
                                <tr v-for="(rm, idx) in adminConfig.room_config" :key="'rm'+idx">
                                    <td class="text-left"><input type="text" v-model="rm.room_name" class="table-input"></td>
                                    <td><input type="text" v-model="rm.display_name" class="table-input"></td>
                                    <td><input type="checkbox" v-model="rm.is_restricted" :true-value="1" :false-value="0"></td>
                                    <td><button @click="adminConfig.room_config.splice(idx, 1)" class="input-action-btn" style="color:red; border:none; background: transparent; cursor: pointer;">🗑️</button></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- CỘT 2: LĐP / KSV -->
                <div style="flex: 1.6; min-width: 450px; display: flex; flex-direction: column; overflow: hidden; background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <h3 style="color: #005993; margin: 0; font-size: 14px;">CẤU HÌNH LĐP / KSV</h3>
                        <div style="display: flex; gap: 5px;">
                            <button class="btn btn-primary" style="padding: 4px 8px; font-size: 11px; background: #ed1c24; color: white; border: none; border-radius: 4px; cursor: pointer;" @click="adminConfig.ld_config.push({display_name: '', lookup_key: '', email: '', sort_order: 1, is_active: 1})">➕ THÊM</button>
                            <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px; background: #005993; color: white; border: none; border-radius: 4px; cursor: pointer;" @click="saveAdminLdConfig" :disabled="isSavingAdmin">{{ isSavingAdmin ? '...' : '💾 LƯU' }}</button>
                        </div>
                    </div>
                    <div class="kb-scroll" style="max-height: 40vh; margin-bottom: 5px; overflow-x: auto;">
                        <table class="main-table" style="min-width: 430px;">
                            <thead><tr><th class="text-left">Tên hiển thị</th><th>Mã tra cứu</th><th>Email</th><th style="width: 50px;">Sắp xếp</th><th style="width: 50px;">Active</th><th style="width: 40px;"></th></tr></thead>
                            <tbody>
                                <tr v-for="(ld, idx) in adminConfig.ld_config" :key="'ld'+idx">
                                    <td class="text-left"><input type="text" v-model="ld.display_name" class="table-input"></td>
                                    <td><input type="text" v-model="ld.lookup_key" class="table-input"></td>
                                    <td><input type="text" v-model="ld.email" class="table-input"></td>
                                    <td><input type="number" v-model="ld.sort_order" class="table-input" style="padding: 4px;"></td>
                                    <td><input type="checkbox" v-model="ld.is_active" :true-value="1" :false-value="0"></td>
                                    <td><button @click="adminConfig.ld_config.splice(idx, 1)" class="input-action-btn" style="color:red; border:none; background: transparent; cursor: pointer;">🗑️</button></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- CỘT 3: CẤU HÌNH SLA -->
                <div style="flex: 1; min-width: 250px; display: flex; flex-direction: column; overflow: hidden; background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <h3 style="color: #005993; margin: 0; font-size: 14px;">PHÂN BỔ SLA</h3>
                        <div style="display: flex; gap: 5px;">
                            <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 11px; background: #005993; color: white; border: none; border-radius: 4px; cursor: pointer;" @click="saveAdminSlaConfig" :disabled="isSavingAdmin">{{ isSavingAdmin ? '...' : '💾 LƯU' }}</button>
                        </div>
                    </div>
                    <div class="kb-scroll" style="max-height: 40vh; margin-bottom: 5px; overflow-x: auto;">
                        <table class="main-table">
                            <thead><tr><th class="text-left">Tiêu chí</th><th style="width: 70px;">Giá trị</th></tr></thead>
                            <tbody>
                                <tr v-for="(sla, idx) in adminConfig.sla_config" :key="'sla'+idx">
                                    <td class="text-left"><input type="text" v-model="sla['Tiêu chí']" class="table-input" style="font-size: 12px; padding: 4px;"></td>
                                    <td><input type="text" v-model="sla['Giá trị']" class="table-input" style="text-align: center; font-size: 12px; padding: 4px;"></td>
                                </tr>
                                <tr v-if="adminConfig.sla_config.length === 0">
                                    <td colspan="2" class="empty-state">Chưa tải được cấu hình SLA mặc định.</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>
