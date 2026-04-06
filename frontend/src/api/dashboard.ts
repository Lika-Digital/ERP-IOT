import api from './index'

export interface DashboardResponse {
  marina_id: number
  marina_name: string
  is_stale: boolean
  pedestals: unknown
  health: unknown
  active_sessions: unknown
  pending_sessions: unknown
}

export interface HealthResponse {
  marina_id: number
  is_stale: boolean
  data: unknown
}

export interface PedestalListResponse {
  marina_id: number
  is_stale: boolean
  pedestals: unknown
}

export const getDashboard = (marinaId: number) =>
  api.get<DashboardResponse>(`/marinas/${marinaId}/dashboard`).then((r) => r.data)

export const getMarinaHealth = (marinaId: number) =>
  api.get<HealthResponse>(`/marinas/${marinaId}/health`).then((r) => r.data)

export const listPedestals = (marinaId: number) =>
  api.get<PedestalListResponse>(`/marinas/${marinaId}/pedestals`).then((r) => r.data)

export const listBerths = (marinaId: number) =>
  api.get(`/marinas/${marinaId}/berths`).then((r) => r.data)
