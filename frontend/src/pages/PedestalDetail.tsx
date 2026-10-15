/**
 * PedestalDetail — three-tab view for a single pedestal.
 *
 * Tab 1 — Real Time: health indicators + sessions + alarms for this pedestal
 * Tab 2 — Berths:    occupancy per berth, camera frame grab, RTSP stream URL
 * Tab 3 — Controls:  allow/deny/stop sessions + acknowledge alarms
 *                    (mirrors PedestalControl look and feel, scoped to this pedestal)
 */
import { cabinetSentence } from '../api'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getDashboard, type PedestalInfo, type PedestalHealth, type SessionInfo } from '../api/dashboard'
import { getPendingSessions, getActiveSessions } from '../api/energy'
import { getActiveAlarms, getAlarmLog, acknowledgeAlarm, type AlarmLogEntry } from '../api/alarms'
import { allowSession, askReason, denySession, NO_REASON, stopSession } from '../api/controls'
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
import Status, { ALARM_STATE, OCCUPANCY, REACH, SESSION } from '../components/ui/Status'

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
    const reason = await askReason(`Allow session #${sessionId}`)
    if (!reason) { setControlError(NO_REASON); return }
    setActionLoading(sessionId)
    try {
      await allowSession(mid, sessionId, reason, pid)
      await fetchRealTime()
    } catch (err) { setControlError(cabinetSentence(err, 'Failed to allow session.')) }
    finally { setActionLoading(null) }
  }

  const handleDeny = async () => {
    if (!denyDialog) return
    if (denyReason.trim().length < 3) { setControlError(NO_REASON); return }
    setActionLoading(denyDialog.sessionId)
    try {
      await denySession(mid, denyDialog.sessionId, denyReason.trim(), pid)
      setDenyDialog(null); setDenyReason('')
      await fetchRealTime()
    } catch (err) { setControlError(cabinetSentence(err, 'Failed to deny session.')) }
    finally { setActionLoading(null) }
  }

  const handleStop = async () => {
    if (!stopDialog) return
    const reason = await askReason(`Stop session #${stopDialog.sessionId}`)
    if (!reason) { setControlError(NO_REASON); return }
    setActionLoading(stopDialog.sessionId)
    try {
      await stopSession(mid, stopDialog.sessionId, reason, pid)
      setStopDialog(null)
      await fetchRealTime()
    } catch (err) { setControlError(cabinetSentence(err, 'Failed to stop session.')) }
    finally { setActionLoading(null) }
  }

  const handleAckAlarm = async () => {
    if (!ackDialog) return
    setActionLoading(ackDialog.alarmId)
    try {
      await acknowledgeAlarm(mid, ackDialog.alarmId, pid)
      setAckDialog(null)
      await fetchRealTime()
    } catch (err) { setControlError(cabinetSentence(err, 'Failed to acknowledge alarm.')) }
    finally { setActionLoading(null) }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="page max-w-5xl" data-page="pedestal">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3 mb-6">
        <button onClick={() => navigate(`/marinas/${mid}/dashboard`)} className="btn-secondary btn-sm">
          ← Dashboard
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="page-title truncate">{pedestalInfo?.name ?? `Pedestal ${pid}`}</h1>
          {pedestalInfo?.location && <p className="page-lead">{pedestalInfo.location}</p>}
        </div>
        {health?.last_heartbeat && (
          <span className="text-xs text-fg-muted tabular-nums self-center">
            last heard {new Date(health.last_heartbeat).toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-line overflow-x-auto">
        <TabButton active={tab === 'realtime'} onClick={() => setTab('realtime')}>Real time</TabButton>
        <TabButton active={tab === 'berths'} onClick={() => setTab('berths')}>Berths</TabButton>
        <TabButton active={tab === 'controls'} onClick={() => setTab('controls')}>Controls</TabButton>
      </div>

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

          <ConfirmDialog
            isOpen={!!denyDialog}
            title="Deny session"
            message="A reason is required (at least 3 characters). It is written to the audit log."
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

          <ConfirmDialog
            isOpen={!!ackDialog}
            title="Acknowledge alarm"
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

function SessionLine({ s, kind, children }: { s: Session; kind: 'pending' | 'active'; children?: React.ReactNode }) {
  const look = SESSION[kind]
  return (
    <li className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Status tone={look.tone} icon={look.icon} word={look.word} />
          <span className="font-semibold">Session #{s.id}</span>
        </div>
        <p className="text-xs text-fg-muted">
          {s.socket_id != null ? `socket ${s.socket_id}` : 'no socket'} · {s.type ?? 'unknown type'}
          {s.customer_name && ` · ${s.customer_name}`}
          {s.started_at && ` · started ${new Date(s.started_at).toLocaleString()}`}
        </p>
      </div>
      {children}
    </li>
  )
}

function AlarmLine({ a, children }: { a: AlarmLogEntry; children?: React.ReactNode }) {
  const look = ALARM_STATE[a.acknowledged_at ? 'acknowledged' : 'open']
  const fields = a.alarm_data && typeof a.alarm_data === 'object'
    ? Object.entries(a.alarm_data).filter(([k]) => k !== 'id').slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(' · ')
    : ''
  return (
    <li className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <Status tone={look.tone} icon={look.icon} word={look.word} />
          <span className="font-semibold">Alarm #{a.id}</span>
        </div>
        <p className="text-xs text-fg-muted">{new Date(a.received_at).toLocaleString()}{fields && ` · ${fields}`}</p>
      </div>
      {children}
    </li>
  )
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="card mb-4">
      <h2 className="text-lg font-bold tracking-tight mb-2 flex items-center gap-2">
        {title}
        {count !== undefined && <span className="text-sm font-semibold text-fg-muted tabular-nums">{count}</span>}
      </h2>
      {children}
    </section>
  )
}

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
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={isStale} onRefresh={onRefresh} />

      {error && (
        <div className="notice-danger mb-4" role="alert">
          <p>{error}</p>
          <button className="btn-primary btn-sm mt-2" onClick={onRefresh}>Retry</button>
        </div>
      )}

      {health && (
        <Section title="Devices">
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <HealthRow label="Camera" ok={health.camera_reachable} />
            <HealthRow label="Temperature sensor" ok={health.temp_sensor_reachable} />
          </div>
          {health.last_heartbeat && (
            <p className="mt-2 text-xs text-fg-muted">Last heartbeat {new Date(health.last_heartbeat).toLocaleString()}</p>
          )}
        </Section>
      )}

      <Section title="Waiting for approval" count={pendingSessions.length}>
        {pendingSessions.length === 0 ? (
          <p className="text-sm text-fg-muted">No sessions are waiting on this pedestal.</p>
        ) : (
          <ul className="divide-y divide-line">{pendingSessions.map((s) => <SessionLine key={s.id} s={s} kind="pending" />)}</ul>
        )}
      </Section>

      <Section title="Active sessions" count={activeSessions.length}>
        {activeSessions.length === 0 ? (
          <p className="text-sm text-fg-muted">No active sessions on this pedestal.</p>
        ) : (
          <ul className="divide-y divide-line">{activeSessions.map((s) => <SessionLine key={s.id} s={s} kind="active" />)}</ul>
        )}
      </Section>

      <Section title="Recent alarms">
        {alarmLog.length === 0 ? (
          <p className="text-sm text-fg-muted">No alarms recorded for this pedestal.</p>
        ) : (
          <ul className="divide-y divide-line">{alarmLog.map((a) => <AlarmLine key={a.id} a={a} />)}</ul>
        )}
      </Section>
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
  const reach = stream.data ? REACH[stream.data.reachable ? 'yes' : 'no'] : null
  return (
    <div>
      <section className="card mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-lg font-bold tracking-tight">Berth occupancy</h2>
          <button className="btn-secondary btn-sm" onClick={onRefreshOccupancy} disabled={occupancy.loading}>
            {occupancy.loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>

        {occupancy.featureUnavailable && <p className="notice-warn">This feature is not available on this pedestal.</p>}
        {occupancy.error && <p className="notice-danger" role="alert">{occupancy.error}</p>}
        {!occupancy.data && !occupancy.loading && !occupancy.featureUnavailable && !occupancy.error && (
          <p className="text-sm text-fg-muted">Press Refresh to load occupancy.</p>
        )}

        {occupancy.data && !occupancy.featureUnavailable && (
          <>
            {occupancy.data.berths.length === 0 ? (
              <p className="text-sm text-fg-muted">No berths are configured for this pedestal.</p>
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
            {occupancy.data.message && <p className="text-xs text-fg-muted mt-2">{occupancy.data.message}</p>}
          </>
        )}
      </section>

      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-lg font-bold tracking-tight">Live stream</h2>
          <button className="btn-secondary btn-sm" onClick={onGetStream} disabled={stream.loading}>
            {stream.loading ? 'Loading…' : 'Get stream URL'}
          </button>
        </div>

        {stream.error && <p className="notice-warn">{stream.error}</p>}

        {stream.data && reach && (
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <Status tone={reach.tone} icon={reach.icon} word={reach.word} />
              {stream.data.last_checked && (
                <span className="text-xs text-fg-muted">checked {new Date(stream.data.last_checked).toLocaleString()}</span>
              )}
            </div>
            <input
              type="text"
              readOnly
              aria-label="stream URL"
              value={stream.data.stream_url}
              className="input font-mono text-xs bg-surface-2"
              onClick={(e) => (e.target as HTMLInputElement).select()}
            />
            <p className="text-xs text-fg-muted mt-2">Copy this URL and open it in VLC or any RTSP player.</p>
          </div>
        )}

        {!stream.data && !stream.loading && !stream.error && (
          <p className="text-sm text-fg-muted">Press Get stream URL to fetch the RTSP address.</p>
        )}
      </section>
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
    <div className="border border-line rounded-control p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <OccupancyBadge occupied={berth.occupied} />
          <div>
            <p className="text-sm font-semibold">{berth.berth_name ?? `Berth ${berth.berth_id}`}</p>
            {berth.last_analyzed && (
              <p className="text-xs text-fg-muted">Analysed {new Date(berth.last_analyzed).toLocaleString()}</p>
            )}
            {berth.note && <p className="text-xs text-fg-muted">{berth.note}</p>}
          </div>
        </div>
        <button className="btn-secondary btn-sm shrink-0" onClick={onGetFrame} disabled={frame?.loading}>
          {frame?.loading ? 'Loading…' : 'Get frame'}
        </button>
      </div>

      {frame && !frame.loading && (
        <div className="mt-3">
          {frame.error ? (
            <p className="notice-warn">The camera is not available on this pedestal.</p>
          ) : frame.objectUrl ? (
            <div>
              <img
                src={frame.objectUrl}
                alt={`Camera frame — pedestal ${pedestalId}`}
                className="w-full max-w-lg rounded-control border border-line"
              />
              {frame.capturedAt && (
                <p className="text-xs text-fg-muted mt-1">Captured {new Date(frame.capturedAt).toLocaleString()}</p>
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
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <p className="text-sm text-fg-muted">Sessions and alarms on this pedestal.</p>
        <button className="btn-secondary" onClick={onRefresh} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <div className="notice-danger mb-4" role="alert">{error}</div>}

      <Section title="Waiting for approval" count={pendingSessions.length}>
        {pendingSessions.length === 0 ? (
          <p className="text-fg-muted text-sm">No sessions are waiting on this pedestal.</p>
        ) : (
          <ul className="divide-y divide-line">
            {pendingSessions.map((s) => (
              <SessionLine key={s.id} s={s} kind="pending">
                <div className="flex gap-2 shrink-0">
                  <button onClick={() => onAllow(s.id)} className="btn-primary btn-sm" disabled={actionLoading === s.id}>
                    Allow
                  </button>
                  <button onClick={() => onDenyOpen(s.id)} className="btn-danger btn-sm" disabled={actionLoading === s.id}>
                    Deny
                  </button>
                </div>
              </SessionLine>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Active sessions" count={activeSessions.length}>
        {activeSessions.length === 0 ? (
          <p className="text-fg-muted text-sm">No active sessions on this pedestal.</p>
        ) : (
          <ul className="divide-y divide-line">
            {activeSessions.map((s) => (
              <SessionLine key={s.id} s={s} kind="active">
                <button onClick={() => onStopOpen(s.id)} className="btn-danger btn-sm shrink-0 self-start sm:self-center"
                  disabled={actionLoading === s.id}>
                  Stop
                </button>
              </SessionLine>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Open alarms" count={unackedAlarms.length}>
        {unackedAlarms.length === 0 ? (
          <p className="text-fg-muted text-sm">No open alarms on this pedestal.</p>
        ) : (
          <ul className="divide-y divide-line">
            {unackedAlarms.map((a) => (
              <AlarmLine key={a.id} a={a}>
                <button onClick={() => onAckOpen(a.id)} className="btn-primary btn-sm shrink-0 self-start sm:self-center"
                  disabled={actionLoading === a.id}>
                  Acknowledge
                </button>
              </AlarmLine>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function OccupancyBadge({ occupied }: { occupied: boolean | null }) {
  const o = OCCUPANCY[occupied === null || occupied === undefined ? 'none' : occupied ? 'occupied' : 'vacant']
  return <Status tone={o.tone} icon={o.icon} word={o.word} />
}

function HealthRow({ label, ok }: { label: string; ok: boolean }) {
  const r = REACH[ok ? 'yes' : 'no']
  return (
    <span className="flex items-center gap-2">
      {label}
      <Status tone={r.tone} icon={r.icon} word={r.word} />
    </span>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-semibold border-b-[3px] -mb-px whitespace-nowrap transition-colors ${
        active
          ? 'border-accent text-fg'
          : 'border-transparent text-fg-muted hover:text-fg hover:border-line'
      }`}
    >
      {children}
    </button>
  )
}
