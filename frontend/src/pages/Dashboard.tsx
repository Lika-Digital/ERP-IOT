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
import { useWebSocket } from '../hooks/useWebSocket'

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

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="p-6">
        <div className="card bg-red-50 border-red-200">
          <p className="text-red-700">{error}</p>
          <button className="btn-primary mt-3" onClick={fetchDashboard}>Retry</button>
        </div>
      </div>
    )
  }

  const pedestals: PedestalInfo[] = Array.isArray(data?.pedestals) ? data!.pedestals : []
  const activeSessions: SessionInfo[] = Array.isArray(data?.active_sessions) ? data!.active_sessions : []
  const pendingSessions: SessionInfo[] = Array.isArray(data?.pending_sessions) ? data!.pending_sessions : []
  const health: Record<string, PedestalHealth> = (data?.health as Record<string, PedestalHealth>) ?? {}
  const tempMap: Record<string, TemperatureReading> = data?.temperature_map ?? {}
  const readingsMap: Record<string, SensorReadings> = data?.readings_map ?? {}
  const marinaTemp = tempMap['0'] ?? null

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{data?.marina_name || 'Dashboard'}</h1>
          <p className="text-sm text-gray-500 mt-1">Real-time overview</p>
        </div>
        <button onClick={fetchDashboard} className="btn-secondary" disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={data?.is_stale ?? false} onRefresh={fetchDashboard} />

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-gray-200">
        <TabButton active={tab === 'overview'} onClick={() => setTab('overview')}>Overview</TabButton>
        <TabButton active={tab === 'berths'} onClick={() => setTab('berths')}>Berths</TabButton>
      </div>

      {/* ── Overview tab ─────────────────────────────────────────────────── */}
      {tab === 'overview' && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatCard label="Pedestals" value={pedestals.length} icon="⚡" color="blue" />
            <StatCard label="Active Sessions" value={activeSessions.length} icon="🔌" color="green" />
            <StatCard
              label="Pending Approvals"
              value={pendingSessions.length}
              icon="⏳"
              color={pendingSessions.length > 0 ? 'yellow' : 'gray'}
            />
            {marinaTemp ? (
              <StatCard
                label="Temperature"
                value={`${marinaTemp.value}°C`}
                icon="🌡️"
                color={marinaTemp.alarm ? 'red' : 'green'}
              />
            ) : (
              <StatCard label="Status" value={data?.is_stale ? 'Cached' : 'Live'} icon="📡" color={data?.is_stale ? 'yellow' : 'green'} />
            )}
          </div>

          {pedestals.length > 0 && (
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-3">Pedestals</h2>
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
              <h2 className="text-lg font-semibold mb-4 text-yellow-700">
                Pending Approvals ({pendingSessions.length})
              </h2>
              <div className="space-y-2">
                {pendingSessions.map((s, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-3 bg-yellow-50 rounded-lg border border-yellow-200">
                    <div>
                      <p className="text-sm font-medium">Session #{s.id} — Pedestal {s.pedestal_id}</p>
                      <p className="text-xs text-gray-500">Type: {s.type} · Socket: {s.socket_id ?? '—'}</p>
                    </div>
                    <span className="badge-yellow">pending</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeSessions.length > 0 && (
            <div className="card mb-6">
              <h2 className="text-lg font-semibold mb-4">Active Sessions ({activeSessions.length})</h2>
              <div className="space-y-2">
                {activeSessions.map((s, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-3 bg-green-50 rounded-lg border border-green-200">
                    <div>
                      <p className="text-sm font-medium">Session #{s.id} — Pedestal {s.pedestal_id}</p>
                      <p className="text-xs text-gray-500">
                        Type: {s.type} · Started:{' '}
                        {s.started_at ? new Date(s.started_at).toLocaleTimeString() : '—'}
                      </p>
                    </div>
                    <span className="badge-green">active</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!loading && activeSessions.length === 0 && pendingSessions.length === 0 && pedestals.length === 0 && (
            <div className="card text-center py-10">
              <p className="text-gray-400">No data available.</p>
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
        <p className="text-gray-400">No pedestal data available. Refresh the dashboard first.</p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">Berth occupancy across all pedestals — fetched on demand.</p>
        <button
          className="btn-secondary"
          onClick={onRefreshAll}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing...' : 'Refresh All'}
        </button>
      </div>

      <div className="space-y-6">
        {pedestals.map((p) => {
          const entry = occupancy[p.id]
          return (
            <div key={p.id} className="card">
              {/* Pedestal header */}
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-gray-900">
                  {p.name}
                  <span className="ml-2 text-xs text-gray-400 font-normal">#{p.id}</span>
                </h3>
                <button
                  className="btn-secondary py-1 text-xs"
                  onClick={() => onRefreshPedestal(p.id)}
                  disabled={entry?.loading}
                >
                  {entry?.loading ? 'Loading...' : 'Refresh'}
                </button>
              </div>

              {!entry && (
                <p className="text-sm text-gray-400 italic">Click Refresh to load berth data.</p>
              )}

              {entry?.loading && (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand-600" />
                  Loading occupancy...
                </div>
              )}

              {entry?.featureUnavailable && (
                <p className="text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded-lg">
                  Feature not available on this pedestal
                </p>
              )}

              {entry?.error && (
                <p className="text-sm text-red-600">{entry.error}</p>
              )}

              {entry && !entry.loading && !entry.featureUnavailable && !entry.error && (
                <>
                  {entry.data?.berths.length === 0 ? (
                    <p className="text-sm text-gray-400 italic">No berths configured for this pedestal</p>
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
                    <p className="text-xs text-gray-400 mt-2 italic">{entry.data.message}</p>
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
    <div className="border border-gray-100 rounded-lg p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <OccupancyBadge occupied={berth.occupied} />
          <div>
            <p className="text-sm font-medium text-gray-800">
              {berth.berth_name ?? `Berth ${berth.berth_id}`}
            </p>
            {berth.last_analyzed && (
              <p className="text-xs text-gray-400">
                Analyzed: {new Date(berth.last_analyzed).toLocaleString()}
              </p>
            )}
            {berth.note && (
              <p className="text-xs text-gray-400 italic">{berth.note}</p>
            )}
          </div>
        </div>
        <button
          className="btn-secondary py-1 text-xs shrink-0"
          onClick={onGetFrame}
          disabled={frame?.loading}
        >
          {frame?.loading ? 'Loading...' : 'Get Frame'}
        </button>
      </div>

      {/* Inline frame display */}
      {frame && !frame.loading && (
        <div className="mt-3">
          {frame.error ? (
            <p className="text-xs text-red-500">{frame.error}</p>
          ) : frame.objectUrl ? (
            <div>
              <img
                src={frame.objectUrl}
                alt={`Camera frame — pedestal ${pedestalId}`}
                className="w-full max-w-md rounded-lg border border-gray-200"
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
  const isOnline = health?.opta_connected ?? false
  const tempReading = readings?.temperature_reading ?? (temperature ? { value: temperature.value, alarm: temperature.alarm, at: temperature.at ?? null } : null)
  const hasAlarm = (tempReading?.alarm ?? false) || (readings?.moisture_reading?.alarm ?? false)

  return (
    <div
      className={`card flex flex-col gap-3 cursor-pointer hover:shadow-md transition-shadow ${hasAlarm ? 'border-red-300 bg-red-50' : ''}`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">{pedestal.name}</h3>
          {pedestal.location && <p className="text-xs text-gray-400">{pedestal.location}</p>}
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
          isOnline ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
        }`}>
          {isOnline ? 'Online' : 'Offline'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <ReadingCell label="Temperature" value={tempReading ? `${tempReading.value}°C` : null} alarm={tempReading?.alarm} at={tempReading?.at ?? null} />
        <ReadingCell label="Power" value={readings?.power_reading ? `${readings.power_reading.watts} W` : null} sub={readings?.power_reading ? `${readings.power_reading.kwh_total?.toFixed(2)} kWh total` : undefined} at={readings?.power_reading?.at ?? null} />
        <ReadingCell label="Water Flow" value={readings?.water_reading ? `${readings.water_reading.lpm} L/min` : null} sub={readings?.water_reading ? `${readings.water_reading.total_liters?.toFixed(0)} L total` : undefined} at={readings?.water_reading?.at ?? null} />
        <ReadingCell label="Moisture" value={readings?.moisture_reading ? `${readings.moisture_reading.value}%` : null} alarm={readings?.moisture_reading?.alarm} at={readings?.moisture_reading?.at ?? null} />
      </div>

      <div className="rounded-lg px-3 py-2 bg-gray-50 text-sm">
        {activeSession ? (
          <span className="text-green-700 font-medium">● Active session #{activeSession.id} · {activeSession.type}</span>
        ) : pendingSession ? (
          <span className="text-yellow-700 font-medium">◌ Pending #{pendingSession.id}</span>
        ) : (
          <span className="text-gray-400">No active session</span>
        )}
      </div>

      {health && (
        <div className="flex gap-3 text-xs text-gray-500 pt-1 border-t border-gray-100">
          <HealthDot ok={health.camera_reachable} label="Camera" />
          <HealthDot ok={health.temp_sensor_reachable} label="Temp Sensor" />
          {health.last_heartbeat && (
            <span className="ml-auto text-gray-400">♥ {new Date(health.last_heartbeat).toLocaleTimeString()}</span>
          )}
        </div>
      )}

      <p className="text-xs text-brand-600 font-medium">View details →</p>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ReadingCell({ label, value, sub, alarm, at }: { label: string; value: string | null; sub?: string; alarm?: boolean; at: string | null }) {
  return (
    <div className={`rounded-lg p-3 ${alarm ? 'bg-red-100' : 'bg-gray-50'}`}>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      {value ? (
        <>
          <p className={`text-base font-bold leading-tight ${alarm ? 'text-red-600' : 'text-gray-800'}`}>
            {value}{alarm && <span className="ml-1 text-xs">⚠️</span>}
          </p>
          {sub && <p className="text-xs text-gray-400">{sub}</p>}
          {at && <p className="text-xs text-gray-400">{new Date(at).toLocaleTimeString()}</p>}
        </>
      ) : (
        <p className="text-sm text-gray-400">—</p>
      )}
    </div>
  )
}

function HealthDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-green-500' : 'bg-red-400'}`} />
      {label}
    </span>
  )
}

function StatCard({ label, value, icon, color }: { label: string; value: number | string; icon: string; color: 'blue' | 'green' | 'yellow' | 'gray' | 'red' }) {
  const colorMap = { blue: 'bg-blue-50 text-blue-700', green: 'bg-green-50 text-green-700', yellow: 'bg-yellow-50 text-yellow-700', gray: 'bg-gray-50 text-gray-600', red: 'bg-red-50 text-red-700' }
  return (
    <div className={`rounded-xl p-4 ${colorMap[color]}`}>
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm opacity-75">{label}</div>
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
