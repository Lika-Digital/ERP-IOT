import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getPendingSessions, getActiveSessions } from '../api/energy'
import { allowSession, denySession, stopSession } from '../api/controls'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import ConfirmDialog from '../components/ui/ConfirmDialog'

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
    setActionLoading(sessionId)
    try {
      await allowSession(id, sessionId, pedestalId)
      await fetchData()
    } catch {
      setError('Failed to allow session.')
    } finally {
      setActionLoading(null)
    }
  }

  const handleDeny = async () => {
    if (!denyDialog) return
    setActionLoading(denyDialog.sessionId)
    try {
      await denySession(id, denyDialog.sessionId, denyReason || undefined, denyDialog.pedestalId)
      setDenyDialog(null)
      setDenyReason('')
      await fetchData()
    } catch {
      setError('Failed to deny session.')
    } finally {
      setActionLoading(null)
    }
  }

  const handleStop = async () => {
    if (!stopDialog) return
    setActionLoading(stopDialog.sessionId)
    try {
      await stopSession(id, stopDialog.sessionId, stopDialog.pedestalId)
      setStopDialog(null)
      await fetchData()
    } catch {
      setError('Failed to stop session.')
    } finally {
      setActionLoading(null)
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Pedestal Control</h1>
          <p className="text-sm text-gray-500 mt-1">Manage session approvals and active sessions</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={isStale} onRefresh={fetchData} />

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Pending sessions */}
      <div className="card mb-6">
        <h2 className="text-lg font-semibold mb-4 text-yellow-700">
          Pending Approvals
          {pendingSessions.length > 0 && (
            <span className="ml-2 badge-yellow">{pendingSessions.length}</span>
          )}
        </h2>

        {pendingSessions.length === 0 ? (
          <p className="text-gray-400 text-sm">No pending sessions.</p>
        ) : (
          <div className="space-y-3">
            {pendingSessions.map((s) => (
              <div
                key={s.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-yellow-50 rounded-lg border border-yellow-200"
              >
                <div>
                  <p className="text-sm font-medium">
                    Session #{s.id} — Pedestal {s.pedestal_id}
                    {s.socket_id != null && ` (Socket ${s.socket_id})`}
                  </p>
                  {s.customer_name && (
                    <p className="text-xs text-gray-600">Customer: {s.customer_name}</p>
                  )}
                  <p className="text-xs text-gray-500">Type: {s.type ?? 'unknown'}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => handleAllow(s.id, s.pedestal_id)}
                    className="btn-primary py-1.5 text-xs"
                    disabled={actionLoading === s.id}
                  >
                    Allow
                  </button>
                  <button
                    onClick={() => setDenyDialog({ sessionId: s.id, pedestalId: s.pedestal_id })}
                    className="btn-danger py-1.5 text-xs"
                    disabled={actionLoading === s.id}
                  >
                    Deny
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active sessions */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">
          Active Sessions
          {activeSessions.length > 0 && (
            <span className="ml-2 badge-green">{activeSessions.length}</span>
          )}
        </h2>

        {activeSessions.length === 0 ? (
          <p className="text-gray-400 text-sm">No active sessions.</p>
        ) : (
          <div className="space-y-3">
            {activeSessions.map((s) => (
              <div
                key={s.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-green-50 rounded-lg border border-green-200"
              >
                <div>
                  <p className="text-sm font-medium">
                    Session #{s.id} — Pedestal {s.pedestal_id}
                    {s.socket_id != null && ` (Socket ${s.socket_id})`}
                  </p>
                  {s.started_at && (
                    <p className="text-xs text-gray-500">
                      Started: {new Date(s.started_at).toLocaleString()}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => setStopDialog({ sessionId: s.id, pedestalId: s.pedestal_id })}
                  className="btn-danger py-1.5 text-xs shrink-0"
                  disabled={actionLoading === s.id}
                >
                  Stop
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Deny dialog */}
      <ConfirmDialog
        isOpen={!!denyDialog}
        title="Deny Session"
        message="Optionally provide a reason for denial that will be sent to the customer."
        confirmLabel="Deny Session"
        confirmVariant="danger"
        onConfirm={handleDeny}
        onCancel={() => { setDenyDialog(null); setDenyReason('') }}
      >
        <input
          className="input"
          placeholder="Reason (optional)"
          value={denyReason}
          onChange={(e) => setDenyReason(e.target.value)}
        />
      </ConfirmDialog>

      {/* Stop dialog */}
      <ConfirmDialog
        isOpen={!!stopDialog}
        title="Stop Session"
        message={`Are you sure you want to stop session #${stopDialog?.sessionId}? This will cut power immediately.`}
        confirmLabel="Stop Session"
        confirmVariant="danger"
        onConfirm={handleStop}
        onCancel={() => setStopDialog(null)}
      />
    </div>
  )
}
