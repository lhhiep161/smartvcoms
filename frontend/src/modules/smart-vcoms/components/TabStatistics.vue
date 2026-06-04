<script setup>
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart, FunnelChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components';
import VChart from 'vue-echarts';
import { useSmartVCOMS } from '../composables/useSmartVCOMS'

use([CanvasRenderer, BarChart, LineChart, FunnelChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent]);

const { fetchAPI, adminConfig, loadAdminConfig } = useSmartVCOMS()
const emit = defineEmits(['open-stat-detail'])

const statMode = ref('today')
const statYear = ref(new Date().getFullYear())
const statMonth = ref(null)
const statDay = ref(null)
const statRoom = ref('')
const statAvailableYears = ref([new Date().getFullYear()])
const isStatLoading = ref(false)
const statData = ref(null)

const loadStatistics = async () => {
    isStatLoading.value = true
    try {
        let url = `/api/vcoms/statistics?mode=${statMode.value}`
        if (statRoom.value) url += `&room=${encodeURIComponent(statRoom.value)}`
        if (statMode.value === 'custom') {
            if (statYear.value) url += `&year=${statYear.value}`
            if (statMonth.value) url += `&month=${statMonth.value}`
            if (statDay.value) url += `&day=${statDay.value}`
        }
        const res = await fetchAPI(url)
        if (res.status === 'success') {
            statData.value = res.data
            if (res.data.available_years && res.data.available_years.length > 0) {
                statAvailableYears.value = res.data.available_years
                if (!statAvailableYears.value.includes(statYear.value)) statYear.value = statAvailableYears.value[0]
            }
        }
    } catch (e) { console.error(e) } 
    finally { isStatLoading.value = false }
}

const chartPhongBan = computed(() => {
    if (!statData.value) return {};
    const data = statData.value.phong_ban;
    return {
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        legend: { data: ['Đã xong', 'Đang xử lý'], bottom: 0 },
        grid: { left: '3%', right: '4%', bottom: '15%', top: '5%', containLabel: true },
        xAxis: { type: 'category', data: data.map(d => d.phong), axisLabel: { interval: 0, rotate: 15 } },
        yAxis: { type: 'value' },
        series: [
            { name: 'Đã xong', type: 'bar', stack: 'total', data: data.map(d => d.closed), itemStyle: { color: '#005993' } },
            { name: 'Đang xử lý', type: 'bar', stack: 'total', data: data.map(d => d.open), itemStyle: { color: '#ed1c24' } }
        ]
    };
});

const chartPheu = computed(() => {
    if (!statData.value) return {};
    return {
        tooltip: { trigger: 'item', formatter: '{b}: {c}' },
        series: [{ type: 'funnel', left: '10%', top: '5%', bottom: '5%', width: '80%', sort: 'none', gap: 2, label: { show: true, position: 'inside', formatter: '{b}: {c}' }, itemStyle: { borderColor: '#fff', borderWidth: 1 }, data: statData.value.pheu.map(d => ({ name: d.stage, value: d.count })) }],
        color: ['#005993', '#3498db', '#f39c12', '#ed1c24']
    };
});

const chartKhungGio = computed(() => {
    if (!statData.value) return {};
    const data = statData.value.khung_gio;
    return { tooltip: { trigger: 'axis' }, grid: { left: '3%', right: '4%', bottom: '5%', top: '5%', containLabel: true }, xAxis: { type: 'category', boundaryGap: false, data: data.map(d => d.bucket) }, yAxis: { type: 'value' }, series: [{ name: 'Số lượng', type: 'line', areaStyle: { color: 'rgba(0, 89, 147, 0.2)' }, itemStyle: { color: '#005993' }, data: data.map(d => d.count), smooth: true }] };
});

const chartTGGiaiNgan = computed(() => {
    if (!statData.value) return {};
    const data = statData.value.tg_giai_ngan;
    return { tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } }, grid: { left: '3%', right: '4%', bottom: '5%', top: '5%', containLabel: true }, xAxis: { type: 'category', data: data.map(d => d.bucket) }, yAxis: { type: 'value' }, series: [{ name: 'Số lượng', type: 'bar', data: data.map(d => d.count), itemStyle: { color: function(params) { const colorList = ['#005993', '#3498db', '#f39c12', '#ed1c24', '#c0392b']; return colorList[params.dataIndex % colorList.length]; } }, label: { show: true, position: 'top' } }] };
});

const onChartClick = (type, params) => {
    if (!params || !params.name) return;
    let filters = {};
    if (type === 'room') filters.room = [params.name];
    else if (type === 'progress') filters.progress = [params.name];
    else if (type === 'khung_gio') filters.khung_gio = [params.name];
    else if (type === 'tg_cho_gn') filters.tg_cho_gn = [params.name];
    emit('open-stat-detail', filters);
}

onMounted(() => { 
    loadAdminConfig();
    loadStatistics();
})
</script>

<template>
    <div style="display: flex; flex-direction: column; height: 100%; overflow-y: auto; padding-right: 5px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; background: white; padding: 10px 15px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div style="display: flex; align-items: center; gap: 15px;">
                <h3 style="margin: 0; color: #005993; text-transform: uppercase;">📊 THỐNG KÊ HỒ SƠ GIẢI NGÂN</h3>
                <select v-model="statMode" @change="loadStatistics" class="table-input" style="width: 150px; font-weight: bold; border-radius: 4px; padding: 6px;"><option value="today">Hôm nay</option><option value="custom">Chuyên sâu</option></select>
                <select v-model="statRoom" @change="loadStatistics" class="table-input" style="width: 150px; font-weight: bold; border-radius: 4px; padding: 6px;"><option value="">Tất cả Phòng</option><option v-for="rm in adminConfig.room_config" :key="rm.room_name" :value="rm.display_name || rm.room_name">{{ rm.display_name || rm.room_name }}</option></select>
            </div>
            <div v-if="statMode === 'custom'" style="display: flex; gap: 10px;">
                <select v-model="statYear" @change="loadStatistics" class="table-input" style="width: 100px; border-radius: 4px; padding: 6px;"><option v-for="y in statAvailableYears" :key="y" :value="y">Năm {{y}}</option></select>
                <select v-model="statMonth" @change="loadStatistics" class="table-input" style="width: 120px; border-radius: 4px; padding: 6px;"><option :value="null">Tất cả tháng</option><option v-for="m in 12" :key="m" :value="m">Tháng {{m}}</option></select>
                <select v-model="statDay" @change="loadStatistics" class="table-input" style="width: 120px; border-radius: 4px; padding: 6px;"><option :value="null">Tất cả ngày</option><option v-for="d in 31" :key="d" :value="d">Ngày {{d}}</option></select>
            </div>
            <button class="btn btn-primary" @click="loadStatistics" style="padding: 6px 15px; background: #005993; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">🔄 LÀM MỚI</button>
        </div>
        <div v-if="isStatLoading" style="text-align: center; margin-top: 50px;"><h3 style="color: #005993;">Đang tải dữ liệu thống kê... ⏳</h3></div>
        <div v-else style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding-bottom: 20px;">
            <div style="background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 15px; border-top: 4px solid #005993;"><h4 style="text-align: center; color: #005993; margin-top: 0;">SỐ LƯỢNG HS THEO PHÒNG BAN</h4><v-chart class="chart" :option="chartPhongBan" autoresize style="height: 300px;" @click="onChartClick('room', $event)" /></div>
            <div style="background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 15px; border-top: 4px solid #005993;"><h4 style="text-align: center; color: #005993; margin-top: 0;">PHỄU TIẾN ĐỘ XỬ LÝ</h4><v-chart class="chart" :option="chartPheu" autoresize style="height: 300px;" @click="onChartClick('progress', $event)" /></div>
            <div style="background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 15px; border-top: 4px solid #005993;"><h4 style="text-align: center; color: #005993; margin-top: 0;">LƯU LƯỢNG HỒ SƠ ĐẾN (KHUNG GIỜ)</h4><v-chart class="chart" :option="chartKhungGio" autoresize style="height: 300px;" @click="onChartClick('khung_gio', $event)" /></div>
            <div style="background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 15px; border-top: 4px solid #005993;"><h4 style="text-align: center; color: #005993; margin-top: 0;">THỜI GIAN CHỜ GN (TỪ LÚC KÝ SỐ)</h4><v-chart class="chart" :option="chartTGGiaiNgan" autoresize style="height: 300px;" @click="onChartClick('tg_cho_gn', $event)" /></div>
        </div>
    </div>
</template>
