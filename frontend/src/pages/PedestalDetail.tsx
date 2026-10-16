/**
 * PedestalDetail — three-tab view for a single pedestal.
 *
 * Tab 1 — Real Time: health indicators + sessions + alarms for this pedestal
 * Tab 2 — Berths:    occupancy per berth (no camera — D30)
 * Tab 3 — Controls:  allow/deny/stop sessions + acknowledge alarms
 *                    (mirrors PedestalControl look and feel, scoped to this pedestal)
 *
 * P4 (spec §6.13): `?cabinet=` is the ERP's cabinet id; every read and command goes to
 * THAT cabinet. The page is named by the ERP's display_id, never by the name the cabinet
 * sends, and the command buttons exist only when the server says `controllable`.
 */
import { cabinetSentence } from '../api'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { getDashboard, type PedestalHealth, type SessionInfo } from '../api/dashboard'
import { getPendingSessions, getActiveSessions } from '../api/energy'
import { getActiveAlarms, getAlarmLog, acknowledgeAlarm, type AlarmLogEntry } from '../api/alarms'
import { allowSession, askReason, denySession, NO_REASON, stopSession, type ControlCabinet } from '../api/controls'
import {
  getBerthOccupancy,
  type BerthOccupancy,
  type BerthOccupancyPayload,
} from '../api/pedestalExt'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Status, { ALARM_STATE, CABINET_LINK, OCCUPANCY, REACH, SESSION, SIMULATED } from '../components/ui/Status'
import { dateTime, time } from '../utils/format'

type Tab = 'realtime' | 'berths' | 'controls'

// ── Sub-state types ───────────────────────────────────────────────────────────

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
  const [params] = useSearchParams()
  const cid = params.get('cabinet') ? Number(params.get('cabinet')) : undefined

  const [tab, setTab] = useState<Tab>('realtime')

  // Real Time state
  const [cabinet, setCabinet] = useState<ControlCabinet | null>(null)
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
        getDashboard(mid, cid),
        getPendingSessions(mid, cid),
        getActiveSessions(mid, cid),
        getAlarmLog(mid, { pedestal_id: pid, limit: 20 }),
      ])

      setCabinet(dash.cabinet ?? null)
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
  }, [mid, pid, cid])

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
      await allowSession(mid, sessionId, reason, pid, cid)
      await fetchRealTime()
    } catch (err) { setControlError(cabinetSentence(err, 'Failed to allow session.')) }
    finally { setActionLoading(null) }
  }

  const handleDeny = async () => {
    if (!denyDialog) return
    if (denyReason.trim().length < 3) { setControlError(NO_REASON); return }
    setActionLoading(denyDialog.sessionId)
    try {
      await denySession(mid, denyDialog.sessionId, denyReason.trim(), pid, cid)
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
      await stopSession(mid, stopDialog.sessionId, reason, pid, cid)
      setStopDialog(null)
      await fetchRealTime()
    } catch (err) { setControlError(cabinetSentence(err, 'Failed to stop session.')) }
    finally { setActionLoading(null) }
  }

  const handleAckAlarm = async () => {
    if (!ackDialog) return
    setActionLoading(ackDialog.alarmId)
    try {
      await acknowledgeAlarm(mid, ackDialog.alarmId, pid, cid)
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
          <h1 className="page-title truncate" data-live-name>{cabinet ? cabinet.display_id : `Pedestal ${pid}`}</h1>
          {cabinet && (
            <span className="flex flex-wrap items-center gap-2 mt-1">
              <Status tone={CABINET_LINK[cabinet.connection].tone} icon={CABINET_LINK[cabinet.connection].icon} word={CABINET_LINK[cabinet.connection].word} />
              {cabinet.simulated && <Status tone={SIMULATED.tone} icon={SIMULATED.icon} word={SIMULATED.word} />}
            </span>
          )}
        </div>
        {health?.last_heartbeat && (
          <span className="text-xs text-fg-muted tabular-nums self-center">
            last heard {time(health.last_heartbeat)}
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
          occupancy={occupancy}
          onRefreshOccupancy={fetchOccupancy}
        />
      )}

      {tab === 'controls' && (
        <>
          <ControlsTab
            controllable={cabinet?.controllable ?? false}
            noControl={cabinet ? cabinet.sentence : 'No cabinet of this marina is connected in the ERP yet. Commands go only to cabinets the ERP has recorded.'}
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
          {s.started_at && ` · started ${dateTime(s.started_at)}`}
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
        <p className="text-xs text-fg-muted">{dateTime(a.received_at)}{fields && ` · ${fields}`}</p>
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
            <p className="mt-2 text-xs text-fg-muted">Last heartbeat {dateTime(health.last_heartbeat)}</p>
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
// No camera frame, no stream URL (D30, spec §6.12): pictures stay on the cabinet.

function BerthsTab({
  occupancy,
  onRefreshOccupancy,
}: {
  occupancy: OccupancyState
  onRefreshOccupancy: () => void
}) {
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
                {occupancy.data.berths.map((b) => <BerthDetailRow key={b.berth_id} berth={b} />)}
              </div>
            )}
            {occupancy.data.message && <p className="text-xs text-fg-muted mt-2">{occupancy.data.message}</p>}
          </>
        )}
      </section>
    </div>
  )
}

function BerthDetailRow({ berth }: { berth: BerthOccupancy }) {
  return (
    <div className="border border-line rounded-control p-3">
      <div className="flex flex-wrap items-center gap-3">
        <OccupancyBadge occupied={berth.occupied} />
        <div>
          <p className="text-sm font-semibold">{berth.berth_name ?? `Berth ${berth.berth_id}`}</p>
          {berth.last_analyzed && (
            <p className="text-xs text-fg-muted">Analysed {dateTime(berth.last_analyzed)}</p>
          )}
          {berth.note && <p className="text-xs text-fg-muted">{berth.note}</p>}
        </div>
      </div>
    </div>
  )
}

// ── Controls tab ──────────────────────────────────────────────────────────────

function ControlsTab({
  controllable,
  noControl,
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
  controllable: boolean
  noControl: string | null
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
      {!controllable && noControl && <p className="notice-warn mb-4" data-no-control>{noControl}</p>}

      <Section title="Waiting for approval" count={pendingSessions.length}>
        {pendingSessions.length === 0 ? (
          <p className="text-fg-muted text-sm">No sessions are waiting on this pedestal.</p>
        ) : (
          <ul className="divide-y divide-line">
            {pendingSessions.map((s) => (
              <SessionLine key={s.id} s={s} kind="pending">
                {controllable && <div className="flex gap-2 shrink-0">
                  <button onClick={() => onAllow(s.id)} className="btn-primary btn-sm" disabled={actionLoading === s.id}>
                    Allow
                  </button>
                  <button onClick={() => onDenyOpen(s.id)} className="btn-danger btn-sm" disabled={actionLoading === s.id}>
                    Deny
                  </button>
                </div>}
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
                {controllable && <button onClick={() => onStopOpen(s.id)} className="btn-danger btn-sm shrink-0 self-start sm:self-center"
                  disabled={actionLoading === s.id}>
                  Stop
                </button>}
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
                {controllable && <button onClick={() => onAckOpen(a.id)} className="btn-primary btn-sm shrink-0 self-start sm:self-center"
                  disabled={actionLoading === a.id}>
                  Acknowledge
                </button>}
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
