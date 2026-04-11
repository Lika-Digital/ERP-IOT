/**
 * PedestalDetail — three-tab view for a single pedestal.
 *
 * Tab 1 — Real Time: health indicators + sessions + alarms for this pedestal
 * Tab 2 — Berths:    occupancy per berth, camera frame grab, RTSP stream URL
 * Tab 3 — Controls:  allow/deny/stop sessions + acknowledge alarms
 *                    (mirrors PedestalControl look and feel, scoped to this pedestal)
 */
import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getDashboard, type PedestalInfo, type PedestalHealth, type SessionInfo } from '../api/dashboard'
import { getPendingSessions, getActiveSessions } from '../api/energy'
import { getActiveAlarms, getAlarmLog, acknowledgeAlarm, type AlarmLogEntry } from '../api/alarms'
import { allowSession, denySession, stopSession } from '../api/controls'
import {
  getBerthOccupancy,
  getCameraFrame,
  getCameraStreamUrl,
  type BerthOccupancy,
  type BerthOccupancyPayload,
  type CameraStreamPayload,
} from '../api/pedestalExt'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import ConfirmDialog from '../components/ui/ConfirmDialog'

type Tab = 'realtime' | 'berths' | 'controls'

// ── Sub-state types ───────────────────────────────────────────────────────────

interface FrameState {
  objectUrl: string | null
  capturedAt: string | null
  loading: boolean
  error: string | null
}

interface StreamState {
  data: CameraStreamPayload | null
  loading: boolean
  error: string | null
}

interface OccupancyState {
  data: BerthOccupancyPayload | null
  loading: boolean
  error: string | null
  featureUnavailable: boolean
}

interface Session {
  id: number
  status: string
  pedestal_id: number
  socket_id?: number
  type?: string
  started_at?: string
  customer_name?: string
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PedestalDetail() {
  const { marinaId, pedestalId } = useParams<{ marinaId: string; pedestalId: string }>()
  const navigate = useNavigate()
  const mid = Number(marinaId)
  const pid = Number(pedestalId)

  const [tab, setTab] = useState<Tab>('realtime')

  // Real Time state
  const [pedestalInfo, setPedestalInfo] = useState<PedestalInfo | null>(null)
  const [health, setHealth] = useState<PedestalHealth | null>(null)
  const [activeSessions, setActiveSessions] = useState<Session[]>([])
  const [pendingSessions, setPendingSessions] = useState<Session[]>([])
  const [alarmLog, setAlarmLog] = useState<AlarmLogEntry[]>([])
  const [isStaleRT, setIsStaleRT] = useState(false)
  const [loadingRT, setLoadingRT] = useState(true)
  const [errorRT, setErrorRT] = useState<string | null>(null)

  // Berths state
  const [occupancy, setOccupancy] = useState<OccupancyState>({
    data: null, loading: false, error: null, featureUnavailable: false,
  })
  const [frames, setFrames] = useState<Record<number, FrameState>>({})
  const [stream, setStream] = useState<StreamState>({ data: null, loading: false, error: null })

  // Controls dialog state
  const [denyDialog, setDenyDialog] = useState<{ sessionId: number } | null>(null)
  const [denyReason, setDenyReason] = useState('')
  const [stopDialog, setStopDialog] = useState<{ sessionId: number } | null>(null)
  const [ackDialog, setAckDialog] = useState<{ alarmId: number } | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [controlError, setControlError] = useState<string | null>(null)

  // ── Data fetch ─────────────────────────────────────────────────────────────

  const fetchRealTime = useCallback(async () => {
    try {
      setLoadingRT(true)
      const [dash, pending, active, alarms] = await Promise.all([
        getDashboard(mid),
        getPendingSessions(mid),
        getActiveSessions(mid),
        getAlarmLog(mid, { pedestal_id: pid, limit: 20 }),
      ])

      const info = Array.isArray(dash.pedestals)
        ? dash.pedestals.find((p: PedestalInfo) => p.id === pid) ?? null
        : null
      setPedestalInfo(info)
      setHealth((dash.health as Record<string, PedestalHealth>)?.[String(pid)] ?? null)

      const filterByPedestal = (sessions: unknown[]): Session[] =>
        (sessions as Session[]).filter((s) => s.pedestal_id === pid)

      setPendingSessions(filterByPedestal(pending.sessions ?? []))
      setActiveSessions(filterByPedestal(active.sessions ?? []))
      setAlarmLog(alarms.alarms ?? [])
      setIsStaleRT(dash.is_stale || pending.is_stale || active.is_stale)
      setErrorRT(null)
    } catch {
      setErrorRT('Failed to load pedestal data.')
    } finally {
      setLoadingRT(false)
    }
  }, [mid, pid])

  const fetchOccupancy = useCallback(async () => {
    setOccupancy({ data: null, loading: true, error: null, featureUnavailable: false })
    try {
      const resp = await getBerthOccupancy(mid, pid)
      setOccupancy({ data: resp.data, loading: false, error: null, featureUnavailable: false })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setOccupancy({
        data: null,
        loading: false,
        error: status === 503 ? null : 'Failed to load berth occupancy.',
        featureUnavailable: status === 503,
      })
    }
  }, [mid, pid])

  const fetchFrame = useCallback(async (berthId: number) => {
    setFrames((prev) => {
      if (prev[berthId]?.objectUrl) URL.revokeObjectURL(prev[berthId].objectUrl!)
      return { ...prev, [berthId]: { objectUrl: null, capturedAt: null, loading: true, error: null } }
    })
    try {
      const url = await getCameraFrame(mid, pid)
      setFrames((prev) => ({
        ...prev,
        [berthId]: { objectUrl: url, capturedAt: new Date().toISOString(), loading: false, error: null },
      }))
    } catch {
      setFrames((prev) => ({
        ...prev,
        [berthId]: { objectUrl: null, capturedAt: null, loading: false, error: 'Frame unavailable.' },
      }))
    }
  }, [mid, pid])

  const fetchStream = useCallback(async () => {
    setStream({ data: null, loading: true, error: null })
    try {
      const resp = await getCameraStreamUrl(mid, pid)
      setStream({ data: resp.data, loading: false, error: null })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      const msg = status === 503 ? 'Camera feature not available on this pedestal.' : 'Failed to get stream URL.'
      setStream({ data: null, loading: false, error: msg })
    }
  }, [mid, pid])

  // Load Real Time on mount
  useEffect(() => { fetchRealTime() }, [fetchRealTime])

  // Load berths when switching to Berths tab
  useEffect(() => {
    if (tab === 'berths' && !occupancy.data && !occupancy.loading) fetchOccupancy()
  }, [tab]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Controls handlers ──────────────────────────────────────────────────────

  const handleAllow = async (sessionId: number) => {
    setActionLoading(sessionId)
    try {
      await allowSession(mid, sessionId, pid)
      await fetchRealTime()
    } catch { setControlError('Failed to allow session.') }
    finally { setActionLoading(null) }
  }

  const handleDeny = async () => {
    if (!denyDialog) return
    setActionLoading(denyDialog.sessionId)
    try {
      await denySession(mid, denyDialog.sessionId, denyReason || undefined, pid)
      setDenyDialog(null); setDenyReason('')
      await fetchRealTime()
    } catch { setControlError('Failed to deny session.') }
    finally { setActionLoading(null) }
  }

  const handleStop = async () => {
    if (!stopDialog) return
    setActionLoading(stopDialog.sessionId)
    try {
      await stopSession(mid, stopDialog.sessionId, pid)
      setStopDialog(null)
      await fetchRealTime()
    } catch { setControlError('Failed to stop session.') }
    finally { setActionLoading(null) }
  }

  const handleAckAlarm = async () => {
    if (!ackDialog) return
    setActionLoading(ackDialog.alarmId)
    try {
      await acknowledgeAlarm(mid, ackDialog.alarmId, pid)
      setAckDialog(null)
      await fetchRealTime()
    } catch { setControlError('Failed to acknowledge alarm.') }
    finally { setActionLoading(null) }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate(`/marinas/${mid}/dashboard`)} className="text-sm text-gray-500 hover:text-gray-700">
          ← Dashboard
        </button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-gray-900">
            {pedestalInfo?.name ?? `Pedestal ${pid}`}
          </h1>
          {pedestalInfo?.location && (
            <p className="text-sm text-gray-500">{pedestalInfo.location}</p>
          )}
        </div>
        {health && (
          <span className={`text-xs font-medium px-2 py-1 rounded-full ${
            health.opta_connected ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
          }`}>
            {health.opta_connected ? 'Online' : 'Offline'}
          </span>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        <TabButton active={tab === 'realtime'} onClick={() => setTab('realtime')}>Real Time</TabButton>
        <TabButton active={tab === 'berths'} onClick={() => setTab('berths')}>Berths</TabButton>
        <TabButton active={tab === 'controls'} onClick={() => setTab('controls')}>Controls</TabButton>
      </div>

      {/* ── Real Time tab ─────────────────────────────────────────────────── */}
      {tab === 'realtime' && (
        <RealTimeTab
          health={health}
          activeSessions={activeSessions}
          pendingSessions={pendingSessions}
          alarmLog={alarmLog}
          isStale={isStaleRT}
          loading={loadingRT}
          error={errorRT}
          onRefresh={fetchRealTime}
        />
      )}

      {/* ── Berths tab ───────────────────────────────────────────────────── */}
      {tab === 'berths' && (
        <BerthsTab
          pedestalId={pid}
          occupancy={occupancy}
          frames={frames}
          stream={stream}
          onRefreshOccupancy={fetchOccupancy}
          onGetFrame={fetchFrame}
          onGetStream={fetchStream}
        />
      )}

      {/* ── Controls tab ─────────────────────────────────────────────────── */}
      {tab === 'controls' && (
        <>
          <ControlsTab
            pendingSessions={pendingSessions}
            activeSessions={activeSessions}
            alarmLog={alarmLog}
            loading={loadingRT}
            actionLoading={actionLoading}
            error={controlError}
            onRefresh={fetchRealTime}
            onAllow={handleAllow}
            onDenyOpen={(sessionId) => setDenyDialog({ sessionId })}
            onStopOpen={(sessionId) => setStopDialog({ sessionId })}
            onAckOpen={(alarmId) => setAckDialog({ alarmId })}
          />

          {/* Deny dialog */}
          <ConfirmDialog
            isOpen={!!denyDialog}
            title="Deny Session"
            message="Optionally provide a reason for denial."
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
            message={`Stop session #${stopDialog?.sessionId}? This will cut power immediately.`}
            confirmLabel="Stop Session"
            confirmVariant="danger"
            onConfirm={handleStop}
            onCancel={() => setStopDialog(null)}
          />

          {/* Acknowledge dialog */}
          <ConfirmDialog
            isOpen={!!ackDialog}
            title="Acknowledge Alarm"
            message={`Acknowledge alarm #${ackDialog?.alarmId}?`}
            confirmLabel="Acknowledge"
            confirmVariant="primary"
            onConfirm={handleAckAlarm}
            onCancel={() => setAckDialog(null)}
          />
        </>
      )}
    </div>
  )
}

// ── Real Time tab ──────────────────────────────────────────────────────────────

function RealTimeTab({
  health,
  activeSessions,
  pendingSessions,
  alarmLog,
  isStale,
  loading,
  error,
  onRefresh,
}: {
  health: PedestalHealth | null
  activeSessions: Session[]
  pendingSessions: Session[]
  alarmLog: AlarmLogEntry[]
  isStale: boolean
  loading: boolean
  error: string | null
  onRefresh: () => void
}) {
  return (
    <div>
      <div className="flex justify-end mb-4">
        <button className="btn-secondary" onClick={onRefresh} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={isStale} onRefresh={onRefresh} />

      {error && (
        <div className="card bg-red-50 border-red-200 mb-4">
          <p className="text-red-700">{error}</p>
          <button className="btn-primary mt-2" onClick={onRefresh}>Retry</button>
        </div>
      )}

      {/* Health */}
      {health && (
        <div className="card mb-4">
          <h2 className="text-base font-semibold mb-3">Health</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <HealthRow label="OPTA Connected" ok={health.opta_connected} />
            <HealthRow label="Camera Reachable" ok={health.camera_reachable} />
            <HealthRow label="Temp Sensor" ok={health.temp_sensor_reachable} />
            {health.last_heartbeat && (
              <div className="col-span-2 text-xs text-gray-500">
                Last heartbeat: {new Date(health.last_heartbeat).toLocaleString()}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pending sessions */}
      <div className="card mb-4">
        <h2 className="text-base font-semibold mb-3 text-yellow-700">
          Pending Approvals
          {pendingSessions.length > 0 && (
            <span className="ml-2 badge-yellow">{pendingSessions.length}</span>
          )}
        </h2>
        {pendingSessions.length === 0 ? (
          <p className="text-sm text-gray-400">No pending sessions for this pedestal.</p>
        ) : (
          <div className="space-y-2">
            {pendingSessions.map((s) => (
              <div key={s.id} className="px-3 py-2 bg-yellow-50 rounded-lg border border-yellow-200 text-sm">
                <p className="font-medium">Session #{s.id}{s.socket_id != null && ` · Socket ${s.socket_id}`}</p>
                <p className="text-xs text-gray-500">Type: {s.type ?? '—'}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active sessions */}
      <div className="card mb-4">
        <h2 className="text-base font-semibold mb-3">
          Active Sessions
          {activeSessions.length > 0 && (
            <span className="ml-2 badge-green">{activeSessions.length}</span>
          )}
        </h2>
        {activeSessions.length === 0 ? (
          <p className="text-sm text-gray-400">No active sessions for this pedestal.</p>
        ) : (
          <div className="space-y-2">
            {activeSessions.map((s) => (
              <div key={s.id} className="px-3 py-2 bg-green-50 rounded-lg border border-green-200 text-sm">
                <p className="font-medium">Session #{s.id}{s.socket_id != null && ` · Socket ${s.socket_id}`}</p>
                {s.started_at && (
                  <p className="text-xs text-gray-500">Started: {new Date(s.started_at).toLocaleString()}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Alarm log */}
      <div className="card">
        <h2 className="text-base font-semibold mb-3">Recent Alarms</h2>
        {alarmLog.length === 0 ? (
          <p className="text-sm text-gray-400">No alarms recorded for this pedestal.</p>
        ) : (
          <div className="space-y-2">
            {alarmLog.map((a) => (
              <div key={a.id} className={`px-3 py-2 rounded-lg border text-sm ${a.acknowledged_at ? 'bg-gray-50 border-gray-200' : 'bg-red-50 border-red-200'}`}>
                <div className="flex items-center justify-between">
                  <p className="font-medium">Alarm #{a.id}</p>
                  {a.acknowledged_at ? (
                    <span className="text-xs text-gray-500">Acknowledged</span>
                  ) : (
                    <span className="text-xs text-red-600 font-medium">Unacknowledged</span>
                  )}
                </div>
                <p className="text-xs text-gray-500">{new Date(a.received_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Berths tab ────────────────────────────────────────────────────────────────

function BerthsTab({
  pedestalId,
  occupancy,
  frames,
  stream,
  onRefreshOccupancy,
  onGetFrame,
  onGetStream,
}: {
  pedestalId: number
  occupancy: OccupancyState
  frames: Record<number, FrameState>
  stream: StreamState
  onRefreshOccupancy: () => void
  onGetFrame: (berthId: number) => void
  onGetStream: () => void
}) {
  return (
    <div>
      {/* Occupancy section */}
      <div className="card mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">Berth Occupancy</h2>
          <button
            className="btn-secondary py-1 text-xs"
            onClick={onRefreshOccupancy}
            disabled={occupancy.loading}
          >
            {occupancy.loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        {occupancy.featureUnavailable && (
          <p className="text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded-lg">
            Feature not available on this pedestal
          </p>
        )}
        {occupancy.error && <p className="text-sm text-red-600">{occupancy.error}</p>}
        {!occupancy.data && !occupancy.loading && !occupancy.featureUnavailable && !occupancy.error && (
          <p className="text-sm text-gray-400 italic">Click Refresh to load occupancy data.</p>
        )}

        {occupancy.data && !occupancy.featureUnavailable && (
          <>
            {occupancy.data.berths.length === 0 ? (
              <p className="text-sm text-gray-400 italic">No berths configured for this pedestal</p>
            ) : (
              <div className="space-y-3">
                {occupancy.data.berths.map((b) => (
                  <BerthDetailRow
                    key={b.berth_id}
                    berth={b}
                    pedestalId={pedestalId}
                    frame={frames[b.berth_id]}
                    onGetFrame={() => onGetFrame(b.berth_id)}
                  />
                ))}
              </div>
            )}
            {occupancy.data.message && (
              <p className="text-xs text-gray-400 mt-2 italic">{occupancy.data.message}</p>
            )}
          </>
        )}
      </div>

      {/* Camera stream section */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">Live Stream</h2>
          <button
            className="btn-secondary py-1 text-xs"
            onClick={onGetStream}
            disabled={stream.loading}
          >
            {stream.loading ? 'Loading...' : 'Get Stream URL'}
          </button>
        </div>

        {stream.error && (
          <p className="text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded-lg">{stream.error}</p>
        )}

        {stream.data && (
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-2 h-2 rounded-full ${stream.data.reachable ? 'bg-green-500' : 'bg-red-400'}`} />
              <span className="text-xs text-gray-500">
                {stream.data.reachable ? 'Reachable' : 'Not reachable'}
                {stream.data.last_checked && ` · checked ${new Date(stream.data.last_checked).toLocaleString()}`}
              </span>
            </div>
            <input
              type="text"
              readOnly
              value={stream.data.stream_url}
              className="input font-mono text-xs bg-gray-50"
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <p className="text-xs text-gray-400 mt-2">
              Copy this URL and open it in VLC or any RTSP-compatible player.
            </p>
          </div>
        )}

        {!stream.data && !stream.loading && !stream.error && (
          <p className="text-sm text-gray-400 italic">Click Get Stream URL to fetch the RTSP address.</p>
        )}
      </div>
    </div>
  )
}

function BerthDetailRow({
  berth,
  pedestalId,
  frame,
  onGetFrame,
}: {
  berth: BerthOccupancy
  pedestalId: number
  frame?: FrameState
  onGetFrame: () => void
}) {
  return (
    <div className="border border-gray-100 rounded-lg p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <OccupancyBadge occupied={berth.occupied} />
          <div>
            <p className="text-sm font-medium">{berth.berth_name ?? `Berth ${berth.berth_id}`}</p>
            {berth.last_analyzed && (
              <p className="text-xs text-gray-400">Analyzed: {new Date(berth.last_analyzed).toLocaleString()}</p>
            )}
            {berth.note && <p className="text-xs text-gray-400 italic">{berth.note}</p>}
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary py-1 text-xs shrink-0" onClick={onGetFrame} disabled={frame?.loading}>
            {frame?.loading ? 'Loading...' : 'Get Frame'}
          </button>
        </div>
      </div>

      {/* Frame inline */}
      {frame && !frame.loading && (
        <div className="mt-3">
          {frame.error ? (
            <p className="text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded">
              Camera feature not available on this pedestal
            </p>
          ) : frame.objectUrl ? (
            <div>
              <img
                src={frame.objectUrl}
                alt={`Camera frame — pedestal ${pedestalId}`}
                className="w-full max-w-lg rounded-lg border border-gray-200"
              />
              {frame.capturedAt && (
                <p className="text-xs text-gray-400 mt-1">
                  Captured: {new Date(frame.capturedAt).toLocaleString()}
                </p>
              )}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

// ── Controls tab ──────────────────────────────────────────────────────────────

function ControlsTab({
  pendingSessions,
  activeSessions,
  alarmLog,
  loading,
  actionLoading,
  error,
  onRefresh,
  onAllow,
  onDenyOpen,
  onStopOpen,
  onAckOpen,
}: {
  pendingSessions: Session[]
  activeSessions: Session[]
  alarmLog: AlarmLogEntry[]
  loading: boolean
  actionLoading: number | null
  error: string | null
  onRefresh: () => void
  onAllow: (sessionId: number) => void
  onDenyOpen: (sessionId: number) => void
  onStopOpen: (sessionId: number) => void
  onAckOpen: (alarmId: number) => void
}) {
  const unackedAlarms = alarmLog.filter((a) => !a.acknowledged_at)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">Control sessions and alarms for this pedestal.</p>
        <button className="btn-secondary" onClick={onRefresh} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Pending sessions — Allow / Deny */}
      <div className="card mb-6">
        <h2 className="text-lg font-semibold mb-4 text-yellow-700">
          Pending Approvals
          {pendingSessions.length > 0 && <span className="ml-2 badge-yellow">{pendingSessions.length}</span>}
        </h2>
        {pendingSessions.length === 0 ? (
          <p className="text-gray-400 text-sm">No pending sessions for this pedestal.</p>
        ) : (
          <div className="space-y-3">
            {pendingSessions.map((s) => (
              <div key={s.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-yellow-50 rounded-lg border border-yellow-200">
                <div>
                  <p className="text-sm font-medium">
                    Session #{s.id}{s.socket_id != null && ` (Socket ${s.socket_id})`}
                  </p>
                  {s.customer_name && <p className="text-xs text-gray-600">Customer: {s.customer_name}</p>}
                  <p className="text-xs text-gray-500">Type: {s.type ?? 'unknown'}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => onAllow(s.id)}
                    className="btn-primary py-1.5 text-xs"
                    disabled={actionLoading === s.id}
                  >
                    Allow
                  </button>
                  <button
                    onClick={() => onDenyOpen(s.id)}
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

      {/* Active sessions — Stop */}
      <div className="card mb-6">
        <h2 className="text-lg font-semibold mb-4">
          Active Sessions
          {activeSessions.length > 0 && <span className="ml-2 badge-green">{activeSessions.length}</span>}
        </h2>
        {activeSessions.length === 0 ? (
          <p className="text-gray-400 text-sm">No active sessions for this pedestal.</p>
        ) : (
          <div className="space-y-3">
            {activeSessions.map((s) => (
              <div key={s.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-green-50 rounded-lg border border-green-200">
                <div>
                  <p className="text-sm font-medium">
                    Session #{s.id}{s.socket_id != null && ` (Socket ${s.socket_id})`}
                  </p>
                  {s.started_at && (
                    <p className="text-xs text-gray-500">Started: {new Date(s.started_at).toLocaleString()}</p>
                  )}
                </div>
                <button
                  onClick={() => onStopOpen(s.id)}
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

      {/* Active alarms — Acknowledge */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">
          Active Alarms
          {unackedAlarms.length > 0 && <span className="ml-2 text-xs font-semibold bg-red-100 text-red-700 px-2 py-0.5 rounded-full">{unackedAlarms.length}</span>}
        </h2>
        {unackedAlarms.length === 0 ? (
          <p className="text-gray-400 text-sm">No active alarms for this pedestal.</p>
        ) : (
          <div className="space-y-3">
            {unackedAlarms.map((a) => (
              <div key={a.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-red-50 rounded-lg border border-red-200">
                <div>
                  <p className="text-sm font-medium">Alarm #{a.id}</p>
                  <p className="text-xs text-gray-500">{new Date(a.received_at).toLocaleString()}</p>
                  {a.alarm_data && typeof a.alarm_data === 'object' && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      {Object.entries(a.alarm_data)
                        .filter(([k]) => k !== 'id')
                        .slice(0, 3)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(' · ')}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => onAckOpen(a.id)}
                  className="btn-secondary py-1.5 text-xs shrink-0"
                  disabled={actionLoading === a.id}
                >
                  Acknowledge
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function OccupancyBadge({ occupied }: { occupied: boolean | null }) {
  if (occupied === null || occupied === undefined) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
        <span className="w-1.5 h-1.5 rounded-full bg-gray-400" />
        No Analysis
      </span>
    )
  }
  return occupied ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
      <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
      Occupied
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
      <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
      Available
    </span>
  )
}

function HealthRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`w-2 h-2 rounded-full ${ok ? 'bg-green-500' : 'bg-red-400'}`} />
      <span className="text-gray-700">{label}</span>
      <span className={`text-xs ${ok ? 'text-green-600' : 'text-red-500'}`}>{ok ? 'OK' : 'Fault'}</span>
    </div>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
        active
          ? 'border-brand-600 text-brand-700'
          : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
      }`}
    >
      {children}
    </button>
  )
}
