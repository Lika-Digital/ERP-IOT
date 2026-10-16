/**
 * The marina's drawn map (spec §6.1, D23). The drawing is a static SVG under
 * /maps/, drawn once; this component only sets the CLASS of each `berth-<id>`
 * element — never its geometry — from the server's `berth_colour`.
 *
 * A cabinet alarm is not a colour (v17): it is a marker laid OVER the drawing
 * (icon + "Alarm" + count), positioned from the berth's box, so the drawing
 * itself is never changed.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { MapBerth } from '../api/dashboard'
import { StatusGlyph } from './ui/Status'

interface Props {
  file: string
  berths: MapBerth[]
  selected: string | null
  onSelect: (svgId: string) => void
}

type Box = { left: number; top: number }

export default function MarinaMap({ file, berths, selected, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [marks, setMarks] = useState<Record<string, Box>>({})
  const bySvg = useMemo(() => new Map(berths.filter((b) => b.svg_id).map((b) => [b.svg_id!, b])), [berths])

  useEffect(() => {
    let live = true
    // a file NAME from the server (the database refuses paths); same origin, our own drawing
    fetch(`/maps/${encodeURIComponent(file)}`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((text) => { if (live) setSvg(text) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [file])

  // class per berth + where the alarm markers go; runs after the drawing is in the DOM
  useEffect(() => {
    const root = host.current?.querySelector('svg')
    if (!root) return
    const vb = root.viewBox.baseVal
    const next: Record<string, Box> = {}
    root.querySelectorAll<SVGGraphicsElement>('[id^="berth-"]').forEach((el) => {
      const b = bySvg.get(el.id)
      el.setAttribute('class', [
        'berth',
        `tone-${b ? b.berth_colour : 'grey'}`,
        el.id === selected ? 'is-selected' : '',
      ].join(' ').trim())
      el.setAttribute('data-colour', b ? b.berth_colour : 'grey')
      if (b) {
        el.setAttribute('tabindex', '0')
        el.setAttribute('role', 'button')
        el.setAttribute('aria-label', `Berth ${b.number}`)
      }
      if (b && b.alarm.length > 0 && vb && vb.width > 0) {
        const r = el.getBBox()
        next[el.id] = {
          left: ((r.x + r.width / 2 - vb.x) / vb.width) * 100,
          top: ((r.y - vb.y) / vb.height) * 100,
        }
      }
    })
    setMarks(next)
  }, [svg, bySvg, selected])

  if (failed) {
    return <p className="text-sm text-fg-muted">The map could not be loaded; the berth list below is complete.</p>
  }

  const pick = (e: React.SyntheticEvent) => {
    const el = (e.target as Element).closest('[id^="berth-"]')
    if (el && bySvg.has(el.id)) onSelect(el.id)
  }

  return (
    <div className="relative marina-map" data-map-host>
      <div
        ref={host}
        className="map-drawing"
        onClick={pick}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') pick(e) }}
        // our own static drawing from /maps/, never data from a cabinet or a user
        dangerouslySetInnerHTML={svg ? { __html: svg } : undefined}
      />
      {Object.entries(marks).map(([id, pos]) => {
        const b = bySvg.get(id)!
        return (
          <span
            key={id}
            className="map-alarm"
            style={{ left: `${pos.left}%`, top: `${pos.top}%` }}
            data-alarm-marker={b.number}
            title={b.alarm.map((a) => a.sentence).join(' · ')}
          >
            <StatusGlyph icon="alert" className="w-3 h-3" />
            Alarm {b.alarm.length}
          </span>
        )
      })}
    </div>
  )
}
