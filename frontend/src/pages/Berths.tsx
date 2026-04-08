import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { listBerths } from '../api/dashboard'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import { useWebSocket } from '../hooks/useWebSocket'

interface Berth {
  id: number
  name?: string
  pedestal_id?: number
  occupied?: boolean
  vessel_name?: string
  vessel_length?: number
  status?: string
  [key: string]: unknown
}

export default function Berths() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const id = Number(marinaId)

  const [berths, setBerths] = useState<Berth[]>([])
  const [isStale, setIsStale] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      const resp = await listBerths(id)
      const data = resp as { berths?: Berth[]; is_stale?: boolean }
      setBerths(Array.isArray(data?.berths) ? data.berths : [])
      setIsStale(!!data?.is_stale)
      setError(null)
    } catch {
      setError('Failed to load berth data.')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetchData() }, [fetchData])
  useWebSocket({ marinaId: id, onMessage: () => fetchData() })

  if (loading && berths.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
      </div>
    )
  }

  const occupied = berths.filter((b) => b.occupied)
  const free = berths.filter((b) => !b.occupied)

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Berths</h1>
          <p className="text-sm text-gray-500 mt-1">Berth occupancy overview</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={isStale} onRefresh={fetchData} />

      {error && (
        <div className="card bg-red-50 border-red-200 mb-6">
          <p className="text-red-700">{error}</p>
          <button className="btn-primary mt-3" onClick={fetchData}>Retry</button>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="rounded-xl p-4 bg-blue-50 text-blue-700">
          <div className="text-2xl mb-1">⚓</div>
          <div className="text-2xl font-bold">{berths.length}</div>
          <div className="text-sm opacity-75">Total Berths</div>
        </div>
        <div className="rounded-xl p-4 bg-red-50 text-red-700">
          <div className="text-2xl mb-1">🚢</div>
          <div className="text-2xl font-bold">{occupied.length}</div>
          <div className="text-sm opacity-75">Occupied</div>
        </div>
        <div className="rounded-xl p-4 bg-green-50 text-green-700">
          <div className="text-2xl mb-1">✓</div>
          <div className="text-2xl font-bold">{free.length}</div>
          <div className="text-sm opacity-75">Available</div>
        </div>
      </div>

      {berths.length === 0 ? (
        <div className="card text-center py-10">
          <p className="text-gray-400">No berth data available.</p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {berths.map((berth, i) => (
            <div
              key={berth.id ?? i}
              className={`card flex flex-col gap-2 ${
                berth.occupied ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'
              }`}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-900">
                  {berth.name ?? `Berth ${berth.id ?? i + 1}`}
                </h3>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  berth.occupied
                    ? 'bg-red-100 text-red-700'
                    : 'bg-green-100 text-green-700'
                }`}>
                  {berth.occupied ? 'Occupied' : 'Free'}
                </span>
              </div>

              {berth.pedestal_id && (
                <p className="text-xs text-gray-500">Pedestal #{berth.pedestal_id}</p>
              )}

              {berth.vessel_name && (
                <p className="text-sm text-gray-700">
                  <span className="font-medium">Vessel:</span> {berth.vessel_name}
                  {berth.vessel_length ? ` (${berth.vessel_length}m)` : ''}
                </p>
              )}

              {berth.status && berth.status !== 'free' && berth.status !== 'occupied' && (
                <p className="text-xs text-gray-400 capitalize">{berth.status}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
