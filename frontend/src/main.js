import { createApp } from 'vue'
import App from './app/AppShell.vue'
import router from './app/router'
import './assets/style.css'

const app = createApp(App)
app.use(router)
app.mount('#app')
