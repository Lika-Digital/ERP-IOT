import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { getDailyAnalytics, getSessionSummary, type DailyAnalytics, type SessionSummary } from '../api/energy'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import { useToken } from '../theme/useToken'
import { num } from '../utils/format'

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card !p-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold tracking-tight tabular-nums">{value}</p>
    </div>
  )
}

export default function Energy() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const id = Number(marinaId)

  const [daily, setDaily] = useState<DailyAnalytics[]>([])
  const [summary, setSummary] = useState<SessionSummary | null>(null)
  const [isStale, setIsStale] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [c1, c2, c3, grid, muted, surface, line] =
    useToken('chart-1', 'chart-2', 'chart-3', 'chart-grid', 'fg-muted', 'surface', 'line')

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      const [dailyResp, summaryResp] = await Promise.all([
        getDailyAnalytics(id, dateFrom || undefined, dateTo || undefined),
        getSessionSummary(id),
      ])
      setDaily(dailyResp.data ?? [])
      setSummary(summaryResp.data ?? null)
      setIsStale(dailyResp.is_stale || summaryResp.is_stale)
      setError(null)
    } catch {
      setError('Failed to load energy data.')
    } finally {
      setLoading(false)
    }
  }, [id, dateFrom, dateTo])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const totalEnergy = daily.reduce((sum, d) => sum + (d.energy_kwh ?? 0), 0)
  const totalWater = daily.reduce((sum, d) => sum + (d.water_liters ?? 0), 0)
  const axis = { fontSize: 11, fill: muted }
  const tooltip = { contentStyle: { background: surface, border: `1px solid ${line}`, borderRadius: 8 } }

  const chart = (title: string, key: keyof DailyAnalytics, colour: string, name: string, height = 260) => (
    <div className="card">
      <h2 className="text-base font-bold tracking-tight mb-4">{title}</h2>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={daily}>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} />
          <XAxis dataKey="date" tick={axis} stroke={grid} />
          <YAxis tick={axis} stroke={grid} allowDecimals={key !== 'session_count'} />
          <Tooltip {...tooltip} cursor={{ fill: grid, opacity: 0.4 }} />
          <Bar dataKey={key} fill={colour} name={name} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )

  return (
    <div className="page max-w-6xl" data-page="energy">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="page-title">Energy & analytics</h1>
          <p className="page-lead">Consumption as reported by the cabinets</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={isStale} onRefresh={fetchData} />

      {error && <div className="notice-danger mb-4" role="alert">{error}</div>}

      <div className="card mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="label" htmlFor="from">From</label>
            <input id="from" type="date" className="input w-40" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="to">To</label>
            <input id="to" type="date" className="input w-40" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <button className="btn-primary" onClick={fetchData}>Apply</button>
          {(dateFrom || dateTo) && (
            <button className="btn-secondary" onClick={() => { setDateFrom(''); setDateTo('') }}>Clear</button>
          )}
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <Stat label="Total sessions" value={summary.total_sessions ?? '—'} />
          <Stat label="Completed" value={summary.completed_sessions ?? '—'} />
          <Stat label="Total energy" value={num(summary.total_energy_kwh, 1, 'kWh')} />
          <Stat label="Total water" value={num(summary.total_water_liters, 0, 'L')} />
        </div>
      )}

      {daily.length > 0 && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <Stat label="Energy in period" value={num(totalEnergy, 2, 'kWh')} />
          <Stat label="Water in period" value={num(totalWater, 0, 'L')} />
        </div>
      )}

      {daily.length > 0 ? (
        <div className="space-y-6">
          {chart('Daily energy (kWh)', 'energy_kwh', c1, 'Energy (kWh)')}
          {chart('Daily water (litres)', 'water_liters', c2, 'Water (L)')}
          {chart('Sessions per day', 'session_count', c3, 'Sessions', 200)}
        </div>
      ) : (
        !loading && (
          <div className="card text-center py-10">
            <p className="text-fg-muted">No energy data for the selected period.</p>
          </div>
        )
      )}
    </div>
  )
}
