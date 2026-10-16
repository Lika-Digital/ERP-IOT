/**
 * A berth's detail and configuration (D27 phase 1, D30; spec §6.10, §6.12).
 *
 * Vessel: name and registration; the owner only on request, and the server records
 * every such read (D15). Admin edits, with a reason. The cabinet's own occupancy and
 * match result — a result, never a picture (D30). What the cabinet does not offer
 * over its API yet is one sentence each, never a control (D3).
 */
import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { askReason } from '../components/ui/ReasonDialog'
import { detailOf } from '../api/auth'
import {
  clearVessel, getBerthDetail, getVesselOwner, setVessel, type BerthDetail as Detail,
} from '../api/berthDetail'
import Status, { BERTH_ALARM, BERTH_COLOUR, MATCH, OCCUPANCY, SIMULATED } from '../components/ui/Status'
import { dateTime, num } from '../utils/format'

export default function BerthDetail() {
  const { marinaId, berthId } = useParams<{ marinaId: string; berthId: string }>()
  const mid = Number(marinaId), bid = Number(berthId)
  const [data, setData] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [owner, setOwner] = useState<{ owner_name: string | null; owner_contact: string | null } | null>(null)
  const [editing, setEditing] = useState(false)

  const load = useCallback(() => {
    getBerthDetail(mid, bid).then((d) => { setData(d); setError(null) })
      .catch((e) => setError(detailOf(e, 'The berth could not be loaded.')))
  }, [mid, bid])
  useEffect(() => { load() }, [load])

  if (error && !data) return <div className="page"><div className="notice-danger" role="alert">{error}</div></div>
  if (!data || !data.berth) return null
  const b = data.berth
  const look = BERTH_COLOUR[b.berth_colour] ?? BERTH_COLOUR.grey
  const a = data.analysis

  return (
    <div className="page max-w-5xl" data-page="berth">
      <p className="text-sm mb-2"><Link className="text-link" to={`/marinas/${mid}/dashboard`}>← Dashboard</Link></p>
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h1 className="page-title">Berth {b.number}</h1>
        <Status tone={look.tone} icon={look.icon} word={look.word} size="md" />
        {b.alarm.length > 0 && <Status tone={BERTH_ALARM.tone} icon={BERTH_ALARM.icon} word={`${BERTH_ALARM.word} ${b.alarm.length}`} />}
        {b.simulated && <Status tone={SIMULATED.tone} icon={SIMULATED.icon} word={SIMULATED.word} />}
      </div>
      <p className="page-lead mb-6">
        {[b.status_sentence, ...b.alarm.map((x) => x.sentence)].filter(Boolean).join(' · ') || 'Nothing needs attention.'}
      </p>
      {error && <div className="notice-danger mb-4" role="alert">{error}</div>}

      <div className="grid gap-4 md:grid-cols-2">
        <section className="card" data-vessel>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="text-lg font-bold tracking-tight">Vessel</h2>
            {data.can_edit && !editing && (
              <button className="btn-secondary btn-sm" onClick={() => setEditing(true)}>
                {data.vessel ? 'Edit' : 'Add vessel'}
              </button>
            )}
          </div>
          {editing ? (
            <VesselForm detail={data} marinaId={mid} berthId={bid}
              onDone={() => { setEditing(false); setOwner(null); load() }} onError={setError} />
          ) : data.vessel ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-fg-muted">Name</dt><dd className="font-semibold">{data.vessel.name}</dd></div>
              <div><dt className="text-fg-muted">Registration</dt><dd className="font-semibold">{data.vessel.registration ?? '—'}</dd></div>
              <div className="col-span-2">
                <dt className="text-fg-muted">Owner</dt>
                <dd>
                  {owner ? (
                    <span className="font-semibold" data-owner>{owner.owner_name ?? '—'} · {owner.owner_contact ?? '—'}</span>
                  ) : data.vessel.has_owner ? (
                    <button className="btn-secondary btn-sm mt-1" onClick={() =>
                      getVesselOwner(mid, bid).then(setOwner).catch((e) => setError(detailOf(e, 'The owner could not be read.')))}>
                      Show owner
                    </button>
                  ) : '—'}
                  <p className="text-xs text-fg-muted mt-1">Personal data: every view is recorded.</p>
                </dd>
              </div>
              {data.can_edit && (
                <div className="col-span-2">
                  <button className="btn-secondary btn-sm" onClick={async () => {
                    const reason = await askReason('Remove the vessel from this berth')
                    if (!reason) return
                    clearVessel(mid, bid, reason).then(() => { setOwner(null); load() })
                      .catch((e) => setError(detailOf(e, 'The vessel could not be removed.')))
                  }}>Remove vessel</button>
                </div>
              )}
            </dl>
          ) : (
            <p className="text-sm text-fg-muted">No vessel recorded for this berth.</p>
          )}
        </section>

        <section className="card" data-analysis>
          <h2 className="text-lg font-bold tracking-tight mb-1">Cabinet analysis</h2>
          <p className="text-xs text-fg-muted mb-3">
            The cabinet compares the berth with its reference photo; only the result comes here.
          </p>
          {!data.cabinet ? (
            <p className="text-sm text-fg-muted">No cabinet is connected to this berth yet.</p>
          ) : !a ? (
            <p className="text-sm text-fg-muted">The collector has nothing from {data.cabinet.display_id} for this berth yet.</p>
          ) : (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-fg-muted">Occupancy</dt><dd>
                <OccupancyLook occupied={a.occupied} /></dd></div>
              <div><dt className="text-fg-muted">Vessel match</dt><dd>
                <MatchLook match={a.match} /></dd></div>
              <div><dt className="text-fg-muted">Score</dt><dd className="font-semibold">{num(a.score, 2)}</dd></div>
              <div><dt className="text-fg-muted">Reference photos</dt><dd className="font-semibold">{a.reference_images ?? '—'}</dd></div>
              <div className="col-span-2"><dt className="text-fg-muted">Analysed</dt><dd className="font-semibold">
                {dateTime(a.analysed_at)} · {data.cabinet.display_id}
                {a.is_stale && <span className="text-fg-muted"> · data from {dateTime(a.data_as_of)}</span>}
              </dd></div>
            </dl>
          )}
        </section>
      </div>

      <section className="card mt-4" data-functions>
        <h2 className="text-lg font-bold tracking-tight mb-3">Assessment on the cabinet</h2>
        <ul className="divide-y divide-line">
          {data.functions.map((f) => (
            <li key={f.key} className="py-2 flex flex-wrap items-baseline justify-between gap-2" data-function={f.key}>
              <span className="font-semibold text-sm">{f.title}</span>
              <span className="text-sm text-fg-muted">{f.sentence}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function OccupancyLook({ occupied }: { occupied: boolean | null }) {
  const o = OCCUPANCY[occupied === null ? 'none' : occupied ? 'occupied' : 'vacant']
  return <Status tone={o.tone} icon={o.icon} word={o.word} />
}

function MatchLook({ match }: { match: 'match' | 'no_match' | null }) {
  const m = MATCH[match ?? 'none']
  return <Status tone={m.tone} icon={m.icon} word={m.word} />
}

function VesselForm({ detail, marinaId, berthId, onDone, onError }: {
  detail: Detail; marinaId: number; berthId: number; onDone: () => void; onError: (s: string) => void
}) {
  const [name, setName] = useState(detail.vessel?.name ?? '')
  const [registration, setRegistration] = useState(detail.vessel?.registration ?? '')
  const [changeOwner, setChangeOwner] = useState(!detail.vessel?.has_owner)
  const [ownerName, setOwnerName] = useState('')
  const [ownerContact, setOwnerContact] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const save = () => {
    setBusy(true)
    // the owner is sent only when it is being changed; otherwise the server keeps it
    setVessel(marinaId, berthId, {
      name, registration: registration || null, reason,
      ...(changeOwner ? { owner_name: ownerName || null, owner_contact: ownerContact || null } : {}),
    }).then(onDone).catch((e) => onError(detailOf(e, 'The vessel could not be saved.'))).finally(() => setBusy(false))
  }
  return (
    <div className="flex flex-col gap-3" data-vessel-form>
      <label><span className="label">Name</span><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label><span className="label">Registration</span><input className="input" value={registration} onChange={(e) => setRegistration(e.target.value)} /></label>
      {detail.vessel?.has_owner && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={changeOwner} onChange={(e) => setChangeOwner(e.target.checked)} />
          Replace the recorded owner
        </label>
      )}
      {changeOwner && (
        <>
          <label><span className="label">Owner</span><input className="input" value={ownerName} onChange={(e) => setOwnerName(e.target.value)} /></label>
          <label><span className="label">Owner contact</span><input className="input" value={ownerContact} onChange={(e) => setOwnerContact(e.target.value)} /></label>
        </>
      )}
      <label><span className="label">Reason</span><input className="input" value={reason} onChange={(e) => setReason(e.target.value)}
        placeholder="At least 3 characters — written to the audit log" /></label>
      <div className="flex gap-2">
        <button className="btn-primary btn-sm" disabled={busy || name.trim().length === 0 || reason.trim().length < 3} onClick={save}>Save</button>
        <button className="btn-secondary btn-sm" onClick={onDone}>Cancel</button>
      </div>
    </div>
  )
}
