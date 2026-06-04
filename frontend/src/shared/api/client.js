import { redirectToLogin, useAuthStore } from '../../app/stores/auth'

export async function apiFetch(url, options = {}) {
    const { token, bootstrapAuth } = useAuthStore()
    bootstrapAuth()
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
    const response = await fetch(url, {
        ...options,
        headers: {
            'Authorization': token.value ? `Bearer ${token.value}` : '',
            ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
            ...(options.headers || {}),
        },
    })
    if (response.status === 401) {
        redirectToLogin()
        throw new Error('Unauthorized')
    }
    return response
}

export async function apiFetchJSON(url, options = {}) {
    const response = await apiFetch(url, options)
    return response.json()
}
