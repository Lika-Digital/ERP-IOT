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
    <div className="p-6 space-y-6" data-page="users">
      <h1 className="text-2xl font-bold text-gray-900">Users</h1>

      {error && <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" data-error>{error}</div>}

      {link && (
        <div className="card border-brand-300" data-setup-link>
          <p className="text-sm text-gray-700">
            One-time link for <strong>{link.email}</strong> — shown only now, valid until{' '}
            {new Date(link.setup.expires_at + 'Z').toLocaleString()}. Send it over a channel you trust.
          </p>
          <code className="block mt-2 p-2 bg-gray-50 border rounded text-xs break-all" data-link>{link.setup.link}</code>
          <button className="btn-secondary mt-3" onClick={() => setLink(null)}>Done</button>
        </div>
      )}

      <form onSubmit={create} className="card space-y-3" data-create-user>
        <h2 className="font-semibold text-gray-900">New user</h2>
        <div className="grid sm:grid-cols-3 gap-3">
          <input className="input" type="email" placeholder="e-mail" required value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <input className="input" placeholder="full name" value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            <option value="marina_manager">Marina Manager</option>
            <option value="admin">Admin</option>
          </select>
        </div>
        {form.role === 'marina_manager' && (
          <div className="flex flex-wrap gap-3 text-sm">
            {marinas.map((m) => (
              <label key={m.id} className="flex items-center gap-1">
                <input type="checkbox" checked={form.marina_ids.includes(m.id)}
                  onChange={() => setForm({ ...form, marina_ids: toggleMarina(form.marina_ids, m.id) })} />
                {m.name}
              </label>
            ))}
          </div>
        )}
        <button className="btn-primary" type="submit">Create and get link</button>
      </form>

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="py-2">User</th><th>Role</th><th>Marinas</th><th>Password</th>
              <th>2FA</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t" data-user={u.email}>
                <td className="py-2">
                  <div className="font-medium">{u.full_name || u.email}</div>
                  <div className="text-xs text-gray-500">{u.email}</div>
                </td>
                <td>
                  <select className="input py-1" value={u.role} disabled={u.email === me}
                    onChange={(e) => act(() => updateUser(u.id, { role: e.target.value as Role }))}>
                    <option value="marina_manager">{ROLE_LABEL.marina_manager}</option>
                    <option value="admin">{ROLE_LABEL.admin}</option>
                  </select>
                </td>
                <td className="text-xs">
                  {u.role === 'admin' ? 'all' : marinas.map((m) => (
                    <label key={m.id} className="mr-2 whitespace-nowrap">
                      <input type="checkbox" checked={u.marina_ids.includes(m.id)}
                        onChange={() => act(() => updateUser(u.id, { marina_ids: toggleMarina(u.marina_ids, m.id) }))} />{' '}
                      {m.name}
                    </label>
                  ))}
                </td>
                <td>{u.password_set ? <span className="badge-green">set</span> : <span className="badge-yellow">link pending</span>}</td>
                <td>{u.mfa_enrolled ? <span className="badge-green">linked</span> : <span className="badge-yellow">not linked</span>}</td>
                <td>
                  {!u.is_active ? <span className="badge-gray">disabled</span>
                    : u.locked_until ? <span className="badge-red">locked</span>
                    : <span className="badge-green">active</span>}
                </td>
                <td className="space-x-2 whitespace-nowrap text-right">
                  <button className="btn-secondary py-1 text-xs"
                    onClick={() => act(async () => setLink({ email: u.email, setup: await newSetupLink(u.id) }))}>
                    New link
                  </button>
                  {u.mfa_enrolled && u.email !== me && (
                    <button className="btn-secondary py-1 text-xs" data-reset-mfa={u.email}
                      onClick={async () => {
                        const reason = await askReason(`Reset 2FA za ${u.email}`)
                        if (reason) act(() => resetMfa(u.id, reason))
                      }}>
                      Reset 2FA
                    </button>
                  )}
                  {u.locked_until && (
                    <button className="btn-secondary py-1 text-xs"
                      onClick={async () => {
                        const reason = await askReason(`Otključaj ${u.email}`)
                        if (reason) act(() => unlockUser(u.id, reason))
                      }}>
                      Unlock
                    </button>
                  )}
                  {u.email !== me && (
                    <button className="btn-secondary py-1 text-xs"
                      onClick={() => act(() => updateUser(u.id, { is_active: !u.is_active }))}>
                      {u.is_active ? 'Disable' : 'Enable'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card overflow-x-auto">
        <h2 className="font-semibold text-gray-900 mb-2">Sign-in audit (latest 50)</h2>
        <table className="w-full text-xs">
          <tbody>
            {audit.map((a) => (
              <tr key={a.id} className="border-t">
                <td className="py-1 pr-3 whitespace-nowrap">{new Date(a.created_at + 'Z').toLocaleString()}</td>
                <td className="pr-3">{a.event}</td>
                <td className="pr-3">{a.email_tried}</td>
                <td className="pr-3 text-gray-500">{a.detail}</td>
                <td className="text-gray-400">{a.source_ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
