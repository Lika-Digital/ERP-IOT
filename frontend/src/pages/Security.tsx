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
} from '../api/security'
import { listMarinas } from '../api/marinas'
import { detailOf } from '../api/auth'
import { askReason } from '../components/ui/ReasonDialog'
import Status, { SEVERITY, ALARM_STATE, RULE_MODE } from '../components/ui/Status'
import { dateTime } from '../utils/format'

const utc = (s: string | null) => (s ? dateTime(s + 'Z') : '—')

/** Evidence is shown as data: every value is text in a <code>, never markup (D21: a log line is data). */
function EvidenceList({ alarm }: { alarm: SecurityAlarm }) {
  return (
    <ul className="mt-2 space-y-1 text-xs" data-evidence>
      {alarm.evidence.map((e, i) => (
        <li key={i} className="p-3 bg-surface-2 border border-line rounded-control">
          <div className="text-fg-muted mb-1">
            {e.source} · rows {e.row_ids.join(', ')}{e.observed_at ? ` · ${utc(e.observed_at)}` : ''}
          </div>
          <code className="block whitespace-pre-wrap break-all font-mono text-fg">{JSON.stringify(e.fields, null, 2)}</code>
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
    <div className="page space-y-6" data-page="security">
      <div>
        <h1 className="page-title">Security</h1>
        <p className="page-lead">
          The security agent only reads and opens alarms with evidence. It never acts: every step is yours.
        </p>
      </div>

      {error && <div className="notice-danger" role="alert" data-error>{error}</div>}

      <section className="card space-y-4" data-alarms>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold tracking-tight">Alarms</h2>
          <label className="text-sm text-fg-muted flex items-center gap-2">
            <input type="checkbox" className="accent-current" checked={showClosed} onChange={() => setShowClosed(!showClosed)} />
            show closed
          </label>
        </div>
        {shown.length === 0 && <p className="text-sm text-fg-muted" data-no-alarms>No alarms.</p>}
        {shown.map((a) => {
          const sev = SEVERITY[a.severity] ?? SEVERITY.info
          const st = ALARM_STATE[a.state] ?? ALARM_STATE.open
          return (
            <article key={a.id} className="border-t border-line pt-4" data-alarm={a.rule_id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Status tone={sev.tone} icon={sev.icon} word={sev.word} />
                    <Status tone={st.tone} icon={st.icon} word={st.word} />
                  </div>
                  <h3 className="mt-2 font-semibold">{a.title}</h3>
                  <p className="text-xs text-fg-muted">{utc(a.created_at)} · <code>{a.rule_id}</code></p>
                  <p className="text-sm mt-1">{a.why}</p>
                  {a.decision_note && <p className="text-xs text-fg-muted mt-1">Note: {a.decision_note}</p>}
                </div>
                <div className="flex gap-2">
                  {a.state === 'open' && (
                    <button className="btn-primary btn-sm" onClick={() => decide(a, 'acknowledged')}>Acknowledge</button>
                  )}
                  {a.state !== 'closed' && (
                    <button className="btn-secondary btn-sm" onClick={() => decide(a, 'closed')}>Close</button>
                  )}
                </div>
              </div>
              <EvidenceList alarm={a} />
            </article>
          )
        })}
      </section>

      <section className="card space-y-4" data-service-windows>
        <div>
          <h2 className="text-lg font-bold tracking-tight">Service windows</h2>
          <p className="text-xs text-fg-muted">Without an announced window the door signal cannot be used.</p>
        </div>
        <form onSubmit={announce} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5" data-announce>
          <select className="input" required value={form.cabinet_id} aria-label="cabinet"
            onChange={(e) => setForm({ ...form, cabinet_id: Number(e.target.value) })}>
            <option value={0} disabled>cabinet</option>
            {cabinets.map((c) => <option key={c.id} value={c.id}>{c.display_id}</option>)}
          </select>
          <input className="input" type="datetime-local" required value={form.from} aria-label="from"
            onChange={(e) => setForm({ ...form, from: e.target.value })} />
          <input className="input" type="datetime-local" required value={form.to} aria-label="to"
            onChange={(e) => setForm({ ...form, to: e.target.value })} />
          <input className="input" placeholder="who comes" required value={form.announced_by} aria-label="who comes"
            onChange={(e) => setForm({ ...form, announced_by: e.target.value })} />
          <button className="btn-primary" type="submit" disabled={!form.cabinet_id}>Announce</button>
        </form>
        <ul className="divide-y divide-line">
          {windows.map((w) => (
            <li key={w.id} className="py-3 flex flex-wrap items-center justify-between gap-2 text-sm" data-window={w.id}>
              <div className="min-w-0">
                <p className="font-mono font-semibold">{w.display_id}</p>
                <p className="text-fg-muted">{utc(w.from_at)} – {utc(w.to_at)} · {w.announced_by}</p>
              </div>
              <button className="btn-secondary btn-sm" onClick={() => act(() => cancelWindow(w.id))}>Cancel</button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card space-y-4" data-rules>
        <div>
          <h2 className="text-lg font-bold tracking-tight">Rules</h2>
          <p className="text-xs text-fg-muted">A rule in the shadow only logs what it would open. It opens alarms once you switch it on.</p>
        </div>
        <ul className="divide-y divide-line">
          {rules.map((r) => {
            const sev = SEVERITY[r.severity] ?? SEVERITY.info
            const mode = RULE_MODE[r.mode] ?? RULE_MODE.shadow
            return (
              <li key={r.rule_id} className="py-3 flex flex-wrap items-center gap-x-4 gap-y-2" data-rule={r.rule_id}>
                <div className="min-w-0 flex-1 basis-64">
                  <code className="text-sm font-semibold">{r.rule_id}</code>
                  <p className="text-sm text-fg-muted">{r.describe}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Status tone={sev.tone} icon={sev.icon} word={sev.word} />
                  <Status tone={mode.tone} icon={mode.icon} word={mode.word} />
                  <button className="btn-secondary btn-sm" data-toggle-rule={r.rule_id}
                    onClick={() => act(() => setRuleMode(r.rule_id, r.mode === 'active' ? 'shadow' : 'active'))}>
                    {r.mode === 'active' ? 'Back to shadow' : 'Switch on'}
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      </section>
    </div>
  )
}
