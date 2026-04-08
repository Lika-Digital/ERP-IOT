import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  getDashboard,
  type DashboardResponse,
  type PedestalInfo,
  type PedestalHealth,
  type TemperatureReading,
  type SessionInfo,
  type SensorReadings,
} from '../api/dashboard'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import { useWebSocket } from '../hooks/useWebSocket'

export default function Dashboard() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const id = Number(marinaId)

  const [data, setData] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
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

  useEffect(() => { fetchData() }, [fetchData])

  useWebSocket({ marinaId: id, onMessage: () => fetchData() })

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
          <button className="btn-primary mt-3" onClick={fetchData}>Retry</button>
        </div>
      </div>
    )
  }

  const pedestals: PedestalInfo[]   = Array.isArray(data?.pedestals) ? data.pedestals : []
  const activeSessions: SessionInfo[] = Array.isArray(data?.active_sessions) ? data.active_sessions : []
  const pendingSessions: SessionInfo[] = Array.isArray(data?.pending_sessions) ? data.pending_sessions : []
  const health: Record<string, PedestalHealth> = (data?.health as Record<string, PedestalHealth>) ?? {}
  const tempMap: Record<string, TemperatureReading> = data?.temperature_map ?? {}
  const readingsMap: Record<string, SensorReadings> = data?.readings_map ?? {}

  // marina-level temperature (pedestal_id = 0)
  const marinaTemp = tempMap['0'] ?? null

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{data?.marina_name || 'Dashboard'}</h1>
          <p className="text-sm text-gray-500 mt-1">Real-time overview</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={data?.is_stale ?? false} onRefresh={fetchData} />

      {/* Stats row */}
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
            icon={marinaTemp.alarm ? '🌡️' : '🌡️'}
            color={marinaTemp.alarm ? 'red' : 'green'}
          />
        ) : (
          <StatCard label="Status" value={data?.is_stale ? 'Cached' : 'Live'} icon="📡" color={data?.is_stale ? 'yellow' : 'green'} />
        )}
      </div>

      {/* Pedestal Cards */}
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
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Pending sessions */}
      {pendingSessions.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-lg font-semibold mb-4 text-yellow-700">
            Pending Approvals ({pendingSessions.length})
          </h2>
          <div className="space-y-2">
            {pendingSessions.map((s, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3 bg-yellow-50 rounded-lg border border-yellow-200">
                <div>
                  <p className="text-sm font-medium">
                    Session #{s.id} — Pedestal {s.pedestal_id}
                  </p>
                  <p className="text-xs text-gray-500">
                    Type: {s.type} · Socket: {s.socket_id ?? '—'}
                  </p>
                </div>
                <span className="badge-yellow">pending</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active sessions */}
      {activeSessions.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-lg font-semibold mb-4">Active Sessions ({activeSessions.length})</h2>
          <div className="space-y-2">
            {activeSessions.map((s, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-3 bg-green-50 rounded-lg border border-green-200">
                <div>
                  <p className="text-sm font-medium">
                    Session #{s.id} — Pedestal {s.pedestal_id}
                  </p>
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
    </div>
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
}: {
  pedestal: PedestalInfo
  health?: PedestalHealth
  temperature?: TemperatureReading
  readings?: SensorReadings
  activeSession?: SessionInfo
  pendingSession?: SessionInfo
}) {
  const isOnline = health?.opta_connected ?? false
  const tempReading = readings?.temperature_reading ?? (temperature ? { value: temperature.value, alarm: temperature.alarm, at: temperature.at ?? null } : null)
  const hasAlarm = (tempReading?.alarm ?? false) || (readings?.moisture_reading?.alarm ?? false)

  return (
    <div className={`card flex flex-col gap-3 ${hasAlarm ? 'border-red-300 bg-red-50' : ''}`}>
      {/* Header */}
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

      {/* Readings grid */}
      <div className="grid grid-cols-2 gap-2">
        {/* Temperature */}
        <ReadingCell
          label="Temperature"
          value={tempReading ? `${tempReading.value}°C` : null}
          alarm={tempReading?.alarm}
          at={tempReading?.at ?? null}
        />

        {/* Power */}
        <ReadingCell
          label="Power"
          value={readings?.power_reading ? `${readings.power_reading.watts} W` : null}
          sub={readings?.power_reading ? `${readings.power_reading.kwh_total?.toFixed(2)} kWh total` : undefined}
          at={readings?.power_reading?.at ?? null}
        />

        {/* Water */}
        <ReadingCell
          label="Water Flow"
          value={readings?.water_reading ? `${readings.water_reading.lpm} L/min` : null}
          sub={readings?.water_reading ? `${readings.water_reading.total_liters?.toFixed(0)} L total` : undefined}
          at={readings?.water_reading?.at ?? null}
        />

        {/* Moisture */}
        <ReadingCell
          label="Moisture"
          value={readings?.moisture_reading ? `${readings.moisture_reading.value}%` : null}
          alarm={readings?.moisture_reading?.alarm}
          at={readings?.moisture_reading?.at ?? null}
        />
      </div>

      {/* Session status */}
      <div className="rounded-lg px-3 py-2 bg-gray-50 text-sm">
        {activeSession ? (
          <span className="text-green-700 font-medium">
            ● Active session #{activeSession.id} · {activeSession.type}
          </span>
        ) : pendingSession ? (
          <span className="text-yellow-700 font-medium">
            ◌ Pending #{pendingSession.id}
          </span>
        ) : (
          <span className="text-gray-400">No active session</span>
        )}
      </div>

      {/* Health indicators */}
      {health && (
        <div className="flex gap-3 text-xs text-gray-500 pt-1 border-t border-gray-100">
          <HealthDot ok={health.camera_reachable} label="Camera" />
          <HealthDot ok={health.temp_sensor_reachable} label="Temp Sensor" />
          {health.last_heartbeat && (
            <span className="ml-auto text-gray-400">
              ♥ {new Date(health.last_heartbeat).toLocaleTimeString()}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function ReadingCell({
  label,
  value,
  sub,
  alarm,
  at,
}: {
  label: string
  value: string | null
  sub?: string
  alarm?: boolean
  at: string | null
}) {
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

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string
  value: number | string
  icon: string
  color: 'blue' | 'green' | 'yellow' | 'gray' | 'red'
}) {
  const colorMap = {
    blue:   'bg-blue-50 text-blue-700',
    green:  'bg-green-50 text-green-700',
    yellow: 'bg-yellow-50 text-yellow-700',
    gray:   'bg-gray-50 text-gray-600',
    red:    'bg-red-50 text-red-700',
  }
  return (
    <div className={`rounded-xl p-4 ${colorMap[color]}`}>
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm opacity-75">{label}</div>
    </div>
  )
}
