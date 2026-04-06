import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getDashboard, type DashboardResponse } from '../api/dashboard'
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

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Re-fetch on WebSocket events
  useWebSocket({
    marinaId: id,
    onMessage: () => fetchData(),
  })

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

  const pendingSessions = (data?.pending_sessions as unknown[]) ?? []
  const activeSessions = (data?.active_sessions as unknown[]) ?? []
  const pedestals = (data?.pedestals as unknown[]) ?? []

  return (
    <div className="p-6 max-w-7xl mx-auto">
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
        <StatCard
          label="Pedestals"
          value={Array.isArray(pedestals) ? pedestals.length : '—'}
          icon="⚡"
          color="blue"
        />
        <StatCard
          label="Active Sessions"
          value={Array.isArray(activeSessions) ? activeSessions.length : '—'}
          icon="🔌"
          color="green"
        />
        <StatCard
          label="Pending Approvals"
          value={Array.isArray(pendingSessions) ? pendingSessions.length : '—'}
          icon="⏳"
          color={Array.isArray(pendingSessions) && pendingSessions.length > 0 ? 'yellow' : 'gray'}
        />
        <StatCard
          label="Status"
          value={data?.is_stale ? 'Cached' : 'Live'}
          icon="📡"
          color={data?.is_stale ? 'yellow' : 'green'}
        />
      </div>

      {/* Pending sessions */}
      {Array.isArray(pendingSessions) && pendingSessions.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-lg font-semibold mb-4 text-yellow-700">
            Pending Approvals ({pendingSessions.length})
          </h2>
          <div className="space-y-2">
            {pendingSessions.map((s: unknown, i) => {
              const session = s as Record<string, unknown>
              return (
                <div
                  key={i}
                  className="flex items-center justify-between px-4 py-3 bg-yellow-50 rounded-lg border border-yellow-200"
                >
                  <div>
                    <p className="text-sm font-medium">
                      Session #{String(session.id ?? '?')} — Pedestal {String(session.pedestal_id ?? '?')}
                    </p>
                    <p className="text-xs text-gray-500">
                      Type: {String(session.type ?? 'unknown')} · Socket: {String(session.socket_id ?? '?')}
                    </p>
                  </div>
                  <span className="badge-yellow">pending</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Active sessions */}
      {Array.isArray(activeSessions) && activeSessions.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Active Sessions ({activeSessions.length})</h2>
          <div className="space-y-2">
            {activeSessions.map((s: unknown, i) => {
              const session = s as Record<string, unknown>
              return (
                <div
                  key={i}
                  className="flex items-center justify-between px-4 py-3 bg-green-50 rounded-lg border border-green-200"
                >
                  <div>
                    <p className="text-sm font-medium">
                      Session #{String(session.id ?? '?')} — Pedestal {String(session.pedestal_id ?? '?')}
                    </p>
                    <p className="text-xs text-gray-500">
                      Type: {String(session.type ?? 'unknown')} · Started:{' '}
                      {session.started_at
                        ? new Date(String(session.started_at)).toLocaleTimeString()
                        : '—'}
                    </p>
                  </div>
                  <span className="badge-green">active</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {!loading && Array.isArray(activeSessions) && activeSessions.length === 0 &&
        Array.isArray(pendingSessions) && pendingSessions.length === 0 && (
          <div className="card text-center py-10">
            <p className="text-gray-400">No active or pending sessions.</p>
          </div>
        )}
    </div>
  )
}

function StatCard({
  label,
  value,
  icon,
  color,
}: {
  label: string
  value: number | string
  icon: string
  color: 'blue' | 'green' | 'yellow' | 'gray'
}) {
  const colorMap = {
    blue: 'bg-blue-50 text-blue-700',
    green: 'bg-green-50 text-green-700',
    yellow: 'bg-yellow-50 text-yellow-700',
    gray: 'bg-gray-50 text-gray-600',
  }

  return (
    <div className={`rounded-xl p-4 ${colorMap[color]}`}>
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-sm opacity-75">{label}</div>
    </div>
  )
}
