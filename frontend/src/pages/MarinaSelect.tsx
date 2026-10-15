import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  listMarinas,
  createMarina,
  updateMarina,
  testConnection,
  type Marina,
  type MarinaCreate,
  type MarinaUpdate,
} from '../api/marinas'
import { useAuthStore } from '../store/authStore'
import Status, { MARINA, CONNECTION } from '../components/ui/Status'

const EMPTY_CREATE: MarinaCreate = {
  name: '',
  pedestal_api_base_url: '',
  pedestal_service_email: '',
  pedestal_service_password: '',
  timezone: 'UTC',
}

export default function MarinaSelect() {
  const [marinas, setMarinas] = useState<Marina[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create modal
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createForm, setCreateForm] = useState<MarinaCreate>({ ...EMPTY_CREATE })

  // Edit modal
  const [editingMarina, setEditingMarina] = useState<Marina | null>(null)
  const [editForm, setEditForm] = useState<MarinaUpdate>({})
  const [editPassword, setEditPassword] = useState('')
  const [saving, setSaving] = useState(false)

  // Test connection
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<{ success: boolean; detail: string } | null>(null)

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

  useEffect(() => { fetchMarinas() }, [])

  // ── Create ────────────────────────────────────────────────────────────────

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    setError(null)
    try {
      await createMarina(createForm)
      setShowCreate(false)
      setCreateForm({ ...EMPTY_CREATE })
      await fetchMarinas()
    } catch {
      setError('Failed to create marina.')
    } finally {
      setCreating(false)
    }
  }

  // ── Edit ──────────────────────────────────────────────────────────────────

  const openEdit = (marina: Marina) => {
    setEditingMarina(marina)
    setEditForm({
      name: marina.name,
      location: marina.location ?? '',
      timezone: marina.timezone,
      pedestal_api_base_url: marina.pedestal_api_base_url ?? '',
      pedestal_service_email: marina.pedestal_service_email ?? '',
      status: marina.status,
    })
    setEditPassword('')
    setTestResult(null)
  }

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingMarina) return
    setSaving(true)
    setError(null)
    try {
      const payload: MarinaUpdate = { ...editForm }
      if (editPassword) payload.pedestal_service_password = editPassword
      await updateMarina(editingMarina.id, payload)
      setEditingMarina(null)
      await fetchMarinas()
    } catch {
      setError('Failed to save marina.')
    } finally {
      setSaving(false)
    }
  }

  // ── Test connection ───────────────────────────────────────────────────────

  const handleTestConnection = async (marinaId: number) => {
    setTestingId(marinaId)
    setTestResult(null)
    try {
      const result = await testConnection(marinaId)
      setTestResult(result)
    } catch {
      setTestResult({ success: false, detail: 'Request failed — check network.' })
    } finally {
      setTestingId(null)
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────


  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-fg" />
      </div>
    )
  }

  return (
    <div className="page max-w-5xl" data-page="marinas">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="page-title">Marinas</h1>
          <p className="page-lead">Select a marina to manage</p>
        </div>
        {role === 'admin' && (
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + Add marina
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="notice-danger mb-4" role="alert">{error}</div>
      )}

      {/* Test connection result */}
      {testResult && (
        <div className="card !p-4 mb-4 flex flex-wrap items-start justify-between gap-3" role="status" data-connection-test>
          <div className="space-y-1 min-w-0">
            {(() => { const c = CONNECTION[testResult.success ? 'ok' : 'failed']
              return <Status tone={c.tone} icon={c.icon} word={c.word} /> })()}
            <p className="text-sm text-fg-muted break-words">{testResult.detail}</p>
          </div>
          <button className="btn-secondary btn-sm shrink-0" onClick={() => setTestResult(null)}>Dismiss</button>
        </div>
      )}

      {/* Marina grid */}
      {marinas.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-fg-muted">No marinas assigned to your account.</p>
          {role === 'admin' && (
            <button className="btn-primary mt-4" onClick={() => setShowCreate(true)}>
              Add your first marina
            </button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {marinas.map((marina) => (
            <div key={marina.id} className="card hover:border-accent transition-colors flex flex-col" data-marina={marina.id}>
              {/* Click to navigate */}
              <button
                onClick={() => navigate(`/marinas/${marina.id}/dashboard`)}
                className="block text-left w-full group flex-1"
              >
                {marina.logo_url && (
                  <img src={marina.logo_url} alt={marina.name} className="w-12 h-12 rounded-lg object-cover mb-3" />
                )}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="text-lg font-bold tracking-tight group-hover:text-link truncate">
                      {marina.name}
                    </h2>
                    {marina.location && (
                      <p className="text-sm text-fg-muted truncate">{marina.location}</p>
                    )}
                    <p className="text-xs text-fg-muted mt-1">{marina.timezone}</p>
                  </div>
                  {(() => { const m = MARINA[marina.status] ?? MARINA.inactive
                    return <Status tone={m.tone} icon={m.icon} word={m.word} /> })()}
                </div>
                <div className="mt-3 pt-3 border-t border-line flex items-center text-xs text-fg-muted gap-1">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                  Manage
                </div>
              </button>

              {/* Admin actions */}
              {role === 'admin' && (
                <div className="mt-3 pt-3 border-t border-line flex gap-2">
                  <button
                    className="btn-secondary text-xs flex-1"
                    onClick={() => openEdit(marina)}
                  >
                    Edit
                  </button>
                  <button
                    className="btn-secondary text-xs flex-1"
                    disabled={testingId === marina.id}
                    onClick={() => handleTestConnection(marina.id)}
                  >
                    {testingId === marina.id ? 'Testing…' : 'Test connection'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Create marina modal ─────────────────────────────────────────────── */}
      {showCreate && (
        <MarinaModal
          title="Add marina"
          submitLabel={creating ? 'Creating…' : 'Create marina'}
          disabled={creating}
          onClose={() => setShowCreate(false)}
          onSubmit={handleCreate}
        >
          <MarinaFormFields
            values={createForm}
            onChange={(patch) => setCreateForm((f) => ({ ...f, ...patch }))}
            passwordRequired
          />
        </MarinaModal>
      )}

      {/* ── Edit marina modal ───────────────────────────────────────────────── */}
      {editingMarina && (
        <MarinaModal
          title={`Edit — ${editingMarina.name}`}
          submitLabel={saving ? 'Saving…' : 'Save changes'}
          disabled={saving}
          onClose={() => setEditingMarina(null)}
          onSubmit={handleEdit}
        >
          <MarinaFormFields
            values={editForm as MarinaCreate}
            onChange={(patch) => setEditForm((f) => ({ ...f, ...patch }))}
            passwordRequired={false}
            passwordValue={editPassword}
            onPasswordChange={setEditPassword}
            isEdit
          />
        </MarinaModal>
      )}
    </div>
  )
}

// ── Shared modal shell ──────────────────────────────────────────────────────

function MarinaModal({
  title,
  submitLabel,
  disabled,
  onClose,
  onSubmit,
  children,
}: {
  title: string
  submitLabel: string
  disabled: boolean
  onClose: () => void
  onSubmit: (e: React.FormEvent) => void
  children: React.ReactNode
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-surface text-fg rounded-card shadow-card border border-line max-w-lg w-full p-6 z-10 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold tracking-tight">{title}</h2>
          <button onClick={onClose} className="text-fg-muted hover:text-fg text-2xl leading-none" aria-label="Close">&times;</button>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          {children}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={disabled}>
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Shared form fields ──────────────────────────────────────────────────────

function MarinaFormFields({
  values,
  onChange,
  passwordRequired,
  passwordValue,
  onPasswordChange,
  isEdit = false,
}: {
  values: MarinaCreate
  onChange: (patch: Partial<MarinaCreate>) => void
  passwordRequired: boolean
  passwordValue?: string
  onPasswordChange?: (v: string) => void
  isEdit?: boolean
}) {
  return (
    <>
      <div>
        <label className="label">Name *</label>
        <input
          className="input"
          required
          value={values.name}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="Marina Adriatica"
        />
      </div>

      <div>
        <label className="label">Location</label>
        <input
          className="input"
          value={values.location ?? ''}
          onChange={(e) => onChange({ location: e.target.value })}
          placeholder="Split, Croatia"
        />
      </div>

      <div>
        <label className="label">Timezone</label>
        <input
          className="input"
          value={values.timezone ?? 'UTC'}
          onChange={(e) => onChange({ timezone: e.target.value })}
          placeholder="Europe/Zagreb"
        />
      </div>

      {/* Pedestal SW integration */}
      <div className="rounded-control border border-line p-4 space-y-4 bg-surface-2">
        <p className="text-xs font-semibold text-fg-muted uppercase tracking-wide">
          Cabinet connection
        </p>

        <div>
          <label className="label">API base URL *</label>
          <input
            className="input"
            required
            type="url"
            value={values.pedestal_api_base_url}
            onChange={(e) => onChange({ pedestal_api_base_url: e.target.value })}
            placeholder="https://marina.example.com"
          />
        </div>

        <div>
          <label className="label">
            Service account e-mail *
          </label>
          <input
            className="input"
            required
            type="email"
            value={values.pedestal_service_email}
            onChange={(e) => onChange({ pedestal_service_email: e.target.value })}
            placeholder="erp@service.local"
            autoComplete="off"
          />
        </div>

        <div>
          <label className="label">
            Service account password {isEdit ? '' : '*'}
          </label>
          <input
            className="input"
            required={passwordRequired}
            type="password"
            value={isEdit ? (passwordValue ?? '') : values.pedestal_service_password}
            onChange={(e) =>
              isEdit
                ? onPasswordChange?.(e.target.value)
                : onChange({ pedestal_service_password: e.target.value })
            }
            placeholder={isEdit ? '••••••••  (leave blank to keep current)' : '••••••••'}
            autoComplete="new-password"
          />
          {isEdit && (
            <p className="text-xs text-fg-muted mt-1">
              Leave blank to keep the existing password.
            </p>
          )}
        </div>
      </div>
    </>
  )
}
