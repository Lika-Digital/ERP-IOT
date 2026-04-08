import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  listMarinas,
  createMarina,
  testConnection,
  type Marina,
  type MarinaCreate,
} from '../api/marinas'
import { useAuthStore } from '../store/authStore'

export default function MarinaSelect() {
  const [marinas, setMarinas] = useState<Marina[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<{
    success: boolean
    detail: string
  } | null>(null)

  const [form, setForm] = useState<MarinaCreate>({
    name: '',
    pedestal_api_base_url: '',
    pedestal_service_email: '',
    pedestal_service_password: '',
    timezone: 'UTC',
  })

  const { role } = useAuthStore()
  const navigate = useNavigate()

  const fetchMarinas = async () => {
    try {
      setLoading(true)
      const data = await listMarinas()
      setMarinas(data)
    } catch {
      setError('Failed to load marinas.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMarinas()
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    setError(null)
    try {
      await createMarina(form)
      setShowCreate(false)
      setForm({
        name: '',
        pedestal_api_base_url: '',
        pedestal_service_email: '',
        pedestal_service_password: '',
        timezone: 'UTC',
      })
      await fetchMarinas()
    } catch {
      setError('Failed to create marina.')
    } finally {
      setCreating(false)
    }
  }

  const handleTestConnection = async (marinaId: number) => {
    setTestingId(marinaId)
    setTestResult(null)
    try {
      const result = await testConnection(marinaId)
      setTestResult(result)
    } catch {
      setTestResult({ success: false, detail: 'Request failed — check console.' })
    } finally {
      setTestingId(null)
    }
  }

  const statusColor = (status: string) => {
    if (status === 'active') return 'badge-green'
    if (status === 'maintenance') return 'badge-yellow'
    return 'badge-gray'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Marinas</h1>
          <p className="text-gray-500 text-sm mt-1">Select a marina to manage</p>
        </div>
        {role === 'super_admin' && (
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + Add Marina
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Test connection result banner */}
      {testResult && (
        <div
          className={`mb-4 px-4 py-3 rounded-lg text-sm border ${
            testResult.success
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}
        >
          <strong>{testResult.success ? 'Connection OK' : 'Connection failed'}:</strong>{' '}
          {testResult.detail}
          <button
            className="ml-3 underline text-xs opacity-70"
            onClick={() => setTestResult(null)}
          >
            dismiss
          </button>
        </div>
      )}

      {marinas.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-gray-500">No marinas assigned to your account.</p>
          {role === 'super_admin' && (
            <button className="btn-primary mt-4" onClick={() => setShowCreate(true)}>
              Add your first marina
            </button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {marinas.map((marina) => (
            <div
              key={marina.id}
              className="card hover:border-brand-300 hover:shadow-md transition-all"
            >
              <button
                onClick={() => navigate(`/marinas/${marina.id}/dashboard`)}
                className="block text-left w-full group"
              >
                {marina.logo_url && (
                  <img
                    src={marina.logo_url}
                    alt={marina.name}
                    className="w-12 h-12 rounded-lg object-cover mb-3"
                  />
                )}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="font-semibold text-gray-900 group-hover:text-brand-700 truncate">
                      {marina.name}
                    </h2>
                    {marina.location && (
                      <p className="text-sm text-gray-500 truncate">{marina.location}</p>
                    )}
                    <p className="text-xs text-gray-400 mt-1">{marina.timezone}</p>
                  </div>
                  <span className={statusColor(marina.status)}>{marina.status}</span>
                </div>
                <div className="mt-3 pt-3 border-t border-gray-100 flex items-center text-xs text-gray-400 gap-1">
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 7l5 5m0 0l-5 5m5-5H6"
                    />
                  </svg>
                  Manage
                </div>
              </button>

              {/* Test Connection button — super_admin only */}
              {role === 'super_admin' && (
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <button
                    className="btn-secondary text-xs w-full"
                    disabled={testingId === marina.id}
                    onClick={() => handleTestConnection(marina.id)}
                  >
                    {testingId === marina.id ? 'Testing...' : 'Test Connection'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create marina modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowCreate(false)} />
          <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full p-6 z-10 max-h-[90vh] overflow-y-auto">
            <h2 className="text-lg font-semibold mb-4">Add New Marina</h2>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
                <input
                  className="input"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Marina Adriatica"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                <input
                  className="input"
                  value={form.location ?? ''}
                  onChange={(e) => setForm({ ...form, location: e.target.value })}
                  placeholder="Split, Croatia"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Pedestal API URL *
                </label>
                <input
                  className="input"
                  required
                  type="url"
                  value={form.pedestal_api_base_url}
                  onChange={(e) => setForm({ ...form, pedestal_api_base_url: e.target.value })}
                  placeholder="https://marina.example.com"
                />
              </div>

              {/* Service account credentials */}
              <div className="rounded-lg border border-gray-200 p-4 space-y-3 bg-gray-50">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Pedestal SW Service Account
                </p>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Service Account Email *
                  </label>
                  <input
                    className="input"
                    required
                    type="email"
                    value={form.pedestal_service_email}
                    onChange={(e) =>
                      setForm({ ...form, pedestal_service_email: e.target.value })
                    }
                    placeholder="erp@service.local"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Service Account Password *
                  </label>
                  <input
                    className="input"
                    required
                    type="password"
                    value={form.pedestal_service_password}
                    onChange={(e) =>
                      setForm({ ...form, pedestal_service_password: e.target.value })
                    }
                    placeholder="••••••••"
                    autoComplete="new-password"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
                <input
                  className="input"
                  value={form.timezone ?? 'UTC'}
                  onChange={(e) => setForm({ ...form, timezone: e.target.value })}
                  placeholder="Europe/Zagreb"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowCreate(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? 'Creating...' : 'Create Marina'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
