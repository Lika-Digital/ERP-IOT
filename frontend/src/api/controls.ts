import api from './index'

// Every operator command carries a reason: it is written to command_audit before the
// command is sent, and the server refuses a command without one (spec §5.3).
export const askReason = (what: string): string | null => {
  const r = window.prompt(`Razlog (obvezno, zapisuje se uz naredbu): ${what}`)
  if (r === null) return null
  const t = r.trim()
  return t.length >= 3 ? t : null
}

export const NO_REASON = 'Naredba nije poslana — razlog je obvezan (najmanje 3 znaka).'

const withPedestal = (pedestalId?: number) =>
  pedestalId ? { params: { pedestal_id: pedestalId } } : undefined

export const allowSession = (
  marinaId: number,
  sessionId: number,
  reason: string,
  pedestalId?: number
) =>
  api
    .post(`/marinas/${marinaId}/sessions/${sessionId}/allow`, { reason }, withPedestal(pedestalId))
    .then((r) => r.data)

export const denySession = (
  marinaId: number,
  sessionId: number,
  reason: string,
  pedestalId?: number
) =>
  api
    .post(`/marinas/${marinaId}/sessions/${sessionId}/deny`, { reason }, withPedestal(pedestalId))
    .then((r) => r.data)

export const stopSession = (
  marinaId: number,
  sessionId: number,
  reason: string,
  pedestalId?: number
) =>
  api
    .post(`/marinas/${marinaId}/sessions/${sessionId}/stop`, { reason }, withPedestal(pedestalId))
    .then((r) => r.data)

export const runDiagnostics = (marinaId: number, pedestalId: number, reason: string) =>
  api
    .post(`/marinas/${marinaId}/pedestals/${pedestalId}/diagnostics`, { reason })
    .then((r) => r.data)
