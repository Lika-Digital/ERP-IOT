import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getDashboard,
  type DashboardResponse,
  type PedestalInfo,
  type PedestalHealth,
  type TemperatureReading,
  type SessionInfo,
  type SensorReadings,
} from '../api/dashboard'
import {
  getBerthOccupancy,
  getCameraFrame,
  type BerthOccupancy,
  type BerthOccupancyPayload,
} from '../api/pedestalExt'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import DashboardOverview from '../components/DashboardOverview'
import { useWebSocket } from '../hooks/useWebSocket'
import { num } from '../utils/format'
import Status, { OCCUPANCY, REACH, READING_ALARM, SESSION } from '../components/ui/Status'

type Tab = 'overview' | 'berths'

// ── Per-pedestal berth occupancy state ───────────────────────────────────────

interface OccupancyEntry {
  data: BerthOccupancyPayload | null
  loading: boolean
  error: string | null
  featureUnavailable: boolean
}

// Frame state keyed as "${pedestalId}-${berthId}"
interface FrameEntry {
  objectUrl: string | null
  capturedAt: string | null
  loading: boolean
  error: string | null
}

// ── Component ────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const navigate = useNavigate()
  const id = Number(marinaId)

  const [tab, setTab] = useState<Tab>('overview')
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Berths tab state
  const [occupancy, setOccupancy] = useState<Record<number, OccupancyEntry>>({})
  const [frames, setFrames] = useState<Record<string, FrameEntry>>({})
  const [berthsRefreshing, setBerthsRefreshing] = useState(false)

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true)
      const resp = await getDashboard(id)
      setData(resp)
      setError(null)
    } catch {
      setError('Failed to load dashboard data.')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetchDashboard() }, [fetchDashboard])
  useWebSocket({ marinaId: id, onMessage: () => fetchDashboard() })

  // Fetch occupancy for a single pedestal
  const fetchOccupancy = useCallback(async (pedestalId: number) => {
    setOccupancy((prev) => ({
      ...prev,
      [pedestalId]: { data: null, loading: true, error: null, featureUnavailable: false },
    }))
    try {
      const resp = await getBerthOccupancy(id, pedestalId)
      setOccupancy((prev) => ({
        ...prev,
        [pedestalId]: {
          data: resp.data,
          loading: false,
          error: null,
          featureUnavailable: false,
        },
      }))
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      setOccupancy((prev) => ({
        ...prev,
        [pedestalId]: {
          data: null,
          loading: false,
          error: status === 503 ? null : 'Failed to load occupancy.',
          featureUnavailable: status === 503,
        },
      }))
    }
  }, [id])

  // Refresh all pedestals simultaneously
  const refreshAll = useCallback(async () => {
    if (!data) return
    const pedestals: PedestalInfo[] = Array.isArray(data.pedestals) ? data.pedestals : []
    setBerthsRefreshing(true)
    await Promise.all(pedestals.map((p) => fetchOccupancy(p.id)))
    setBerthsRefreshing(false)
  }, [data, fetchOccupancy])

  // Load occupancy when switching to Berths tab
  useEffect(() => {
    if (tab !== 'berths' || !data) return
    const pedestals: PedestalInfo[] = Array.isArray(data.pedestals) ? data.pedestals : []
    pedestals.forEach((p) => {
      if (!occupancy[p.id]) fetchOccupancy(p.id)
    })
  }, [tab, data]) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch a camera frame for a berth row
  const fetchFrame = useCallback(async (pedestalId: number, berthId: number) => {
    const key = `${pedestalId}-${berthId}`
    setFrames((prev) => ({
      ...prev,
      [key]: { objectUrl: null, capturedAt: null, loading: true, error: null },
    }))
    try {
      // Revoke previous object URL to prevent memory leak
      setFrames((prev) => {
        if (prev[key]?.objectUrl) URL.revokeObjectURL(prev[key].objectUrl!)
        return prev
      })
      const url = await getCameraFrame(id, pedestalId)
      setFrames((prev) => ({
        ...prev,
        [key]: {
          objectUrl: url,
          capturedAt: new Date().toISOString(),
          loading: false,
          error: null,
        },
      }))
    } catch {
      setFrames((prev) => ({
        ...prev,
        [key]: { objectUrl: null, capturedAt: null, loading: false, error: 'Frame unavailable.' },
      }))
    }
  }, [id])

  const pedestals: PedestalInfo[] = Array.isArray(data?.pedestals) ? data!.pedestals : []
  const activeSessions: SessionInfo[] = Array.isArray(data?.active_sessions) ? data!.active_sessions : []
  const pendingSessions: SessionInfo[] = Array.isArray(data?.pending_sessions) ? data!.pending_sessions : []
  const health: Record<string, PedestalHealth> = (data?.health as Record<string, PedestalHealth>) ?? {}
  const tempMap: Record<string, TemperatureReading> = data?.temperature_map ?? {}
  const readingsMap: Record<string, SensorReadings> = data?.readings_map ?? {}
  const marinaTemp = tempMap['0'] ?? null

  return (
    <div className="page" data-page="dashboard">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="page-title">{data?.marina_name || 'Dashboard'}</h1>
          <p className="page-lead">The marina as the collector last saw it</p>
        </div>
      </div>

      {/* D23 (§6.6): map, three cards, cabinets — from the database, no cabinet call */}
      <DashboardOverview marinaId={id} />

      {/* Below: live from the marina's cabinet server, as before 6a */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
        <h2 className="text-lg font-bold tracking-tight">Live from the cabinet server</h2>
        <button onClick={fetchDashboard} className="btn-secondary btn-sm" disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {loading && !data && (
        <div className="flex items-center justify-center h-24">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fg" />
        </div>
      )}
      {error && !data && (
        <div className="notice-danger mb-6" role="alert">
          <p>{error}</p>
          <button className="btn-primary btn-sm mt-3" onClick={fetchDashboard}>Retry</button>
        </div>
      )}

      <StaleDataBanner isStale={data?.is_stale ?? false} onRefresh={fetchDashboard} />

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-line">
        <TabButton active={tab === 'overview'} onClick={() => setTab('overview')}>Overview</TabButton>
        <TabButton active={tab === 'berths'} onClick={() => setTab('berths')}>Berths</TabButton>
      </div>

      {/* ── Overview tab ─────────────────────────────────────────────────── */}
      {tab === 'overview' && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCard label="Pedestals" value={pedestals.length} />
            <StatCard label="Active sessions" value={activeSessions.length} />
            <StatCard label="Waiting for approval" value={pendingSessions.length} />
            {marinaTemp ? (
              <StatCard label="Temperature" value={`${marinaTemp.value}°C`} alarm={marinaTemp.alarm} />
            ) : (
              <StatCard label="Data" value={data?.is_stale ? 'Cached' : 'Live'} />
            )}
          </div>

          {pedestals.length > 0 && (
            <div className="mb-6">
              <h2 className="text-lg font-bold tracking-tight mb-3">Pedestals</h2>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {pedestals.map((p) => {
                  const h = health[String(p.id)]
                  const temp = tempMap[String(p.id)]
                  const readings = readingsMap[String(p.id)]
                  const activeSession = activeSessions.find((s) => s.pedestal_id === p.id)
                  const pendingSession = pendingSessions.find((s) => s.pedestal_id === p.id)
                  return (
                    <PedestalCard
                      key={p.id}
                      pedestal={p}
                      health={h}
                      temperature={temp}
                      readings={readings}
                      activeSession={activeSession}
                      pendingSession={pendingSession}
                      onClick={() => navigate(`/marinas/${id}/pedestals/${p.id}`)}
                    />
                  )
                })}
              </div>
            </div>
          )}

          {pendingSessions.length > 0 && (
            <div className="card mb-6">
              <h2 className="text-lg font-bold tracking-tight mb-2">Waiting for approval ({pendingSessions.length})</h2>
              <ul className="divide-y divide-line">
                {pendingSessions.map((s, i) => (
                  <li key={i} className="py-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold">Session #{s.id} — Pedestal {s.pedestal_id}</p>
                      <p className="text-xs text-fg-muted">{s.type} · socket {s.socket_id ?? '—'}</p>
                    </div>
                    <Status tone={SESSION.pending.tone} icon={SESSION.pending.icon} word={SESSION.pending.word} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {activeSessions.length > 0 && (
            <div className="card mb-6">
              <h2 className="text-lg font-bold tracking-tight mb-2">Active sessions ({activeSessions.length})</h2>
              <ul className="divide-y divide-line">
                {activeSessions.map((s, i) => (
                  <li key={i} className="py-3 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold">Session #{s.id} — Pedestal {s.pedestal_id}</p>
                      <p className="text-xs text-fg-muted">
                        {s.type} · started {s.started_at ? new Date(s.started_at).toLocaleTimeString() : '—'}
                      </p>
                    </div>
                    <Status tone={SESSION.active.tone} icon={SESSION.active.icon} word={SESSION.active.word} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!loading && activeSessions.length === 0 && pendingSessions.length === 0 && pedestals.length === 0 && (
            <div className="card text-center py-10">
              <p className="text-fg-muted">No data available.</p>
            </div>
          )}
        </>
      )}

      {/* ── Berths tab ───────────────────────────────────────────────────── */}
      {tab === 'berths' && (
        <BerthsTab
          pedestals={pedestals}
          occupancy={occupancy}
          frames={frames}
          refreshing={berthsRefreshing}
          onRefreshAll={refreshAll}
          onRefreshPedestal={fetchOccupancy}
          onGetFrame={fetchFrame}
        />
      )}
    </div>
  )
}

// ── Berths Tab ────────────────────────────────────────────────────────────────

function BerthsTab({
  pedestals,
  occupancy,
  frames,
  refreshing,
  onRefreshAll,
  onRefreshPedestal,
  onGetFrame,
}: {
  pedestals: PedestalInfo[]
  occupancy: Record<number, OccupancyEntry>
  frames: Record<string, FrameEntry>
  refreshing: boolean
  onRefreshAll: () => void
  onRefreshPedestal: (pedestalId: number) => void
  onGetFrame: (pedestalId: number, berthId: number) => void
}) {
  if (pedestals.length === 0) {
    return (
      <div className="card text-center py-10">
        <p className="text-fg-muted">No pedestal data available. Refresh the dashboard first.</p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <p className="text-sm text-fg-muted">Camera occupancy for every pedestal — fetched on demand.</p>
        <button
          className="btn-secondary"
          onClick={onRefreshAll}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing…' : 'Refresh all'}
        </button>
      </div>

      <div className="space-y-6">
        {pedestals.map((p) => {
          const entry = occupancy[p.id]
          return (
            <div key={p.id} className="card">
              {/* Pedestal header */}
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-fg">
                  {p.name}
                  <span className="ml-2 text-xs text-fg-muted font-normal">#{p.id}</span>
                </h3>
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => onRefreshPedestal(p.id)}
                  disabled={entry?.loading}
                >
                  {entry?.loading ? 'Loading…' : 'Refresh'}
                </button>
              </div>

              {!entry && (
                <p className="text-sm text-fg-muted italic">Click Refresh to load berth data.</p>
              )}

              {entry?.loading && (
                <div className="flex items-center gap-2 text-sm text-fg-muted">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-fg" />
                  Loading occupancy…
                </div>
              )}

              {entry?.featureUnavailable && (
                <p className="notice-warn">This feature is not available on this pedestal.</p>
              )}

              {entry?.error && (
                <p className="notice-danger" role="alert">{entry.error}</p>
              )}

              {entry && !entry.loading && !entry.featureUnavailable && !entry.error && (
                <>
                  {entry.data?.berths.length === 0 ? (
                    <p className="text-sm text-fg-muted">No berths are configured for this pedestal.</p>
                  ) : (
                    <div className="space-y-2">
                      {entry.data?.berths.map((b) => (
                        <BerthRow
                          key={b.berth_id}
                          berth={b}
                          pedestalId={p.id}
                          frame={frames[`${p.id}-${b.berth_id}`]}
                          onGetFrame={() => onGetFrame(p.id, b.berth_id)}
                        />
                      ))}
                    </div>
                  )}
                  {entry.data?.message && (
                    <p className="text-xs text-fg-muted mt-2 italic">{entry.data.message}</p>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function BerthRow({
  berth,
  pedestalId,
  frame,
  onGetFrame,
}: {
  berth: BerthOccupancy
  pedestalId: number
  frame?: FrameEntry
  onGetFrame: () => void
}) {
  return (
    <div className="border border-line rounded-control p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <OccupancyBadge occupied={berth.occupied} />
          <div>
            <p className="text-sm font-medium text-fg">
              {berth.berth_name ?? `Berth ${berth.berth_id}`}
            </p>
            {berth.last_analyzed && (
              <p className="text-xs text-fg-muted">
                Analysed {new Date(berth.last_analyzed).toLocaleString()}
              </p>
            )}
            {berth.note && (
              <p className="text-xs text-fg-muted italic">{berth.note}</p>
            )}
          </div>
        </div>
        <button
          className="btn-secondary btn-sm shrink-0"
          onClick={onGetFrame}
          disabled={frame?.loading}
        >
          {frame?.loading ? 'Loading…' : 'Get frame'}
        </button>
      </div>

      {/* Inline frame display */}
      {frame && !frame.loading && (
        <div className="mt-3">
          {frame.error ? (
            <p className="notice-danger" role="alert">{frame.error}</p>
          ) : frame.objectUrl ? (
            <div>
              <img
                src={frame.objectUrl}
                alt={`Camera frame — pedestal ${pedestalId}`}
                className="w-full max-w-md rounded-control border border-line"
              />
              {frame.capturedAt && (
                <p className="text-xs text-fg-muted mt-1">
                  Captured {new Date(frame.capturedAt).toLocaleString()}
                </p>
              )}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function OccupancyBadge({ occupied }: { occupied: boolean | null }) {
  const o = OCCUPANCY[occupied === null || occupied === undefined ? 'none' : occupied ? 'occupied' : 'vacant']
  return <Status tone={o.tone} icon={o.icon} word={o.word} />
}

// ── Pedestal Card ─────────────────────────────────────────────────────────────

function PedestalCard({
  pedestal,
  health,
  temperature,
  readings,
  activeSession,
  pendingSession,
  onClick,
}: {
  pedestal: PedestalInfo
  health?: PedestalHealth
  temperature?: TemperatureReading
  readings?: SensorReadings
  activeSession?: SessionInfo
  pendingSession?: SessionInfo
  onClick: () => void
}) {
  // No "Online/Offline" here: the browser would have to work it out from
  // opta_connected, which D2 rules out as proof of life. The berth state on the
  // Berths screen is the server's connection verdict; this card shows the data.
  const tempReading = readings?.temperature_reading ?? (temperature ? { value: temperature.value, alarm: temperature.alarm, at: temperature.at ?? null } : null)

  return (
    <div
      className="card !p-4 flex flex-col gap-3 cursor-pointer hover:border-accent transition-colors"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      data-pedestal={pedestal.id}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-lg font-bold tracking-tight truncate">{pedestal.name}</h3>
          {pedestal.location && <p className="text-xs text-fg-muted truncate">{pedestal.location}</p>}
        </div>
        {health?.last_heartbeat && (
          <span className="text-xs text-fg-muted tabular-nums shrink-0">
            last heard {new Date(health.last_heartbeat).toLocaleTimeString()}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <ReadingCell label="Temperature" value={tempReading ? `${tempReading.value}°C` : null} alarm={tempReading?.alarm} at={tempReading?.at ?? null} />
        <ReadingCell label="Power" value={readings?.power_reading ? `${readings.power_reading.watts} W` : null} sub={readings?.power_reading ? `${num(readings.power_reading.kwh_total, 2, 'kWh')} total` : undefined} at={readings?.power_reading?.at ?? null} />
        <ReadingCell label="Water flow" value={readings?.water_reading ? `${readings.water_reading.lpm} L/min` : null} sub={readings?.water_reading ? `${num(readings.water_reading.total_liters, 0, 'L')} total` : undefined} at={readings?.water_reading?.at ?? null} />
        <ReadingCell label="Moisture" value={readings?.moisture_reading ? `${readings.moisture_reading.value}%` : null} alarm={readings?.moisture_reading?.alarm} at={readings?.moisture_reading?.at ?? null} />
      </div>

      <div className="text-sm">
        {activeSession ? (
          <span className="flex flex-wrap items-center gap-2">
            <Status tone={SESSION.active.tone} icon={SESSION.active.icon} word={SESSION.active.word} />
            session #{activeSession.id} · {activeSession.type}
          </span>
        ) : pendingSession ? (
          <span className="flex flex-wrap items-center gap-2">
            <Status tone={SESSION.pending.tone} icon={SESSION.pending.icon} word={SESSION.pending.word} />
            session #{pendingSession.id}
          </span>
        ) : (
          <span className="text-fg-muted">No active session</span>
        )}
      </div>

      {health && (
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-fg-muted pt-3 border-t border-line">
          <Reach ok={health.camera_reachable} label="Camera" />
          <Reach ok={health.temp_sensor_reachable} label="Temperature sensor" />
        </div>
      )}

      <p className="text-xs text-link font-semibold">View details →</p>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ReadingCell({ label, value, sub, alarm, at }: { label: string; value: string | null; sub?: string; alarm?: boolean; at: string | null }) {
  return (
    <div className={`rounded-control p-3 border ${alarm ? 'bg-st-red-bg border-st-red-line' : 'bg-surface-2 border-transparent'}`}>
      <p className="text-xs text-fg-muted mb-1">{label}</p>
      {value ? (
        <>
          <p className="text-base font-bold leading-tight tabular-nums">{value}</p>
          {alarm && (
            <div className="mt-1"><Status tone={READING_ALARM.tone} icon={READING_ALARM.icon} word={READING_ALARM.word} /></div>
          )}
          {sub && <p className="text-xs text-fg-muted">{sub}</p>}
          {at && <p className="text-xs text-fg-muted">{new Date(at).toLocaleTimeString()}</p>}
        </>
      ) : (
        <p className="text-sm text-fg-muted">—</p>
      )}
    </div>
  )
}

function Reach({ ok, label }: { ok: boolean; label: string }) {
  const r = REACH[ok ? 'yes' : 'no']
  return (
    <span className="flex items-center gap-2">
      {label}
      <Status tone={r.tone} icon={r.icon} word={r.word} />
    </span>
  )
}

function StatCard({ label, value, alarm }: { label: string; value: number | string; alarm?: boolean }) {
  return (
    <div className="card !p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight tabular-nums">{value}</p>
      {alarm && (
        <div className="mt-1"><Status tone={READING_ALARM.tone} icon={READING_ALARM.icon} word={READING_ALARM.word} /></div>
      )}
    </div>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-semibold border-b-[3px] -mb-px transition-colors ${
        active
          ? 'border-accent text-fg'
          : 'border-transparent text-fg-muted hover:text-fg hover:border-line'
      }`}
    >
      {children}
    </button>
  )
}
