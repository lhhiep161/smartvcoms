<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../app/stores/auth'
import logoFull from '../assets/brand/logo/logo_full.png'

const router = useRouter()
const route = useRoute()
const { login } = useAuthStore()
const loginForm = ref({ username: '', password: '' })
const isLoggingIn = ref(false)
const loginError = ref('')


const handleLogin = async () => {
    if (!loginForm.value.username) return;
    isLoggingIn.value = true;
    loginError.value = '';
    try {
        const result = await login(loginForm.value)
        if (result.status === 'success') {
            const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
            router.push(redirect)
        } else {
            loginError.value = result.message;
        }
    } catch (error) {
        loginError.value = "Lỗi kết nối đến máy chủ Backend!";
    } finally {
        isLoggingIn.value = false;
    }
}
</script>

<template>
    <div class="login-screen">
        <div class="login-wrapper">
            <div style="text-align: center; margin-bottom: 18px;">
                <img :src="logoFull" alt="Portal CN9 Logo" style="max-width: 240px; width: 100%; height: auto; object-fit: contain;" />
            </div>
            <div class="portal-title" style="text-align: center;">HỆ THỐNG QUẢN TRỊ</div>
            <div class="portal-subtitle" style="text-align: center;">VIETINBANK CHI NHÁNH 9</div>
            
            <div v-if="loginError" class="alert-error">{{ loginError }}</div>
            
            <div class="form-group"><label>Tên đăng nhập</label><input type="text" v-model="loginForm.username" placeholder="Nhập username hoặc mã đăng nhập..." @keyup.enter="handleLogin"></div>
            <div class="form-group"><label>Mật khẩu</label><input type="password" v-model="loginForm.password" placeholder="Nhập mật khẩu..." @keyup.enter="handleLogin"></div>
            
            <button class="btn btn-primary btn-full" @click="handleLogin" :disabled="isLoggingIn">{{ isLoggingIn ? 'ĐANG XỬ LÝ...' : 'ĐĂNG NHẬP' }}</button>
        </div>
    </div>
</template>
