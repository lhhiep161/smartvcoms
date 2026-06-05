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
    <div class="statistics-root">
        <div class="stats-toolbar">
            <div class="stats-toolbar-title">📊 THỐNG KÊ HỒ SƠ GIẢI NGÂN</div>
            <div class="stats-filter-group">
                <div class="stats-segmented">
                    <button
                        :class="['stats-segment-btn', statMode === 'today' ? 'active' : '']"
                        @click="statMode = 'today'; loadStatistics()"
                    >
                        Hôm nay
                    </button>
                    <button
                        :class="['stats-segment-btn', statMode === 'custom' ? 'active' : '']"
                        @click="statMode = 'custom'; loadStatistics()"
                    >
                        Chuyên sâu
                    </button>
                </div>
                <select v-model="statRoom" @change="loadStatistics" class="table-input stats-filter-select stats-filter-room"><option value="">Tất cả Phòng</option><option v-for="rm in adminConfig.room_config" :key="rm.room_name" :value="rm.display_name || rm.room_name">{{ rm.display_name || rm.room_name }}</option></select>
            </div>
            <div class="stats-toolbar-right">
                <div v-if="statMode === 'custom'" class="stats-filter-group stats-advanced-filters">
                    <select v-model="statYear" @change="loadStatistics" class="table-input stats-filter-select stats-filter-year"><option v-for="y in statAvailableYears" :key="y" :value="y">Năm {{y}}</option></select>
                    <select v-model="statMonth" @change="loadStatistics" class="table-input stats-filter-select stats-filter-month"><option :value="null">Tất cả tháng</option><option v-for="m in 12" :key="m" :value="m">Tháng {{m}}</option></select>
                    <select v-model="statDay" @change="loadStatistics" class="table-input stats-filter-select stats-filter-day"><option :value="null">Tất cả ngày</option><option v-for="d in 31" :key="d" :value="d">Ngày {{d}}</option></select>
                </div>
                <button class="stats-refresh-btn" @click="loadStatistics">🔄 LÀM MỚI</button>
            </div>
        </div>
        <div v-if="isStatLoading" style="text-align: center; margin-top: 50px;"><h3 style="color: #005993;">Đang tải dữ liệu thống kê... ⏳</h3></div>
        <div v-else class="statistics-grid">
            <div class="statistics-chart-card"><h4 class="statistics-chart-title">SỐ LƯỢNG HS THEO PHÒNG BAN</h4><v-chart class="chart" :option="chartPhongBan" autoresize style="height: 300px;" @click="onChartClick('room', $event)" /></div>
            <div class="statistics-chart-card"><h4 class="statistics-chart-title">PHỄU TIẾN ĐỘ XỬ LÝ</h4><v-chart class="chart" :option="chartPheu" autoresize style="height: 300px;" @click="onChartClick('progress', $event)" /></div>
            <div class="statistics-chart-card"><h4 class="statistics-chart-title">LƯU LƯỢNG HỒ SƠ ĐẾN (KHUNG GIỜ)</h4><v-chart class="chart" :option="chartKhungGio" autoresize style="height: 300px;" @click="onChartClick('khung_gio', $event)" /></div>
            <div class="statistics-chart-card"><h4 class="statistics-chart-title">THỜI GIAN CHỜ GN (TỪ LÚC KÝ SỐ)</h4><v-chart class="chart" :option="chartTGGiaiNgan" autoresize style="height: 300px;" @click="onChartClick('tg_cho_gn', $event)" /></div>
        </div>
    </div>
</template>

<style scoped>
.statistics-root { display: flex; flex-direction: column; height: 100%; overflow-y: auto; padding-right: 5px; }
.stats-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; min-height: 46px; background: rgba(255,255,255,0.96); padding: 6px 12px; border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }
.stats-toolbar-title { margin: 0; color: #005993; text-transform: uppercase; font-size: 17px; font-weight: 800; line-height: 1.1; white-space: nowrap; }
.stats-filter-group, .stats-toolbar-right { display: flex; align-items: center; gap: 10px; min-width: 0; }
.stats-filter-group { flex: 1; }
.stats-toolbar-right { flex-shrink: 0; }
.stats-segmented { display: inline-flex; align-items: center; padding: 2px; border-radius: 10px; background: #eaf3fb; border: 1px solid #d2e3f0; box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.05); }
.stats-segment-btn { min-width: 104px; height: 34px; padding: 0 14px; border: none; border-radius: 8px; background: transparent; color: #0f4c81; font-size: 13px; font-weight: 800; cursor: pointer; transition: 0.18s ease; }
.stats-segment-btn.active { background: linear-gradient(135deg, #005993, #0b6bb0); color: #ffffff; box-shadow: 0 3px 8px rgba(0, 89, 147, 0.18); }
.stats-filter-select { height: 36px; font-weight: 700; border-radius: 9px; padding: 0 10px; background: #ffffff; border: 1px solid #d8e4ef; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04); color: #005993; }
.stats-filter-room { width: 154px; }
.stats-filter-year { width: 100px; }
.stats-filter-month, .stats-filter-day { width: 118px; }
.stats-refresh-btn { height: 36px; padding: 0 15px; background: linear-gradient(135deg, #005993, #0b6bb0); color: white; border: none; border-radius: 9px; font-weight: 800; cursor: pointer; white-space: nowrap; box-shadow: 0 3px 8px rgba(0, 89, 147, 0.18); }
.statistics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding-bottom: 20px; }
.statistics-chart-card { background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 15px; border-top: 4px solid #005993; }
.statistics-chart-title { text-align: center; color: #005993; margin-top: 0; }

@media (max-width: 1280px) {
  .stats-toolbar { flex-wrap: wrap; }
  .stats-filter-group { flex-wrap: wrap; }
  .stats-toolbar-right { width: 100%; justify-content: flex-end; }
}
</style>
