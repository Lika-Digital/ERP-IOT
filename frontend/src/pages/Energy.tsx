import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { getDailyAnalytics, getSessionSummary, type DailyAnalytics, type SessionSummary } from '../api/energy'
import StaleDataBanner from '../components/ui/StaleDataBanner'

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

  const totalEnergy = daily.reduce((sum, d) => sum + d.energy_kwh, 0)
  const totalWater = daily.reduce((sum, d) => sum + d.water_liters, 0)

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Energy & Analytics</h1>
          <p className="text-sm text-gray-500 mt-1">Consumption data from Pedestal SW</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={isStale} onRefresh={fetchData} />

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Date range filter */}
      <div className="card mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">From</label>
            <input
              type="date"
              className="input w-40"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">To</label>
            <input
              type="date"
              className="input w-40"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <button className="btn-primary" onClick={fetchData}>
            Apply
          </button>
          {(dateFrom || dateTo) && (
            <button
              className="btn-secondary"
              onClick={() => { setDateFrom(''); setDateTo('') }}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="card">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Total Sessions</p>
            <p className="text-2xl font-bold text-gray-900">{summary.total_sessions}</p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Completed</p>
            <p className="text-2xl font-bold text-green-600">{summary.completed_sessions}</p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Total Energy</p>
            <p className="text-2xl font-bold text-blue-600">{summary.total_energy_kwh.toFixed(1)} kWh</p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 uppercase tracking-wider">Total Water</p>
            <p className="text-2xl font-bold text-cyan-600">{summary.total_water_liters.toFixed(0)} L</p>
          </div>
        </div>
      )}

      {/* Period totals */}
      {daily.length > 0 && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="card bg-blue-50">
            <p className="text-xs font-medium text-blue-600 uppercase tracking-wider">Period Energy</p>
            <p className="text-2xl font-bold text-blue-800">{totalEnergy.toFixed(2)} kWh</p>
          </div>
          <div className="card bg-cyan-50">
            <p className="text-xs font-medium text-cyan-600 uppercase tracking-wider">Period Water</p>
            <p className="text-2xl font-bold text-cyan-800">{totalWater.toFixed(0)} L</p>
          </div>
        </div>
      )}

      {/* Charts */}
      {daily.length > 0 ? (
        <div className="space-y-6">
          <div className="card">
            <h2 className="text-base font-semibold mb-4">Daily Energy Consumption (kWh)</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="energy_kwh" fill="#3b82f6" name="Energy (kWh)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h2 className="text-base font-semibold mb-4">Daily Water Consumption (Liters)</h2>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="water_liters" fill="#06b6d4" name="Water (L)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h2 className="text-base font-semibold mb-4">Daily Session Count</h2>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="session_count" fill="#8b5cf6" name="Sessions" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        !loading && (
          <div className="card text-center py-10">
            <p className="text-gray-400">No energy data available for the selected period.</p>
          </div>
        )
      )}
    </div>
  )
}
