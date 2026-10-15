import { cabinetSentence } from '../api'
import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getPendingSessions, getActiveSessions } from '../api/energy'
import { allowSession, askReason, denySession, NO_REASON, stopSession } from '../api/controls'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Status, { SESSION } from '../components/ui/Status'

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

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      const [pending, active] = await Promise.all([
        getPendingSessions(id),
        getActiveSessions(id),
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
  }, [id])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleAllow = async (sessionId: number, pedestalId: number) => {
    const reason = await askReason(`Allow session #${sessionId}`)
    if (!reason) { setError(NO_REASON); return }
    setActionLoading(sessionId)
    try {
      await allowSession(id, sessionId, reason, pedestalId)
      await fetchData()
    } catch (err) {
      setError(cabinetSentence(err, 'Failed to allow the session.'))
    } finally {
      setActionLoading(null)
    }
  }

  const handleDeny = async () => {
    if (!denyDialog) return
    if (denyReason.trim().length < 3) { setError(NO_REASON); return }
    setActionLoading(denyDialog.sessionId)
    try {
      await denySession(id, denyDialog.sessionId, denyReason.trim(), denyDialog.pedestalId)
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
    if (!stopDialog) return
    const reason = await askReason(`Stop session #${stopDialog.sessionId}`)
    if (!reason) { setError(NO_REASON); return }
    setActionLoading(stopDialog.sessionId)
    try {
      await stopSession(id, stopDialog.sessionId, reason, stopDialog.pedestalId)
      setStopDialog(null)
      await fetchData()
    } catch (err) {
      setError(cabinetSentence(err, 'Failed to stop the session.'))
    } finally {
      setActionLoading(null)
    }
  }

  return (
    <div className="page max-w-5xl" data-page="control">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="page-title">Pedestal control</h1>
          <p className="page-lead">Approve waiting sessions and stop running ones</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={isStale} onRefresh={fetchData} />

      {error && <div className="notice-danger mb-4" role="alert">{error}</div>}

      <section className="card mb-6">
        <h2 className="text-lg font-bold tracking-tight mb-4 flex items-center gap-2">
          Waiting for approval
          <span className="text-sm font-semibold text-fg-muted tabular-nums">{pendingSessions.length}</span>
        </h2>
        {pendingSessions.length === 0 ? (
          <p className="text-fg-muted text-sm">No sessions are waiting.</p>
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
                    Pedestal {s.pedestal_id}{s.socket_id != null && ` · socket ${s.socket_id}`} · {s.type ?? 'unknown type'}
                    {s.customer_name && ` · ${s.customer_name}`}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button onClick={() => handleAllow(s.id, s.pedestal_id)} className="btn-primary btn-sm"
                    disabled={actionLoading === s.id}>
                    Allow
                  </button>
                  <button onClick={() => setDenyDialog({ sessionId: s.id, pedestalId: s.pedestal_id })}
                    className="btn-danger btn-sm" disabled={actionLoading === s.id}>
                    Deny
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2 className="text-lg font-bold tracking-tight mb-4 flex items-center gap-2">
          Active sessions
          <span className="text-sm font-semibold text-fg-muted tabular-nums">{activeSessions.length}</span>
        </h2>
        {activeSessions.length === 0 ? (
          <p className="text-fg-muted text-sm">No active sessions.</p>
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
                    Pedestal {s.pedestal_id}{s.socket_id != null && ` · socket ${s.socket_id}`}
                    {s.started_at && ` · started ${new Date(s.started_at).toLocaleString()}`}
                  </p>
                </div>
                <button onClick={() => setStopDialog({ sessionId: s.id, pedestalId: s.pedestal_id })}
                  className="btn-danger btn-sm shrink-0 self-start sm:self-center" disabled={actionLoading === s.id}>
                  Stop
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

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
        message={`Stop session #${stopDialog?.sessionId}? Power is cut immediately.`}
        confirmLabel="Stop session"
        confirmVariant="danger"
        onConfirm={handleStop}
        onCancel={() => setStopDialog(null)}
      />
    </div>
  )
}
