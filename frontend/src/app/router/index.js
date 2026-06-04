import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import HomeView from '../../views/HomeView.vue'
import LoginView from '../../views/LoginView.vue'
import PortalAdminView from '../../modules/portal-admin/pages/PortalAdminPage.vue'
import SmartVCOMSView from '../../modules/smart-vcoms/pages/SmartVCOMSPage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { requiresAuth: true }
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView
    },
    {
      path: '/portal-admin',
      name: 'portal-admin',
      component: PortalAdminView,
      meta: { requiresAuth: true }
    },
    {
      path: '/smart-vcoms',
      name: 'smart-vcoms',
      component: SmartVCOMSView,
      meta: { requiresAuth: true }
    }
  ]
})

router.beforeEach(async (to) => {
  const { isAuthenticated, bootstrapAuth, loadPermissions, permissionSnapshot, currentUser } = useAuthStore()
  bootstrapAuth()

  if (to.name === 'login' && isAuthenticated.value) {
    const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : '/'
    return redirect
  }

  if (to.meta.requiresAuth && !isAuthenticated.value) {
    return {
      name: 'login',
      query: { redirect: to.fullPath },
    }
  }

  if (to.meta.requiresAuth && isAuthenticated.value) {
    await loadPermissions()

    const routePermissionMap = {
      'smart-vcoms': 'SmartVCOMS',
    }
    const pageId = routePermissionMap[to.name]
    if (pageId) {
      const canView = Boolean(permissionSnapshot.value?.pages?.[pageId]?.actions?.view)
      if (!canView) {
        return '/'
      }
    }

    if (to.name === 'portal-admin' && !permissionSnapshot.value?.pages?.PortalAdmin?.actions?.view) {
      return '/'
    }
  }

  return true
})

export default router
