/**
 * Pedestal control (spec §6.13, P4): the marina's cabinets as the ERP records them, and
 * the sessions and live data of the CHOSEN one, read through that cabinet's own client.
 *
 * A cabinet is named by its display_id, SIM or real — never by the name it sends about
 * itself. Allow / Deny / Stop exist in the DOM only for a cabinet the server calls
 * `controllable` (Online, Smart Mode ON, and not a real cabinet in the demo marina);
 * otherwise one sentence says why. The server enforces the same rule on every command.
 */
import { cabinetSentence } from '../api'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { getPendingSessions, getActiveSessions } from '../api/energy'
import {
  allowSession, askReason, denySession, getControlCabinets, NO_REASON, stopSession, type ControlCabinet,
} from '../api/controls'
import LiveCabinets from '../components/LiveCabinets'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Status, { CABINET_LINK, SESSION, SIMULATED } from '../components/ui/Status'
import { dateTime, time } from '../utils/format'

interface Session {
  id: number
  status: string
  pedestal_id: number
  socket_id?: number
  type?: string
  started_at?: string
  customer_name?: string
}

export default function PedestalControl() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const id = Number(marinaId)
  const [params, setParams] = useSearchParams()

  const [cabinets, setCabinets] = useState<ControlCabinet[] | null>(null)
  const [pendingSessions, setPendingSessions] = useState<Session[]>([])
  const [activeSessions, setActiveSessions] = useState<Session[]>([])
  const [isStale, setIsStale] = useState(false)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Dialog state
  const [denyDialog, setDenyDialog] = useState<{ sessionId: number; pedestalId: number } | null>(null)
  const [denyReason, setDenyReason] = useState('')
  const [stopDialog, setStopDialog] = useState<{ sessionId: number; pedestalId: number } | null>(null)

  const wanted = Number(params.get('cabinet'))
  const cab = cabinets?.find((c) => c.id === wanted) ?? cabinets?.[0] ?? null
  const cabId = cab?.id

  const loadCabinets = useCallback(() => {
    getControlCabinets(id).then((r) => setCabinets(r.cabinets))
      .catch(() => { setCabinets([]); setError('The cabinets could not be loaded.') })
  }, [id])
  useEffect(() => { loadCabinets() }, [loadCabinets])

  const fetchData = useCallback(async () => {
    if (cabId === undefined) { setLoading(false); return }
    try {
      setLoading(true)
      const [pending, active] = await Promise.all([
        getPendingSessions(id, cabId),
        getActiveSessions(id, cabId),
      ])
      setPendingSessions((pending.sessions ?? []) as Session[])
      setActiveSessions((active.sessions ?? []) as Session[])
      setIsStale(pending.is_stale || active.is_stale)
      setError(null)
    } catch {
      setError('Failed to load sessions.')
    } finally {
      setLoading(false)
    }
  }, [id, cabId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const refresh = () => { loadCabinets(); fetchData() }

  const handleAllow = async (sessionId: number, pedestalId: number) => {
    if (!cab) return
    const reason = await askReason(`Allow session #${sessionId} on ${cab.display_id}`)
    if (!reason) { setError(NO_REASON); return }
    setActionLoading(sessionId)
    try {
      await allowSession(id, sessionId, reason, pedestalId, cab.id)
      await fetchData()
    } catch (err) {
      setError(cabinetSentence(err, 'Failed to allow the session.'))
    } finally {
      setActionLoading(null)
    }
  }

  const handleDeny = async () => {
    if (!denyDialog || !cab) return
    if (denyReason.trim().length < 3) { setError(NO_REASON); return }
    setActionLoading(denyDialog.sessionId)
    try {
      await denySession(id, denyDialog.sessionId, denyReason.trim(), denyDialog.pedestalId, cab.id)
      setDenyDialog(null)
      setDenyReason('')
      await fetchData()
    } catch (err) {
      setError(cabinetSentence(err, 'Failed to deny the session.'))
    } finally {
      setActionLoading(null)
    }
  }

  const handleStop = async () => {
    if (!stopDialog || !cab) return
    const reason = await askReason(`Stop session #${stopDialog.sessionId} on ${cab.display_id}`)
    if (!reason) { setError(NO_REASON); return }
    setActionLoading(stopDialog.sessionId)
    try {
      await stopSession(id, stopDialog.sessionId, reason, stopDialog.pedestalId, cab.id)
      setStopDialog(null)
      await fetchData()
    } catch (err) {
      setError(cabinetSentence(err, 'Failed to stop the session.'))
    } finally {
      setActionLoading(null)
    }
  }

  const where = (s: Session) =>
    `${cab?.display_id ?? ''}${s.socket_id != null ? ` · socket ${s.socket_id}` : ''}`

  return (
    <div className="page max-w-5xl" data-page="control">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="page-title">Pedestal control</h1>
          <p className="page-lead">Approve waiting sessions and stop running ones, one cabinet at a time</p>
        </div>
        <button onClick={refresh} className="btn-secondary" disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <div className="notice-danger mb-4" role="alert">{error}</div>}

      {cabinets !== null && cabinets.length === 0 ? (
        <section className="card" data-no-cabinets>
          <p className="text-sm text-fg-muted">
            No cabinet of this marina is connected in the ERP yet. Commands go only to cabinets the ERP has recorded.
          </p>
        </section>
      ) : cab && cabinets && (
        <>
          <section className="card mb-6" data-control-cabinet={cab.display_id} data-controllable={cab.controllable}>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm min-w-0">
                <span className="text-fg-muted">Cabinet</span>
                <select className="input py-1.5 w-auto max-w-full" data-cabinet-select value={cab.id}
                  onChange={(e) => setParams({ cabinet: e.target.value })}>
                  {cabinets.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.display_id}{c.simulated ? ' · SIM' : ''} · {CABINET_LINK[c.connection].word}
                    </option>
                  ))}
                </select>
              </label>
              <span className="flex flex-wrap items-center gap-2">
                <Status tone={CABINET_LINK[cab.connection].tone} icon={CABINET_LINK[cab.connection].icon} word={CABINET_LINK[cab.connection].word} />
                {cab.simulated && <Status tone={SIMULATED.tone} icon={SIMULATED.icon} word={SIMULATED.word} />}
                {cab.last_heartbeat_at && <span className="text-xs text-fg-muted">last heard {time(cab.last_heartbeat_at)}</span>}
              </span>
            </div>
            {cab.sentence && <p className="text-sm text-fg-muted mt-3" data-no-control>{cab.sentence}</p>}
          </section>

          <StaleDataBanner isStale={isStale} onRefresh={fetchData} />

          <section className="card mb-6">
            <h2 className="text-lg font-bold tracking-tight mb-4 flex items-center gap-2">
              Waiting for approval
              <span className="text-sm font-semibold text-fg-muted tabular-nums">{pendingSessions.length}</span>
            </h2>
            {pendingSessions.length === 0 ? (
              <p className="text-fg-muted text-sm">No sessions are waiting on {cab.display_id}.</p>
            ) : (
              <ul className="divide-y divide-line">
                {pendingSessions.map((s) => (
                  <li key={s.id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Status tone={SESSION.pending.tone} icon={SESSION.pending.icon} word={SESSION.pending.word} />
                        <span className="font-semibold">Session #{s.id}</span>
                      </div>
                      <p className="text-xs text-fg-muted">
                        {where(s)} · {s.type ?? 'unknown type'}
                        {s.customer_name && ` · ${s.customer_name}`}
                      </p>
                    </div>
                    {cab.controllable && (
                      <div className="flex gap-2 shrink-0">
                        <button onClick={() => handleAllow(s.id, s.pedestal_id)} className="btn-primary btn-sm"
                          disabled={actionLoading === s.id} data-session-command="allow">
                          Allow
                        </button>
                        <button onClick={() => setDenyDialog({ sessionId: s.id, pedestalId: s.pedestal_id })}
                          className="btn-danger btn-sm" disabled={actionLoading === s.id} data-session-command="deny">
                          Deny
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card mb-6">
            <h2 className="text-lg font-bold tracking-tight mb-4 flex items-center gap-2">
              Active sessions
              <span className="text-sm font-semibold text-fg-muted tabular-nums">{activeSessions.length}</span>
            </h2>
            {activeSessions.length === 0 ? (
              <p className="text-fg-muted text-sm">No active sessions on {cab.display_id}.</p>
            ) : (
              <ul className="divide-y divide-line">
                {activeSessions.map((s) => (
                  <li key={s.id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Status tone={SESSION.active.tone} icon={SESSION.active.icon} word={SESSION.active.word} />
                        <span className="font-semibold">Session #{s.id}</span>
                      </div>
                      <p className="text-xs text-fg-muted">
                        {where(s)}
                        {s.started_at && ` · started ${dateTime(s.started_at)}`}
                      </p>
                    </div>
                    {cab.controllable && (
                      <button onClick={() => setStopDialog({ sessionId: s.id, pedestalId: s.pedestal_id })}
                        className="btn-danger btn-sm shrink-0 self-start sm:self-center" disabled={actionLoading === s.id}
                        data-session-command="stop">
                        Stop
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* the chosen cabinet, live, through its own client (P4) */}
          <LiveCabinets marinaId={id} cabinet={cab} />
        </>
      )}

      <ConfirmDialog
        isOpen={!!denyDialog}
        title="Deny session"
        message="A reason is required (at least 3 characters). It is written to the audit log and sent to the customer."
        confirmLabel="Deny session"
        confirmVariant="danger"
        onConfirm={handleDeny}
        onCancel={() => { setDenyDialog(null); setDenyReason('') }}
      >
        <input className="input" placeholder="Reason" aria-label="reason" value={denyReason}
          onChange={(e) => setDenyReason(e.target.value)} />
      </ConfirmDialog>

      <ConfirmDialog
        isOpen={!!stopDialog}
        title="Stop session"
        message={`Stop session #${stopDialog?.sessionId} on ${cab?.display_id}? Power is cut immediately.`}
        confirmLabel="Stop session"
        confirmVariant="danger"
        onConfirm={handleStop}
        onCancel={() => setStopDialog(null)}
      />
    </div>
  )
}
