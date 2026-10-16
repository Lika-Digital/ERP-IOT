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

export interface SensorReadings {
  power_reading?: { watts: number; kwh_total: number; socket_id?: number; at: string }
  water_reading?: { lpm: number; total_liters: number; at: string }
  moisture_reading?: { value: number; alarm: boolean; at: string }
  temperature_reading?: { value: number; alarm: boolean; at: string }
  heartbeat?: { at: string }
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
  readings_map: Record<string, SensorReadings>
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

// Berths: see api/berths.ts (server-computed status, spec §3)

// ── D23 main dashboard (spec §6.6): one answer, everything decided on the server ──

export type CardState = 'fresh' | 'partial' | 'stale'
export type Simulated = 'none' | 'some' | 'all'

interface CardBase {
  title: string
  state: CardState
  sentence: string
  as_of: string | null
  simulated: Simulated
  href: string
}

export interface EnergyCard extends CardBase {
  key: 'energy'
  electricity_kwh: number
  water_m3: number | null
  delta_yesterday_pct: number | null
  delta_last_week_pct: number | null
  silent: number
  of: number
}

export interface SecurityCard extends CardBase {
  key: 'security'
  open: number
  open_simulated: number
  worst: 'critical' | 'warning' | 'info' | null
}

export interface OccupancyCard extends CardBase {
  key: 'occupancy'
  percent: number | null
  occupied: number
  known: number
  unknown: number
  not_connected: number
  reserved: number
  silent: number
}

export type OverviewCard = EnergyCard | SecurityCard | OccupancyCard

export interface MapBerth {
  berth_id: number
  number: string
  svg_id: string | null
  length_m: number | null
  cabinet: string | null
  simulated: boolean
  status_code: string
  status: string
  berth_colour: 'green' | 'blue' | 'yellow' | 'orange' | 'red' | 'grey' | 'none'
  status_sentence: string
  signals: { connection: string; vessel: string; power: string; reservation: string }
  alarm: { code: string; sentence: string }[]
  data_as_of: string | null
}

export interface OverviewCabinet {
  display_id: string
  simulated: boolean
  connection: 'ONLINE' | 'STALE' | 'OFFLINE'
  last_heartbeat_at: string | null
}

export interface OverviewResponse {
  marina_id: number
  marina_name: string
  map_svg: string | null
  generated_at: string
  cards: OverviewCard[]
  berths: MapBerth[]
  cabinets: OverviewCabinet[]
}

export const getOverview = (marinaId: number) =>
  api.get<OverviewResponse>(`/marinas/${marinaId}/overview`).then((r) => r.data)
