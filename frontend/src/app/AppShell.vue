<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'
import logoFull from '../assets/brand/logo/logo_full.png'
import logoMark from '../assets/brand/logo/logo_mark.png'

const router = useRouter()
const route = useRoute()

const isSidebarOpen = ref(true)

const { currentUser, permissionSnapshot, logout, loadPermissions } = useAuthStore()

const menuItems = computed(() => {
    const items = [{ route: '/', icon: '🏠', label: 'Trang chủ' }]
    if (permissionSnapshot.value?.pages?.SmartVCOMS?.actions?.view) {
        items.push({ route: '/smart-vcoms', icon: '💰', label: 'SmartVCOMS' })
    }
    if (permissionSnapshot.value?.pages?.PortalAdmin?.actions?.view) {
        items.push({ route: '/portal-admin', icon: '🛠️', label: 'Portal Admin' })
    }
    return items
})

const handleLogout = async () => {
    await logout()
    router.push('/login')
}

onMounted(() => {
    loadPermissions().catch(() => {})
})
</script>

<template>
  <div v-if="route.path === '/login'">
    <router-view></router-view>
  </div>
  
    <div v-else class="app-container">
    <div class="sidebar" :style="{ width: isSidebarOpen ? '250px' : '64px', padding: isSidebarOpen ? '20px' : '10px 6px', transition: 'width 0.3s ease, padding 0.3s ease', whiteSpace: 'nowrap', overflow: 'hidden', boxSizing: 'border-box' }">
        <div :style="{ textAlign: 'center', marginBottom: isSidebarOpen ? '30px' : '18px', padding: isSidebarOpen ? '10px 0' : '6px 0' }">
            <img v-if="isSidebarOpen" :src="logoFull" style="max-width: 100%; max-height: 74px; height: auto; object-fit: contain;" alt="Portal CN9 Logo" />
            <img v-else :src="logoMark" style="width: 32px; height: 32px; object-fit: contain;" alt="Portal CN9 Mark" />
        </div>
        <router-link
            v-for="item in menuItems"
            :key="item.route"
            :to="item.route"
            class="sidebar-menu-item"
            active-class="active"
            style="text-decoration: none; display: flex; align-items: center;"
            :style="{ justifyContent: isSidebarOpen ? 'flex-start' : 'center', padding: isSidebarOpen ? '12px 15px' : '10px', width: isSidebarOpen ? 'auto' : '44px', height: isSidebarOpen ? 'auto' : '44px', alignSelf: isSidebarOpen ? 'stretch' : 'center' }"
        >
            <span :style="{ fontSize: isSidebarOpen ? '20px' : '19px', lineHeight: 1 }">{{ item.icon }}</span><span v-if="isSidebarOpen" style="margin-left: 10px;">{{ item.label }}</span>
        </router-link>
        <div style="flex-grow: 1;"></div>
        <div class="sidebar-menu-item" style="color: #ed1c24; cursor: pointer; display: flex; align-items: center;" :style="{ justifyContent: isSidebarOpen ? 'flex-start' : 'center', padding: isSidebarOpen ? '12px 15px' : '10px', width: isSidebarOpen ? 'auto' : '44px', height: isSidebarOpen ? 'auto' : '44px', alignSelf: isSidebarOpen ? 'stretch' : 'center' }" @click="handleLogout">
            <span :style="{ fontSize: isSidebarOpen ? '20px' : '19px', lineHeight: 1 }">⏻</span><span v-if="isSidebarOpen" style="margin-left: 10px;">Đăng xuất</span>
        </div>
    </div>

    <div class="main-content" style="position: relative;" :style="{ padding: route.path === '/smart-vcoms' ? '10px' : '40px' }">
        <button @click="isSidebarOpen = !isSidebarOpen" style="position: absolute; top: 15px; left: 15px; z-index: 999; background: none; border: none; font-size: 24px; cursor: pointer; color: #005993;" title="Ẩn/Hiện Menu">
            ☰
        </button>

        <div v-if="route.path !== '/smart-vcoms'" style="position: absolute; top: 40px; right: 40px; z-index: 10;">
            <div style="color:#005993; font-weight:600; font-size: 14px; background: #f0f7ff; border: 1px solid #dce4ed; padding: 8px 16px; border-radius: 20px; box-shadow: 0 2px 5px rgba(0,89,147,0.1);">
                👋 Xin chào, {{ currentUser?.nameStr || 'User' }} {{ currentUser?.firstGroup ? '(' + currentUser.firstGroup + ')' : '' }}
            </div>
        </div>

        <router-view></router-view>
    </div>
  </div>
</template>
