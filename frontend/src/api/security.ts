import api from './index'

/** Security screen (spec §6.5, D21) — Admin only. The agent opens alarms; an Admin decides. */

export type Severity = 'info' | 'warning' | 'critical'
export type AlarmState = 'open' | 'acknowledged' | 'closed'
export type RuleModeName = 'shadow' | 'active'

export interface Evidence {
  source: string
  row_ids: number[]
  fields: Record<string, unknown>
  observed_at: string | null
}

export interface SecurityAlarm {
  id: number
  rule_id: string
  severity: Severity
  title: string
  why: string
  evidence: Evidence[]
  window_from: string | null
  window_to: string | null
  created_at: string
  state: AlarmState
  decided_by: number | null
  decided_at: string | null
  decision_note: string | null
}

export interface SecurityRule {
  rule_id: string
  severity: Severity
  describe: string
  mode: RuleModeName
  decided_by: number | null
  decided_at: string | null
}

export interface ServiceWindow {
  id: number
  cabinet_id: number
  display_id: string
  from_at: string
  to_at: string
  announced_by: string
  note: string | null
  created_by: number | null
  created_at: string
}

export interface CabinetRef {
  id: number
  display_id: string
}

export const listAlarms = (state?: AlarmState) =>
  api.get<SecurityAlarm[]>('/security/alarms', { params: state ? { state } : {} }).then((r) => r.data)

export const decideAlarm = (id: number, state: 'acknowledged' | 'closed', note: string) =>
  api.patch<SecurityAlarm>(`/security/alarms/${id}`, { state, note }).then((r) => r.data)

export const listRules = () => api.get<SecurityRule[]>('/security/rules').then((r) => r.data)

export const setRuleMode = (ruleId: string, mode: RuleModeName) =>
  api.put<SecurityRule>(`/security/rules/${ruleId}`, { mode }).then((r) => r.data)

export const listWindows = () =>
  api.get<ServiceWindow[]>('/security/service-windows').then((r) => r.data)

/** Times go out with their zone (toISOString is UTC, 'Z'); the server stores naive UTC. */
export const announceWindow = (body: {
  cabinet_id: number
  from_at: string
  to_at: string
  announced_by: string
  note?: string | null
}) => api.post<ServiceWindow>('/security/service-windows', body).then((r) => r.data)

export const cancelWindow = (id: number) => api.delete(`/security/service-windows/${id}`)

export const listCabinets = (marinaId: number) =>
  api.get<{ cabinets: CabinetRef[] }>(`/marinas/${marinaId}/cabinets`).then((r) => r.data.cabinets)
