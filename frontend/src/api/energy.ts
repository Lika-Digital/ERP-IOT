import api from './index'

export interface DailyAnalytics {
  date: string
  energy_kwh: number
  water_liters: number
  session_count: number
}

export interface SessionSummary {
  total_sessions: number
  by_status: Record<string, number>
  total_energy_kwh: number
  total_water_liters: number
  completed_sessions: number
}

export interface EnergyResponse<T> {
  marina_id: number
  is_stale: boolean
  data: T
}

export interface SessionsResponse {
  marina_id: number
  is_stale: boolean
  sessions: unknown[]
}

export const getDailyAnalytics = (
  marinaId: number,
  dateFrom?: string,
  dateTo?: string
) =>
  api
    .get<EnergyResponse<DailyAnalytics[]>>(`/marinas/${marinaId}/energy/daily`, {
      params: { date_from: dateFrom, date_to: dateTo },
    })
    .then((r) => r.data)

export const getSessionSummary = (marinaId: number) =>
  api
    .get<EnergyResponse<SessionSummary>>(`/marinas/${marinaId}/energy/summary`)
    .then((r) => r.data)

export const getActiveSessions = (marinaId: number) =>
  api.get<SessionsResponse>(`/marinas/${marinaId}/sessions/active`).then((r) => r.data)

export const getPendingSessions = (marinaId: number) =>
  api.get<SessionsResponse>(`/marinas/${marinaId}/sessions/pending`).then((r) => r.data)
