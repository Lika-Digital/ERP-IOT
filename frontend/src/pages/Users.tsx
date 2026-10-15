import { useEffect, useState, FormEvent } from 'react'
import {
  authAudit,
  createUser,
  listUsers,
  newSetupLink,
  resetMfa,
  unlockUser,
  updateUser,
  type AuthAuditRow,
  type Role,
  type SetupLink,
  type UserRow,
} from '../api/users'
import { listMarinas, type Marina } from '../api/marinas'
import { detailOf } from '../api/auth'
import { askReason } from '../components/ui/ReasonDialog'
import { useAuthStore } from '../store/authStore'
import Status, { ACCOUNT } from '../components/ui/Status'

const ROLE_LABEL: Record<Role, string> = { admin: 'Admin', marina_manager: 'Marina Manager' }

/** Users — Admin only (D20). A new user gets a one-time link, never a password. */
export default function Users() {
  const [users, setUsers] = useState<UserRow[]>([])
  const [marinas, setMarinas] = useState<Marina[]>([])
  const [audit, setAudit] = useState<AuthAuditRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [link, setLink] = useState<{ email: string; setup: SetupLink } | null>(null)
  const [form, setForm] = useState({ email: '', full_name: '', role: 'marina_manager' as Role, marina_ids: [] as number[] })
  const me = useAuthStore((s) => s.email)

  const load = async () => {
    try {
      const [u, m, a] = await Promise.all([listUsers(), listMarinas(), authAudit(50)])
      setUsers(u)
      setMarinas(m)
      setAudit(a)
    } catch (err) {
      setError(detailOf(err, 'Failed to load users.'))
    }
  }
  useEffect(() => { load() }, [])

  const act = async (fn: () => Promise<unknown>) => {
    setError(null)
    try {
      await fn()
      await load()
    } catch (err) {
      setError(detailOf(err, 'The action failed.'))
    }
  }

  const create = (e: FormEvent) => {
    e.preventDefault()
    act(async () => {
      const r = await createUser({
        email: form.email,
        full_name: form.full_name || null,
        role: form.role,
        marina_ids: form.role === 'marina_manager' ? form.marina_ids : [],
      })
      setLink({ email: r.user.email, setup: r.setup })
      setForm({ email: '', full_name: '', role: 'marina_manager', marina_ids: [] })
    })
  }

  const toggleMarina = (ids: number[], id: number) =>
    ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]

  return (
    <div className="page space-y-6" data-page="users">
      <div>
        <h1 className="page-title">Users</h1>
        <p className="page-lead">A new user gets a one-time link, never a password. Everyone signs in with 2FA.</p>
      </div>

      {error && <div className="notice-danger" role="alert" data-error>{error}</div>}

      {link && (
        <div className="card border-accent" data-setup-link>
          <p className="text-sm">
            One-time link for <strong>{link.email}</strong> — shown only now, valid until{' '}
            {new Date(link.setup.expires_at + 'Z').toLocaleString()}. Send it over a channel you trust.
          </p>
          <code className="block mt-2 p-3 bg-surface-2 border border-line rounded-control text-xs break-all font-mono" data-link>
            {link.setup.link}
          </code>
          <button className="btn-secondary mt-3" onClick={() => setLink(null)}>Done</button>
        </div>
      )}

      <form onSubmit={create} className="card space-y-4" data-create-user>
        <h2 className="text-lg font-bold tracking-tight">New user</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <input className="input" type="email" placeholder="e-mail" aria-label="e-mail" required value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input" placeholder="full name" aria-label="full name" value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <select className="input" aria-label="role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            <option value="marina_manager">Marina Manager</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        {form.role === 'marina_manager' && (
          <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
            {marinas.map((m) => (
              <label key={m.id} className="flex items-center gap-2">
                <input type="checkbox" checked={form.marina_ids.includes(m.id)}
                  onChange={() => setForm({ ...form, marina_ids: toggleMarina(form.marina_ids, m.id) })} />
                {m.name}
              </label>
            ))}
          </div>
        )}
        <button className="btn-primary" type="submit">Create and get link</button>
      </form>

      <section className="card">
        <h2 className="text-lg font-bold tracking-tight mb-2">Accounts</h2>
        <ul className="divide-y divide-line">
          {users.map((u) => {
            const pw = ACCOUNT[u.password_set ? 'password_set' : 'link_pending']
            const mfa = ACCOUNT[u.mfa_enrolled ? 'mfa_linked' : 'mfa_missing']
            const st = ACCOUNT[!u.is_active ? 'disabled' : u.locked_until ? 'locked' : 'active']
            return (
              <li key={u.id} className="py-4 space-y-3" data-user={u.email}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold truncate">{u.full_name || u.email}</p>
                    <p className="text-xs text-fg-muted truncate">{u.email}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Status tone={st.tone} icon={st.icon} word={st.word} />
                    <span data-mfa={u.mfa_enrolled ? 'linked' : 'not-linked'}>
                      <Status tone={mfa.tone} icon={mfa.icon} word={mfa.word} />
                    </span>
                    <Status tone={pw.tone} icon={pw.icon} word={pw.word} />
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <select className="input !w-auto py-1.5" aria-label="role" value={u.role} disabled={u.email === me}
                    onChange={(e) => act(() => updateUser(u.id, { role: e.target.value as Role }))}>
                    <option value="marina_manager">{ROLE_LABEL.marina_manager}</option>
                    <option value="admin">{ROLE_LABEL.admin}</option>
                  </select>
                  <div className="text-xs text-fg-muted flex flex-wrap gap-x-3 gap-y-1">
                    {u.role === 'admin' ? 'All marinas' : marinas.map((m) => (
                      <label key={m.id} className="flex items-center gap-1.5 text-fg">
                        <input type="checkbox" checked={u.marina_ids.includes(m.id)}
                          onChange={() => act(() => updateUser(u.id, { marina_ids: toggleMarina(u.marina_ids, m.id) }))} />
                        {m.name}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button className="btn-secondary btn-sm"
                    onClick={() => act(async () => setLink({ email: u.email, setup: await newSetupLink(u.id) }))}>
                    New link
                  </button>
                  {u.mfa_enrolled && u.email !== me && (
                    <button className="btn-secondary btn-sm" data-reset-mfa={u.email}
                      onClick={async () => {
                        const reason = await askReason(`Reset 2FA for ${u.email}`)
                        if (reason) act(() => resetMfa(u.id, reason))
                      }}>
                      Reset 2FA
                    </button>
                  )}
                  {u.locked_until && (
                    <button className="btn-secondary btn-sm"
                      onClick={async () => {
                        const reason = await askReason(`Unlock ${u.email}`)
                        if (reason) act(() => unlockUser(u.id, reason))
                      }}>
                      Unlock
                    </button>
                  )}
                  {u.email !== me && (
                    <button className="btn-secondary btn-sm"
                      onClick={() => act(() => updateUser(u.id, { is_active: !u.is_active }))}>
                      {u.is_active ? 'Disable' : 'Enable'}
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </section>

      <section className="card">
        <h2 className="text-lg font-bold tracking-tight mb-2">Sign-in audit (latest 50)</h2>
        <ul className="divide-y divide-line text-xs">
          {audit.map((a) => (
            <li key={a.id} className="py-2 flex flex-wrap gap-x-3 gap-y-0.5">
              <span className="tabular-nums text-fg-muted">{new Date(a.created_at + 'Z').toLocaleString()}</span>
              <span className="font-semibold">{a.event}</span>
              <span className="break-all">{a.email_tried}</span>
              {a.detail && <span className="text-fg-muted break-all">{a.detail}</span>}
              {a.source_ip && <span className="text-fg-muted font-mono">{a.source_ip}</span>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
