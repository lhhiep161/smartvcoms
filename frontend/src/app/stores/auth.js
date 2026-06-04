import { computed, ref } from 'vue'

const token = ref('')
const currentUser = ref({})
const permissionSnapshot = ref({ pages: {}, visible_pages: [] })
const isBootstrapped = ref(false)

function loadStoredSession() {
    token.value = localStorage.getItem('token') || ''
    try {
        currentUser.value = JSON.parse(localStorage.getItem('user') || '{}')
    } catch {
        currentUser.value = {}
    }
    try {
        permissionSnapshot.value = JSON.parse(localStorage.getItem('permission_snapshot') || '{"pages":{},"visible_pages":[]}')
    } catch {
        permissionSnapshot.value = { pages: {}, visible_pages: [] }
    }
}

function persistSession(nextToken, nextUser) {
    token.value = nextToken || ''
    currentUser.value = nextUser || {}
    if (token.value) {
        localStorage.setItem('token', token.value)
    } else {
        localStorage.removeItem('token')
    }
    if (nextUser && Object.keys(nextUser).length > 0) {
        localStorage.setItem('user', JSON.stringify(nextUser))
    } else {
        localStorage.removeItem('user')
    }
}

function persistPermissions(snapshot) {
    permissionSnapshot.value = snapshot || { pages: {}, visible_pages: [] }
    localStorage.setItem('permission_snapshot', JSON.stringify(permissionSnapshot.value))
}

function clearSession() {
    persistSession('', {})
    persistPermissions({ pages: {}, visible_pages: [] })
}

function bootstrapAuth() {
    if (!isBootstrapped.value) {
        loadStoredSession()
        isBootstrapped.value = true
    }
}

async function login(credentials) {
    const response = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
    })
    const result = await response.json()
    if (result.status === 'success') {
        persistSession(result.token, result.user)
        await loadPermissions()
    }
    return result
}

async function loadPermissions() {
    bootstrapAuth()
    if (!token.value) {
        persistPermissions({ pages: {}, visible_pages: [] })
        return { status: 'success', data: { pages: {}, visible_pages: [] } }
    }
    const response = await fetch('/api/permissions/me', {
        headers: {
            'Authorization': `Bearer ${token.value}`,
        },
    })
    if (response.status === 401) {
        redirectToLogin()
        throw new Error('Unauthorized')
    }
    const result = await response.json()
    if (result.status === 'success') {
        persistPermissions(result.data || { pages: {}, visible_pages: [] })
    }
    return result
}

async function logout() {
    bootstrapAuth()
    if (token.value) {
        try {
            await fetch('/api/logout', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token.value}`,
                },
            })
        } catch {
            // Logout should still clear local session even if backend is unreachable.
        }
    }
    clearSession()
}

const isAuthenticated = computed(() => !!token.value)

export function redirectToLogin() {
    clearSession()
    const redirect = `${window.location.pathname}${window.location.search}`
    window.location.href = `/login?redirect=${encodeURIComponent(redirect)}`
}

export function useAuthStore() {
    bootstrapAuth()
    return {
        token,
        currentUser,
        permissionSnapshot,
        isAuthenticated,
        isBootstrapped,
        bootstrapAuth,
        persistSession,
        persistPermissions,
        clearSession,
        login,
        loadPermissions,
        logout,
    }
}
