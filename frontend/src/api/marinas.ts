import api from './index'

export interface Marina {
  id: number
  name: string
  location: string | null
  timezone: string
  logo_url: string | null
  pedestal_api_base_url: string
  status: string
  created_at: string
  updated_at: string
}

export interface MarinaCreate {
  name: string
  location?: string
  timezone?: string
  pedestal_api_base_url: string
  pedestal_api_key: string
  webhook_secret?: string
  status?: string
}

export interface MarinaUpdate {
  name?: string
  location?: string
  timezone?: string
  logo_url?: string
  pedestal_api_base_url?: string
  pedestal_api_key?: string
  webhook_secret?: string
  status?: string
}

export const listMarinas = () =>
  api.get<Marina[]>('/marinas').then((r) => r.data)

export const getMarina = (id: number) =>
  api.get<Marina>(`/marinas/${id}`).then((r) => r.data)

export const createMarina = (data: MarinaCreate) =>
  api.post<Marina>('/marinas', data).then((r) => r.data)

export const updateMarina = (id: number, data: MarinaUpdate) =>
  api.patch<Marina>(`/marinas/${id}`, data).then((r) => r.data)

export const deleteMarina = (id: number) =>
  api.delete(`/marinas/${id}`)

export const grantAccess = (marinaId: number, userId: number) =>
  api.post(`/marinas/${marinaId}/access`, { user_id: userId, marina_id: marinaId })

export const revokeAccess = (marinaId: number, userId: number) =>
  api.delete(`/marinas/${marinaId}/access/${userId}`)
