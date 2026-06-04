<script setup>
import { computed } from 'vue'
import { useAuthStore } from '../app/stores/auth'
import logoBrand from '../assets/brand/logo/logo_brand.png'
import logoMark from '../assets/brand/logo/logo_mark.png'

const { currentUser, permissionSnapshot } = useAuthStore()

const modules = computed(() => {
    const items = []
    if (permissionSnapshot.value?.pages?.SmartVCOMS?.actions?.view) {
        items.push({
            title: 'SmartVCOMS',
            subtitle: 'Điều phối hồ sơ và giám sát SLA',
            route: '/smart-vcoms',
            accent: '#005993',
        })
    }
    if (currentUser.value?.isAdmin) {
        items.push({
            title: 'Portal Admin',
            subtitle: 'Khung quản trị user, đăng nhập và phân quyền cho SmartVCOMS',
            route: '/portal-admin',
            accent: '#0f172a',
        })
    }
    return items
})
</script>

<template>
    <div style="padding: 24px 28px 32px;">
        <div style="margin-bottom: 30px; border-radius: 24px; padding: 28px 30px; background: linear-gradient(135deg, #f7fbff 0%, #eef5ff 62%, #fff6f6 100%); border: 1px solid #dce4ed; box-shadow: 0 16px 34px rgba(0, 89, 147, 0.08);">
            <div style="display: flex; gap: 22px; align-items: center; flex-wrap: wrap;">
                <div style="width: 64px; height: 64px; border-radius: 18px; background: white; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 24px rgba(0, 89, 147, 0.12);">
                    <img :src="logoMark" alt="Portal CN9 Mark" style="width: 34px; height: 38px; object-fit: contain;" />
                </div>
                <div style="flex: 1 1 360px;">
                    <img :src="logoBrand" alt="Portal CN9 Logo" style="max-width: 250px; width: 100%; height: auto; object-fit: contain; margin-bottom: 10px;" />
                    <div class="portal-subtitle" style="margin-bottom: 0;">NỀN TẢNG VẬN HÀNH CÁC PHÂN HỆ NGHIỆP VỤ</div>
                </div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px;">
            <router-link
                v-for="module in modules"
                :key="module.route"
                :to="module.route"
                style="text-decoration: none;"
            >
                <div
                    style="height: 180px; border-radius: 18px; padding: 22px; color: white; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 18px 38px rgba(0, 0, 0, 0.12);"
                    :style="{ background: `linear-gradient(145deg, ${module.accent}, #0f172a)` }"
                >
                    <div style="font-size: 28px; font-weight: 900; letter-spacing: 0.02em;">{{ module.title }}</div>
                    <div style="font-size: 14px; line-height: 1.6; opacity: 0.92;">{{ module.subtitle }}</div>
                    <div style="font-size: 13px; font-weight: 700; text-transform: uppercase;">Mở phân hệ</div>
                </div>
            </router-link>
        </div>
    </div>
</template>
