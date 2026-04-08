import api from './index'

export interface PedestalInfo {
  id: number
  name: string
  location: string | null
  ip_address: string | null
  data_mode: string
  initialized: boolean
  mobile_enabled: boolean
}

export interface PedestalHealth {
  opta_connected: boolean
  last_heartbeat: string | null
  camera_reachable: boolean
  temp_sensor_reachable: boolean
}

export interface TemperatureReading {
  value: number
  alarm: boolean
  at: string | null
}

export interface SessionInfo {
  id: number
  pedestal_id: number
  type: string
  socket_id?: string
  started_at?: string
  status: string
}

export interface DashboardResponse {
  marina_id: number
  marina_name: string
  is_stale: boolean
  pedestals: PedestalInfo[]
  health: Record<string, PedestalHealth>
  active_sessions: SessionInfo[]
  pending_sessions: SessionInfo[]
  temperature_map: Record<string, TemperatureReading>
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
