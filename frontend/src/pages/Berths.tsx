import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getBerths, outletCommand, BerthView, BerthsResponse, Outlet, BerthColour } from '../api/berths'
import { askReason, NO_REASON } from '../api/controls'
import { cabinetSentence } from '../api'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import Status, { BERTH_COLOUR, SWITCH } from '../components/ui/Status'
import { useWebSocket } from '../hooks/useWebSocket'

// berth_colour from the server -> tone of the same name (a lookup, spec §3.2)
const STRIPE: Record<BerthColour, string> = {
  grey: 'border-l-st-grey-line',
  red: 'border-l-st-red-line',
  orange: 'border-l-st-orange-line',
  yellow: 'border-l-st-yellow-line',
  blue: 'border-l-st-blue-line',
  green: 'border-l-st-green-line',
}

function fmt(v: number | null | undefined, digits = 1): string {
  // null is "not known", never 0 (contract: power_kw_current null = reading refused)
  return v === null || v === undefined ? '—' : v.toFixed(digits)
}

function OutletRow({
  outlet,
  berths,
  busy,
  onCommand,
}: {
  outlet: Outlet
  berths: Map<number, string>
  busy: boolean
  onCommand: (outlet: Outlet, action: 'activate' | 'stop') => void
}) {
  const sw = SWITCH[outlet.switch] ?? SWITCH.unknown
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 py-2 text-sm border-t border-line first:border-t-0"
      data-outlet={outlet.name}>
      <div className="min-w-0">
        <span className="inline-flex items-center justify-center min-w-[2.25rem] px-1.5 py-0.5 rounded bg-surface-2 font-mono text-xs font-bold">
          {outlet.name}
        </span>
        {outlet.medium === 'electricity' ? (
          <span className="ml-2 text-fg-muted tabular-nums">
            {outlet.phases === 3 ? '3~' : '1~'} <span className="text-fg font-semibold">{fmt(outlet.power_kw, 2)} kW</span> ·{' '}
            {(outlet.current_amps ?? []).map((a) => fmt(a)).join(' / ')} A
          </span>
        ) : (
          <span className="ml-2 text-fg-muted">Water</span>
        )}
        {outlet.shared_with_berths && outlet.shared_with_berths.length > 0 && (
          <span className="block mt-1 text-xs text-fg-muted">
            {outlet.name} is shared with berth {outlet.shared_with_berths.map((b) => berths.get(b) ?? b).join(', ')}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Status tone={sw.tone} icon={sw.icon} word={sw.word} />
        {outlet.controls?.map((action) => (
          <button
            key={action}
            className={action === 'activate' ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
            disabled={busy}
            onClick={() => onCommand(outlet, action)}
            data-control={`${outlet.name}:${action}`}
          >
            {action === 'activate' ? 'Turn on' : 'Turn off'}
          </button>
        ))}
      </div>
    </li>
  )
}

export default function Berths() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const id = Number(marinaId)

  const [view, setView] = useState<BerthsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setView(await getBerths(id))
      setError(null)
    } catch (err) {
      setError(cabinetSentence(err, 'Berth data is not available.'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetchData() }, [fetchData])
  useWebSocket({ marinaId: id, onMessage: () => fetchData() })

  const onCommand = async (berth: BerthView, outlet: Outlet, action: 'activate' | 'stop') => {
    if (berth.pedestal.pk === null) return
    const reason = await askReason(`${outlet.name}: turn ${action === 'activate' ? 'on' : 'off'}`)
    if (!reason) { setMessage(NO_REASON); return }
    setBusy(true)
    setMessage(null)
    try {
      await outletCommand(id, berth.pedestal.pk, outlet.name, action, reason)
      await fetchData()
    } catch (err) {
      setMessage(cabinetSentence(err, 'The command was not carried out.'))
    } finally {
      setBusy(false)
    }
  }

  if (loading && !view) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-fg" />
      </div>
    )
  }

  const berths = view?.berths ?? []
  const names = new Map(berths.map((b) => [b.berth_id, b.name ?? String(b.berth_id)]))

  return (
    <div className="page" data-page="berths">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="page-title">Berths</h1>
          <p className="page-lead">The state of every berth, as the server computes it</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <StaleDataBanner isStale={!!view?.is_stale} onRefresh={fetchData} />

      {error && (
        <div className="notice-danger mb-6" role="alert">
          <p>{error}</p>
          <button className="btn-primary btn-sm mt-3" onClick={fetchData}>Try again</button>
        </div>
      )}

      {message && (
        <div className="notice-warn mb-6" role="status" data-message>{message}</div>
      )}

      {view && !view.cabinet.configured && (
        <p className="text-sm text-fg-muted mb-4">
          This marina's cabinet is not described in the ERP (device type, outlets per berth) — outlets are not shown.
        </p>
      )}

      {berths.length === 0 && !error ? (
        <div className="card text-center py-10">
          <p className="text-fg-muted">{view?.cabinet.outcome.sentence || 'No berth data.'}</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {berths.map((berth) => {
            const st = BERTH_COLOUR[berth.berth_colour] ?? BERTH_COLOUR.grey
            return (
              <article
                key={berth.berth_id}
                className={`card !p-0 overflow-hidden border-l-4 flex flex-col ${STRIPE[berth.berth_colour] ?? STRIPE.grey}`}
                data-berth={berth.berth_id}
                data-colour={berth.berth_colour}
              >
                <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 px-4 pt-4">
                  <div className="min-w-0">
                    <h3 className="text-lg font-bold tracking-tight">{berth.name ?? `Berth ${berth.berth_id}`}</h3>
                    {berth.pedestal.display_id && (
                      <p className="text-xs text-fg-muted font-mono truncate">{berth.pedestal.display_id}</p>
                    )}
                  </div>
                  <Status tone={st.tone} icon={st.icon} word={st.word} />
                </header>
                {berth.status_sentence && (
                  <p className="px-4 pt-2 text-sm" data-sentence>{berth.status_sentence}</p>
                )}
                {berth.outlets.length > 0 && (
                  <ul className="flex-1 mt-3 px-4 pb-2 bg-surface-2/60 border-t border-line">
                    {berth.outlets.map((o) => (
                      <OutletRow
                        key={o.name}
                        outlet={o}
                        berths={names}
                        busy={busy}
                        onCommand={(outlet, action) => onCommand(berth, outlet, action)}
                      />
                    ))}
                  </ul>
                )}
                {berth.outlets.length === 0 && <div className="pb-4" />}
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
