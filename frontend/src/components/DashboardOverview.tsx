/**
 * Main dashboard, top part (D23, spec §6.6): the marina's map, three cards, the
 * cabinets' connection (O51). One request — GET /overview — and everything in it
 * (numbers, freshness, colour, sentences) was decided on the server; this file
 * only looks things up and lays them out. Nothing here calls a cabinet.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getOverview,
  type EnergyCard,
  type MapBerth,
  type OccupancyCard,
  type OverviewCard,
  type OverviewResponse,
  type SecurityCard,
} from '../api/dashboard'
import { useAuthStore } from '../store/authStore'
import MarinaMap from './MarinaMap'
import Status, {
  BERTH_ALARM, BERTH_COLOUR, CABINET_LINK, CARD_STATE, SEVERITY, SIMULATED, type Tone,
} from './ui/Status'

const REFRESH_MS = 60_000
// "needs attention" first, then unknown, then by number (§6.1)
const ORDER: Record<string, number> = { red: 0, orange: 1, yellow: 2, grey: 3, blue: 4, green: 5 }

function hhmm(iso: string | null): string {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'
}

function pct(v: number | null): string {
  if (v === null) return '—'
  return `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(v).toFixed(0)} %`
}

export default function DashboardOverview({ marinaId }: { marinaId: number }) {
  const [data, setData] = useState<OverviewResponse | null>(null)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  const load = useCallback(() => {
    getOverview(marinaId).then((d) => { setData(d); setError(false) }).catch(() => setError(true))
  }, [marinaId])

  useEffect(() => {
    load()
    const t = window.setInterval(load, REFRESH_MS)
    return () => window.clearInterval(t)
  }, [load])

  const berths = useMemo(() => [...(data?.berths ?? [])].sort((a, b) =>
    (a.alarm.length ? -1 : 0) - (b.alarm.length ? -1 : 0)
    || ORDER[a.berth_colour] - ORDER[b.berth_colour]
    || a.number.localeCompare(b.number, undefined, { numeric: true })), [data])

  if (error && !data) {
    return <div className="notice-danger mb-6" role="alert">The overview could not be loaded.</div>
  }
  if (!data) return null

  const sel = data.berths.find((b) => b.svg_id === selected) ?? null
  const attention = berths.filter((b) => b.alarm.length > 0 || ['red', 'orange', 'yellow'].includes(b.berth_colour))
  const listed = showAll ? berths : attention
  const nSim = data.berths.filter((b) => b.simulated).length

  return (
    <section className="mb-8" data-overview>
      {nSim > 0 && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-fg-muted mb-3" data-sim-line>
          <Status tone={SIMULATED.tone} icon={SIMULATED.icon} word={SIMULATED.word} />
          {nSim} of {data.berths.length} berths are on simulated cabinets — demo data, never billed,
          not in reports.
        </p>
      )}

      {data.map_svg ? (
        <div className="card !p-2 sm:!p-3 mb-4">
          <MarinaMap file={data.map_svg} berths={data.berths} selected={selected}
            onSelect={(id) => setSelected(id === selected ? null : id)} />
          <Legend />
        </div>
      ) : null}

      {sel && <BerthPanel berth={sel} onClose={() => setSelected(null)} />}

      <div className="grid gap-4 md:grid-cols-3 mb-4">
        {data.cards.map((c) => <Card key={c.key} card={c} marinaId={marinaId} />)}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <h2 className="text-lg font-bold tracking-tight">
              {showAll ? `All berths (${berths.length})` : `Needs attention (${attention.length})`}
            </h2>
            <button className="btn-secondary btn-sm" onClick={() => setShowAll(!showAll)}>
              {showAll ? 'Needs attention' : 'All berths'}
            </button>
          </div>
          {listed.length === 0 ? (
            <p className="text-sm text-fg-muted">Nothing needs attention.</p>
          ) : (
            <ul className="divide-y divide-line max-h-96 overflow-y-auto">
              {listed.map((b) => <BerthRow key={b.berth_id} berth={b} onPick={() => b.svg_id && setSelected(b.svg_id)} />)}
            </ul>
          )}
        </div>
        <div className="card">
          <h2 className="text-lg font-bold tracking-tight mb-2">Cabinets ({data.cabinets.length})</h2>
          <CabinetSummary cabinets={data.cabinets} />
        </div>
      </div>
    </section>
  )
}

function Legend() {
  return (
    <ul className="flex flex-wrap gap-2 mt-2 px-1" aria-label="Map legend">
      {(['green', 'blue', 'yellow', 'orange', 'red', 'grey'] as Tone[]).map((t) => (
        <li key={t}><Status tone={BERTH_COLOUR[t].tone} icon={BERTH_COLOUR[t].icon} word={BERTH_COLOUR[t].word} /></li>
      ))}
      <li><Status tone={BERTH_ALARM.tone} icon={BERTH_ALARM.icon} word={`${BERTH_ALARM.word} (marker)`} /></li>
    </ul>
  )
}

function Card({ card, marinaId }: { card: OverviewCard; marinaId: number }) {
  const role = useAuthStore((s) => s.role)
  const stale = card.state === 'stale'
  const st = CARD_STATE[card.state]
  const href = card.key === 'security'
    ? (role === 'admin' ? '/security' : `/marinas/${marinaId}/alarms`)
    : `/marinas/${marinaId}/${card.href}`
  return (
    <Link to={href} className="card block hover:border-fg-muted transition-colors" data-card={card.key} data-state={card.state}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-semibold text-fg">{card.title}</h3>
        <div className="flex gap-1">
          {card.simulated !== 'none' && <Status tone={SIMULATED.tone} icon={SIMULATED.icon} word={SIMULATED.word} />}
          {card.state !== 'fresh' && <Status tone={st.tone} icon={st.icon} word={st.word} />}
        </div>
      </div>
      <div className={stale ? 'text-fg-muted' : 'text-fg'}>
        {card.key === 'energy' && <EnergyBody c={card} />}
        {card.key === 'security' && <SecurityBody c={card} />}
        {card.key === 'occupancy' && <OccupancyBody c={card} />}
      </div>
      <p className="text-sm text-fg-muted mt-2">{card.sentence}</p>
      <p className="text-xs text-fg-muted mt-3 flex justify-between">
        <span>as of {hhmm(card.as_of)}</span><span aria-hidden="true">›</span>
      </p>
    </Link>
  )
}

function EnergyBody({ c }: { c: EnergyCard }) {
  return (
    <>
      <p className="text-2xl font-bold tracking-tight">
        {c.electricity_kwh.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh
        <span className="text-fg-muted font-semibold"> · {c.water_m3 === null ? '— m³' : `${c.water_m3} m³`}</span>
      </p>
      <p className="text-sm mt-1">{pct(c.delta_yesterday_pct)} vs yesterday · {pct(c.delta_last_week_pct)} vs last week</p>
    </>
  )
}

function SecurityBody({ c }: { c: SecurityCard }) {
  const sev = c.worst ? SEVERITY[c.worst] : null
  return (
    <>
      <p className="text-2xl font-bold tracking-tight">{c.open} open</p>
      <p className="text-sm mt-1 flex flex-wrap items-center gap-2">
        {sev && c.state !== 'stale' && <Status tone={sev.tone} icon={sev.icon} word={sev.word} />}
        {c.open_simulated > 0 && <span>+{c.open_simulated} SIM</span>}
      </p>
    </>
  )
}

function OccupancyBody({ c }: { c: OccupancyCard }) {
  return (
    <>
      <p className="text-2xl font-bold tracking-tight">{c.percent === null ? '—' : `${c.percent} %`}</p>
      <p className="text-sm mt-1">
        {c.occupied} / {c.known} · {c.unknown} unknown · {c.reserved} reserved
      </p>
    </>
  )
}

function BerthRow({ berth, onPick }: { berth: MapBerth; onPick: () => void }) {
  const look = BERTH_COLOUR[berth.berth_colour] ?? BERTH_COLOUR.grey
  return (
    <li className="py-2 flex flex-wrap items-center gap-2 cursor-pointer" onClick={onPick} data-list-berth={berth.number}>
      <span className="font-semibold w-14">{berth.number}</span>
      <Status tone={look.tone} icon={look.icon} word={look.word} />
      {berth.alarm.length > 0 && (
        <Status tone={BERTH_ALARM.tone} icon={BERTH_ALARM.icon} word={`${BERTH_ALARM.word} ${berth.alarm.length}`} />
      )}
      {berth.simulated && <Status tone={SIMULATED.tone} icon={SIMULATED.icon} word={SIMULATED.word} />}
      <span className="text-sm text-fg-muted basis-full sm:basis-auto">
        {[berth.status_sentence, ...berth.alarm.map((a) => a.sentence)].filter(Boolean).join(' · ')}
      </span>
    </li>
  )
}

function BerthPanel({ berth, onClose }: { berth: MapBerth; onClose: () => void }) {
  const look = BERTH_COLOUR[berth.berth_colour] ?? BERTH_COLOUR.grey
  return (
    <div className="card mb-4" data-berth-panel={berth.number}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-bold tracking-tight">Berth {berth.number}</h2>
          <Status tone={look.tone} icon={look.icon} word={look.word} size="md" />
          {berth.simulated && <Status tone={SIMULATED.tone} icon={SIMULATED.icon} word={SIMULATED.word} />}
        </div>
        <button className="btn-secondary btn-sm" onClick={onClose}>Close</button>
      </div>
      {berth.status_sentence && <p className="text-sm mt-2">{berth.status_sentence}</p>}
      {berth.alarm.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {berth.alarm.map((a) => (
            <li key={a.code} className="flex items-center gap-2 text-sm">
              <Status tone={BERTH_ALARM.tone} icon={BERTH_ALARM.icon} word={BERTH_ALARM.word} />{a.sentence}
            </li>
          ))}
        </ul>
      )}
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3 text-sm">
        <div><dt className="text-fg-muted">Cabinet</dt><dd className="font-semibold">{berth.cabinet ?? '—'}</dd></div>
        <div><dt className="text-fg-muted">Length</dt><dd className="font-semibold">{berth.length_m === null ? '—' : `${berth.length_m} m`}</dd></div>
        <div><dt className="text-fg-muted">Power</dt><dd className="font-semibold">{berth.signals.power}</dd></div>
        <div><dt className="text-fg-muted">Reserved</dt><dd className="font-semibold">{berth.signals.reservation}</dd></div>
      </dl>
    </div>
  )
}

function CabinetSummary({ cabinets }: { cabinets: OverviewResponse['cabinets'] }) {
  const [open, setOpen] = useState(false)
  const count = (k: 'ONLINE' | 'STALE' | 'OFFLINE') => cabinets.filter((c) => c.connection === k).length
  const notOnline = cabinets.filter((c) => c.connection !== 'ONLINE')
  const shown = open ? cabinets : notOnline
  return (
    <>
      <ul className="flex flex-wrap gap-2 mb-2">
        {(['ONLINE', 'STALE', 'OFFLINE'] as const).map((k) => (
          <li key={k}><Status tone={CABINET_LINK[k].tone} icon={CABINET_LINK[k].icon} word={`${CABINET_LINK[k].word} ${count(k)}`} /></li>
        ))}
      </ul>
      <ul className="divide-y divide-line max-h-72 overflow-y-auto">
        {shown.map((c) => (
          <li key={c.display_id} className="py-1.5 flex flex-wrap items-center justify-between gap-2 text-sm" data-cabinet={c.display_id} data-connection={c.connection}>
            <span className="font-semibold break-all">{c.display_id}</span>
            <span className="flex items-center gap-1">
              <Status tone={CABINET_LINK[c.connection].tone} icon={CABINET_LINK[c.connection].icon} word={CABINET_LINK[c.connection].word} />
              <span className="text-xs text-fg-muted">{hhmm(c.last_heartbeat_at)}</span>
            </span>
          </li>
        ))}
      </ul>
      {cabinets.length > notOnline.length && (
        <button className="btn-secondary btn-sm mt-2" onClick={() => setOpen(!open)}>
          {open ? 'Only those not online' : `Show all ${cabinets.length}`}
        </button>
      )}
    </>
  )
}
