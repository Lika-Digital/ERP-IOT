import { useEffect, useState, FormEvent } from 'react'
import {
  announceWindow,
  cancelWindow,
  decideAlarm,
  listAlarms,
  listCabinets,
  listRules,
  listWindows,
  setRuleMode,
  type CabinetRef,
  type SecurityAlarm,
  type SecurityRule,
  type ServiceWindow,
  type Severity,
} from '../api/security'
import { listMarinas } from '../api/marinas'
import { detailOf } from '../api/auth'
import { askReason } from '../components/ui/ReasonDialog'

const SEVERITY_BADGE: Record<Severity, string> = {
  critical: 'badge-red',
  warning: 'badge-yellow',
  info: 'badge-gray',
}

const utc = (s: string | null) => (s ? new Date(s + 'Z').toLocaleString() : '—')

/** Evidence is shown as data: every value is text in a <code>, never markup (D21: a log line is data). */
function EvidenceList({ alarm }: { alarm: SecurityAlarm }) {
  return (
    <ul className="mt-2 space-y-1 text-xs" data-evidence>
      {alarm.evidence.map((e, i) => (
        <li key={i} className="p-2 bg-gray-50 border rounded">
          <div className="text-gray-500">
            {e.source} · rows {e.row_ids.join(', ')}{e.observed_at ? ` · ${utc(e.observed_at)}` : ''}
          </div>
          <code className="block whitespace-pre-wrap break-all">{JSON.stringify(e.fields, null, 2)}</code>
        </li>
      ))}
    </ul>
  )
}

/** Security — Admin only (spec §6.5, D21). The agent reads and opens alarms; you decide. */
export default function Security() {
  const [alarms, setAlarms] = useState<SecurityAlarm[]>([])
  const [rules, setRules] = useState<SecurityRule[]>([])
  const [windows, setWindows] = useState<ServiceWindow[]>([])
  const [cabinets, setCabinets] = useState<CabinetRef[]>([])
  const [showClosed, setShowClosed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ cabinet_id: 0, from: '', to: '', announced_by: '' })

  const load = async () => {
    try {
      const [a, r, w] = await Promise.all([listAlarms(), listRules(), listWindows()])
      setAlarms(a)
      setRules(r)
      setWindows(w)
      const marinas = await listMarinas()
      const cabs = (await Promise.all(marinas.map((m) => listCabinets(m.id)))).flat()
      setCabinets(cabs)
    } catch (err) {
      setError(detailOf(err, 'Failed to load the security screen.'))
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

  const decide = async (a: SecurityAlarm, state: 'acknowledged' | 'closed') => {
    const note = await askReason(`${state === 'closed' ? 'Close' : 'Acknowledge'}: ${a.title}`)
    if (note) act(() => decideAlarm(a.id, state, note))
  }

  const announce = (e: FormEvent) => {
    e.preventDefault()
    act(async () => {
      await announceWindow({
        cabinet_id: form.cabinet_id,
        from_at: new Date(form.from).toISOString(),
        to_at: new Date(form.to).toISOString(),
        announced_by: form.announced_by,
      })
      setForm({ cabinet_id: 0, from: '', to: '', announced_by: '' })
    })
  }

  const shown = alarms.filter((a) => showClosed || a.state !== 'closed')

  return (
    <div className="p-6 space-y-6" data-page="security">
      <h1 className="text-2xl font-bold text-gray-900">Security</h1>
      <p className="text-sm text-gray-500">
        The security agent only reads and opens alarms with evidence. It never acts: every step is yours.
      </p>

      {error && <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700" data-error>{error}</div>}

      <section className="card space-y-3" data-alarms>
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Alarms</h2>
          <label className="text-sm flex items-center gap-1">
            <input type="checkbox" checked={showClosed} onChange={() => setShowClosed(!showClosed)} />
            show closed
          </label>
        </div>
        {shown.length === 0 && <p className="text-sm text-gray-500" data-no-alarms>No alarms.</p>}
        {shown.map((a) => (
          <div key={a.id} className="border-t pt-3" data-alarm={a.rule_id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className={SEVERITY_BADGE[a.severity]}>{a.severity}</span>{' '}
                <span className="font-medium">{a.title}</span>
                <div className="text-xs text-gray-500">{utc(a.created_at)} · {a.rule_id} · {a.state}</div>
                <p className="text-sm text-gray-700 mt-1">{a.why}</p>
                {a.decision_note && <p className="text-xs text-gray-500 mt-1">Note: {a.decision_note}</p>}
              </div>
              <div className="space-x-2 whitespace-nowrap">
                {a.state === 'open' && (
                  <button className="btn-secondary py-1 text-xs" onClick={() => decide(a, 'acknowledged')}>Acknowledge</button>
                )}
                {a.state !== 'closed' && (
                  <button className="btn-secondary py-1 text-xs" onClick={() => decide(a, 'closed')}>Close</button>
                )}
              </div>
            </div>
            <EvidenceList alarm={a} />
          </div>
        ))}
      </section>

      <section className="card space-y-3" data-service-windows>
        <h2 className="font-semibold text-gray-900">Service windows</h2>
        <p className="text-xs text-gray-500">Without an announced window the door signal cannot be used.</p>
        <form onSubmit={announce} className="grid sm:grid-cols-5 gap-2" data-announce>
          <select className="input" required value={form.cabinet_id}
            onChange={(e) => setForm({ ...form, cabinet_id: Number(e.target.value) })}>
            <option value={0} disabled>cabinet</option>
            {cabinets.map((c) => <option key={c.id} value={c.id}>{c.display_id}</option>)}
          </select>
          <input className="input" type="datetime-local" required value={form.from}
            onChange={(e) => setForm({ ...form, from: e.target.value })} />
          <input className="input" type="datetime-local" required value={form.to}
            onChange={(e) => setForm({ ...form, to: e.target.value })} />
          <input className="input" placeholder="who comes" required value={form.announced_by}
            onChange={(e) => setForm({ ...form, announced_by: e.target.value })} />
          <button className="btn-primary" type="submit" disabled={!form.cabinet_id}>Announce</button>
        </form>
        <table className="w-full text-sm">
          <tbody>
            {windows.map((w) => (
              <tr key={w.id} className="border-t" data-window={w.id}>
                <td className="py-2">{w.display_id}</td>
                <td>{utc(w.from_at)} – {utc(w.to_at)}</td>
                <td>{w.announced_by}</td>
                <td className="text-right">
                  <button className="btn-secondary py-1 text-xs" onClick={() => act(() => cancelWindow(w.id))}>Cancel</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card space-y-2" data-rules>
        <h2 className="font-semibold text-gray-900">Rules</h2>
        <p className="text-xs text-gray-500">A rule in the shadow only logs what it would open. It opens alarms once you switch it on.</p>
        <table className="w-full text-sm">
          <tbody>
            {rules.map((r) => (
              <tr key={r.rule_id} className="border-t" data-rule={r.rule_id}>
                <td className="py-2"><code>{r.rule_id}</code></td>
                <td><span className={SEVERITY_BADGE[r.severity]}>{r.severity}</span></td>
                <td className="text-gray-700">{r.describe}</td>
                <td>{r.mode === 'active' ? <span className="badge-green">active</span> : <span className="badge-gray">shadow</span>}</td>
                <td className="text-right">
                  <button className="btn-secondary py-1 text-xs" data-toggle-rule={r.rule_id}
                    onClick={() => act(() => setRuleMode(r.rule_id, r.mode === 'active' ? 'shadow' : 'active'))}>
                    {r.mode === 'active' ? 'Back to shadow' : 'Switch on'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
