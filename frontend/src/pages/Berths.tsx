import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getBerths, outletCommand, BerthView, BerthsResponse, Outlet, BerthColour } from '../api/berths'
import { askReason, NO_REASON } from '../api/controls'
import { cabinetSentence } from '../api'
import StaleDataBanner from '../components/ui/StaleDataBanner'
import { useWebSocket } from '../hooks/useWebSocket'

// Colour key from the server -> CSS. This is a lookup, not a decision: the
// server already decided the colour (spec §3.2).
const COLOUR_CLASS: Record<BerthColour, string> = {
  grey: 'border-gray-300 bg-gray-100',
  red: 'border-red-300 bg-red-50',
  orange: 'border-orange-300 bg-orange-50',
  yellow: 'border-yellow-300 bg-yellow-50',
  blue: 'border-blue-300 bg-blue-50',
  green: 'border-green-300 bg-green-50',
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
  return (
    <li className="flex items-center justify-between gap-2 text-sm" data-outlet={outlet.name}>
      <div>
        <span className="font-mono font-semibold">{outlet.name}</span>
        {outlet.medium === 'electricity' ? (
          <span className="ml-2 text-gray-600">
            {outlet.phases === 3 ? '3~' : '1~'} {fmt(outlet.power_kw, 2)} kW ·{' '}
            {(outlet.current_amps ?? []).map((a) => fmt(a)).join(' / ')} A
          </span>
        ) : (
          <span className="ml-2 text-gray-600">voda</span>
        )}
        {outlet.shared_with_berths && outlet.shared_with_berths.length > 0 && (
          <span className="ml-2 text-xs text-gray-500">
            (dijeli {outlet.name} s vezom{' '}
            {outlet.shared_with_berths.map((b) => berths.get(b) ?? b).join(', ')})
          </span>
        )}
      </div>
      {outlet.controls && (
        <div className="flex gap-1">
          {outlet.controls.map((action) => (
            <button
              key={action}
              className={action === 'activate' ? 'btn-primary py-1 text-xs' : 'btn-secondary py-1 text-xs'}
              disabled={busy}
              onClick={() => onCommand(outlet, action)}
              data-control={`${outlet.name}:${action}`}
            >
              {action === 'activate' ? 'Upali' : 'Ugasi'}
            </button>
          ))}
        </div>
      )}
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
      setError(cabinetSentence(err, 'Podaci o vezovima nisu dostupni.'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetchData() }, [fetchData])
  useWebSocket({ marinaId: id, onMessage: () => fetchData() })

  const onCommand = async (berth: BerthView, outlet: Outlet, action: 'activate' | 'stop') => {
    if (berth.pedestal.pk === null) return
    const reason = await askReason(`${outlet.name} ${action === 'activate' ? 'uključi' : 'isključi'}`)
    if (!reason) { setMessage(NO_REASON); return }
    setBusy(true)
    setMessage(null)
    try {
      await outletCommand(id, berth.pedestal.pk, outlet.name, action, reason)
      await fetchData()
    } catch (err) {
      setMessage(cabinetSentence(err, 'Naredba nije izvršena.'))
    } finally {
      setBusy(false)
    }
  }

  if (loading && !view) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-brand-600" />
      </div>
    )
  }

  const berths = view?.berths ?? []
  const names = new Map(berths.map((b) => [b.berth_id, b.name ?? String(b.berth_id)]))

  return (
    <div className="p-6 max-w-7xl mx-auto" data-page="berths">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Vezovi</h1>
          <p className="text-sm text-gray-500 mt-1">Stanje svakog veza, izračunato na poslužitelju</p>
        </div>
        <button onClick={fetchData} className="btn-secondary" disabled={loading}>
          {loading ? 'Osvježavam…' : 'Osvježi'}
        </button>
      </div>

      <StaleDataBanner isStale={!!view?.is_stale} onRefresh={fetchData} />

      {error && (
        <div className="card bg-red-50 border-red-200 mb-6" role="alert">
          <p className="text-red-700">{error}</p>
          <button className="btn-primary mt-3" onClick={fetchData}>Pokušaj ponovno</button>
        </div>
      )}

      {message && (
        <div className="card bg-yellow-50 border-yellow-200 mb-6" role="status" data-message>
          <p className="text-yellow-800">{message}</p>
        </div>
      )}

      {view && !view.cabinet.configured && (
        <p className="text-sm text-gray-500 mb-4">
          Ormar ove marine nije opisan u ERP-u (tip uređaja, priključci po vezu) — priključci se ne prikazuju.
        </p>
      )}

      {berths.length === 0 && !error ? (
        <div className="card text-center py-10">
          <p className="text-gray-500">{view?.cabinet.outcome.sentence || 'Nema podataka o vezovima.'}</p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {berths.map((berth) => (
            <div
              key={berth.berth_id}
              className={`card flex flex-col gap-2 border ${COLOUR_CLASS[berth.berth_colour] ?? COLOUR_CLASS.grey}`}
              data-berth={berth.berth_id}
              data-colour={berth.berth_colour}
            >
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-900">{berth.name ?? `Vez ${berth.berth_id}`}</h3>
                {berth.pedestal.display_id && (
                  <span className="text-xs text-gray-500 font-mono">{berth.pedestal.display_id}</span>
                )}
              </div>
              {berth.status_sentence && (
                <p className="text-sm text-gray-800" data-sentence>{berth.status_sentence}</p>
              )}
              {berth.outlets.length > 0 && (
                <ul className="flex flex-col gap-1 mt-1">
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
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
