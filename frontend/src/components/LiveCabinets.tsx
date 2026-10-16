/**
 * The chosen cabinet, live — moved here from the dashboard in 6b (D23: the dashboard
 * shows nothing live). Since P4 (spec §6.13) it is read through THAT cabinet's own
 * client and named by the ERP's display_id, never by the name the cabinet sends about
 * itself ("Ormar 1 · Krk" was the simulator's). Each card leads to the cabinet's
 * detail. No camera here (D30).
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ControlCabinet } from '../api/controls'
import {
  getDashboard,
  type DashboardResponse,
  type PedestalHealth,
  type PedestalInfo,
  type SensorReadings,
  type SessionInfo,
  type TemperatureReading,
} from '../api/dashboard'
import { useWebSocket } from '../hooks/useWebSocket'
import { num, time } from '../utils/format'
import StaleDataBanner from './ui/StaleDataBanner'
import Status, { READING_ALARM, REACH, SESSION } from './ui/Status'

export default function LiveCabinets({ marinaId, cabinet }: { marinaId: number; cabinet: ControlCabinet }) {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setData(await getDashboard(marinaId, cabinet.id))
      setError(null)
    } catch {
      setError('The cabinet server could not be read.')
    } finally {
      setLoading(false)
    }
  }, [marinaId, cabinet.id])

  useEffect(() => { load() }, [load])
  useWebSocket({ marinaId, onMessage: () => load() })

  const pedestals: PedestalInfo[] = Array.isArray(data?.pedestals) ? data!.pedestals : []
  const active: SessionInfo[] = Array.isArray(data?.active_sessions) ? data!.active_sessions : []
  const pending: SessionInfo[] = Array.isArray(data?.pending_sessions) ? data!.pending_sessions : []
  const health = (data?.health as Record<string, PedestalHealth>) ?? {}
  const temps: Record<string, TemperatureReading> = data?.temperature_map ?? {}
  const readings: Record<string, SensorReadings> = data?.readings_map ?? {}

  return (
    <section className="card mb-6" data-live-cabinets>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 className="text-lg font-bold tracking-tight">{cabinet.display_id} — live</h2>
        <button onClick={load} className="btn-secondary btn-sm" disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      <StaleDataBanner isStale={data?.is_stale ?? false} onRefresh={load} />
      {error && !data && <div className="notice-danger mb-4" role="alert">{error}</div>}
      {loading && !data && <p className="text-sm text-fg-muted">Reading the cabinet server…</p>}
      {data && pedestals.length === 0 && <p className="text-sm text-fg-muted">{cabinet.display_id} reported nothing.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {pedestals.map((p) => (
          <PedestalCard key={p.id} pedestal={p} name={pedestals.length > 1 ? `${cabinet.display_id} · pedestal ${p.id}` : cabinet.display_id}
            health={health[String(p.id)]}
            temperature={temps[String(p.id)]} readings={readings[String(p.id)]}
            activeSession={active.find((s) => s.pedestal_id === p.id)}
            pendingSession={pending.find((s) => s.pedestal_id === p.id)}
            onClick={() => navigate(`/marinas/${marinaId}/pedestals/${p.id}?cabinet=${cabinet.id}`)} />
        ))}
      </div>
    </section>
  )
}

function PedestalCard({
  pedestal, name, health, temperature, readings, activeSession, pendingSession, onClick,
}: {
  pedestal: PedestalInfo
  name: string
  health?: PedestalHealth
  temperature?: TemperatureReading
  readings?: SensorReadings
  activeSession?: SessionInfo
  pendingSession?: SessionInfo
  onClick: () => void
}) {
  // No "Online/Offline" worked out here from opta_connected (D2): the server's verdict
  // per cabinet is on the dashboard (O51); this card shows the data.
  const temp = readings?.temperature_reading
    ?? (temperature ? { value: temperature.value, alarm: temperature.alarm, at: temperature.at ?? null } : null)
  return (
    <div className="rounded-card border border-line p-4 flex flex-col gap-3 cursor-pointer hover:border-accent transition-colors"
      onClick={onClick} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && onClick()}
      data-pedestal={pedestal.id}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-bold tracking-tight truncate" data-live-name>{name}</h3>
        </div>
        {health?.last_heartbeat && (
          <span className="text-xs text-fg-muted tabular-nums shrink-0">last heard {time(health.last_heartbeat)}</span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <ReadingCell label="Temperature" value={temp ? `${num(temp.value, 1)}°C` : null} alarm={temp?.alarm} at={temp?.at ?? null} />
        <ReadingCell label="Power" value={readings?.power_reading ? `${num(readings.power_reading.watts, 0)} W` : null}
          sub={readings?.power_reading ? `${num(readings.power_reading.kwh_total, 2, 'kWh')} total` : undefined}
          at={readings?.power_reading?.at ?? null} />
        <ReadingCell label="Water flow" value={readings?.water_reading ? `${num(readings.water_reading.lpm, 1)} L/min` : null}
          sub={readings?.water_reading ? `${num(readings.water_reading.total_liters, 0, 'L')} total` : undefined}
          at={readings?.water_reading?.at ?? null} />
        <ReadingCell label="Moisture" value={readings?.moisture_reading ? `${num(readings.moisture_reading.value, 0)}%` : null}
          alarm={readings?.moisture_reading?.alarm} at={readings?.moisture_reading?.at ?? null} />
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
          {/* reachability is a state, not a picture — allowed by D30 */}
          <Reach ok={health.camera_reachable} label="Camera" />
          <Reach ok={health.temp_sensor_reachable} label="Temperature sensor" />
        </div>
      )}
      <p className="text-xs text-link font-semibold">View details →</p>
    </div>
  )
}

function ReadingCell({ label, value, sub, alarm, at }: { label: string; value: string | null; sub?: string; alarm?: boolean; at: string | null }) {
  return (
    <div className={`rounded-control p-3 border ${alarm ? 'bg-st-red-bg border-st-red-line' : 'bg-surface-2 border-transparent'}`}>
      <p className="text-xs text-fg-muted mb-1">{label}</p>
      {value ? (
        <>
          <p className="text-base font-bold leading-tight tabular-nums">{value}</p>
          {alarm && <div className="mt-1"><Status tone={READING_ALARM.tone} icon={READING_ALARM.icon} word={READING_ALARM.word} /></div>}
          {sub && <p className="text-xs text-fg-muted">{sub}</p>}
          {at && <p className="text-xs text-fg-muted">{time(at)}</p>}
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
