import api from './index'

export const allowSession = (marinaId: number, sessionId: number, pedestalId?: number) =>
  api
    .post(
      `/marinas/${marinaId}/sessions/${sessionId}/allow`,
      undefined,
      pedestalId ? { params: { pedestal_id: pedestalId } } : undefined
    )
    .then((r) => r.data)

export const denySession = (
  marinaId: number,
  sessionId: number,
  reason?: string,
  pedestalId?: number
) =>
  api
    .post(
      `/marinas/${marinaId}/sessions/${sessionId}/deny`,
      { reason: reason ?? null },
      pedestalId ? { params: { pedestal_id: pedestalId } } : undefined
    )
    .then((r) => r.data)

export const stopSession = (marinaId: number, sessionId: number, pedestalId?: number) =>
  api
    .post(
      `/marinas/${marinaId}/sessions/${sessionId}/stop`,
      undefined,
      pedestalId ? { params: { pedestal_id: pedestalId } } : undefined
    )
    .then((r) => r.data)

export const runDiagnostics = (marinaId: number, pedestalId: number) =>
  api.post(`/marinas/${marinaId}/pedestals/${pedestalId}/diagnostics`).then((r) => r.data)
