import api from './index'

// Every operator command carries a reason: it is written to command_audit before the
// command is sent, and the server refuses a command without one (spec §5.3).
// Asked in a real dialog since D20 (O38), not window.prompt.
export { askReason } from '../components/ui/ReasonDialog'

export const NO_REASON = 'Command not sent — a reason is required (at least 3 characters).'

// P4 (spec §6.13): a command names its cabinet by the ERP's id — the cabinets of one
// marina can share a pedestal number, and the server refuses what it cannot place.
const target = (pedestalId?: number, cabinetId?: number) => ({
  params: {
    ...(pedestalId ? { pedestal_id: pedestalId } : {}),
    ...(cabinetId ? { cabinet: cabinetId } : {}),
  },
})

/** A cabinet as the ERP records it (P4): never the name the cabinet sends. */
export interface ControlCabinet {
  id: number
  display_id: string
  simulated: boolean
  connection: 'ONLINE' | 'STALE' | 'OFFLINE'
  smart_mode: boolean | null
  controllable: boolean
  sentence: string | null
  last_heartbeat_at: string | null
}

export const getControlCabinets = (marinaId: number) =>
  api
    .get<{ marina_id: number; demo: boolean; cabinets: ControlCabinet[] }>(`/marinas/${marinaId}/control/cabinets`)
    .then((r) => r.data)

export const allowSession = (
  marinaId: number,
  sessionId: number,
  reason: string,
  pedestalId?: number,
  cabinetId?: number
) =>
  api
    .post(`/marinas/${marinaId}/sessions/${sessionId}/allow`, { reason }, target(pedestalId, cabinetId))
    .then((r) => r.data)

export const denySession = (
  marinaId: number,
  sessionId: number,
  reason: string,
  pedestalId?: number,
  cabinetId?: number
) =>
  api
    .post(`/marinas/${marinaId}/sessions/${sessionId}/deny`, { reason }, target(pedestalId, cabinetId))
    .then((r) => r.data)

export const stopSession = (
  marinaId: number,
  sessionId: number,
  reason: string,
  pedestalId?: number,
  cabinetId?: number
) =>
  api
    .post(`/marinas/${marinaId}/sessions/${sessionId}/stop`, { reason }, target(pedestalId, cabinetId))
    .then((r) => r.data)

export const runDiagnostics = (marinaId: number, pedestalId: number, reason: string) =>
  api
    .post(`/marinas/${marinaId}/pedestals/${pedestalId}/diagnostics`, { reason })
    .then((r) => r.data)
