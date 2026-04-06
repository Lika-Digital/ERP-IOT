import api from './index'

export interface AlarmLogEntry {
  id: number
  marina_id: number
  pedestal_id: number
  alarm_data: Record<string, unknown>
  received_at: string
  acknowledged_at: string | null
  acknowledged_by: number | null
}

export interface AlarmLogResponse {
  marina_id: number
  alarms: AlarmLogEntry[]
}

export interface ActiveAlarmsResponse {
  marina_id: number
  is_stale: boolean
  alarms: unknown
}

export const getActiveAlarms = (marinaId: number) =>
  api.get<ActiveAlarmsResponse>(`/marinas/${marinaId}/alarms/active`).then((r) => r.data)

export const getAlarmLog = (
  marinaId: number,
  params?: { limit?: number; pedestal_id?: number; unacknowledged_only?: boolean }
) =>
  api
    .get<AlarmLogResponse>(`/marinas/${marinaId}/alarms/log`, { params })
    .then((r) => r.data)

export const acknowledgeAlarm = (
  marinaId: number,
  alarmId: number,
  pedestalId?: number
) =>
  api
    .post(
      `/marinas/${marinaId}/alarms/${alarmId}/acknowledge`,
      undefined,
      pedestalId ? { params: { pedestal_id: pedestalId } } : undefined
    )
    .then((r) => r.data)
