import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const api = axios.create({ baseURL: '/api' })

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401: clear auth state and redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api

/**
 * The sentence the server attached to a refused cabinet command (spec §2.5):
 * standalone, no plug, busy, not enabled… Each outcome has its own sentence;
 * a generic "failed" would hide which one it was.
 */
export function cabinetSentence(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object' && 'sentence' in detail) {
    const s = (detail as { sentence?: unknown }).sentence
    if (typeof s === 'string' && s) return s
  }
  return fallback
}
