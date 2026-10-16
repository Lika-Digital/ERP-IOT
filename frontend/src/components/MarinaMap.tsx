/**
 * The marina's drawn map (spec §6.1, D23). The drawing is a static SVG under /maps/,
 * drawn once; this component only sets the CLASS of each `berth-<id>` element — never
 * its geometry — from the server's `berth_colour`.
 *
 * v21 (T2):
 *  - a tooltip on hover and focus: number, the state's word, alarms, SIM;
 *  - below 640 px the drawing sits in a viewport with zoom and pan (two fingers, drag,
 *    + and −), starting fitted to the width, so the page itself never scrolls sideways;
 *  - alarm markers are laid OVER the drawing in screen pixels; markers that would
 *    overlap at the current zoom merge into one ("Alarm 2", the tooltip names the
 *    berths) and come apart as you zoom in (O66).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { MapBerth } from '../api/dashboard'
import { BERTH_COLOUR, StatusGlyph } from './ui/Status'

interface Props {
  file: string
  berths: MapBerth[]
  selected: string | null
  onSelect: (svgId: string) => void
}

const NARROW_PX = 640            // T2: one constant
const MIN_SCALE = 1
const MAX_SCALE = 6
const MERGE_X = 56               // markers closer than this (px) merge
const MERGE_Y = 20

type Anchor = { id: string; x: number; y: number }          // in the drawing's own units
type View = { scale: number; tx: number; ty: number }
type Tip = { text: string; left: number; top: number } | null

export function describe(b: MapBerth): string {
  const look = BERTH_COLOUR[b.berth_colour] ?? BERTH_COLOUR.grey
  const parts = [`Berth ${b.number}`, look.word]
  if (b.alarm.length) parts.push(`Alarm: ${b.alarm.map((a) => a.sentence).join(', ')}`)
  if (b.simulated) parts.push('SIM')
  return parts.join(' · ')
}

export default function MarinaMap({ file, berths, selected, onSelect }: Props) {
  const frame = useRef<HTMLDivElement>(null)
  const host = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [anchors, setAnchors] = useState<Anchor[]>([])
  const [box, setBox] = useState({ w: 0, vbX: 0, vbY: 0, vbW: 1, vbH: 1 })
  const [narrow, setNarrow] = useState(() => window.matchMedia(`(max-width: ${NARROW_PX - 1}px)`).matches)
  const [view, setView] = useState<View>({ scale: 1, tx: 0, ty: 0 })
  const [tip, setTip] = useState<Tip>(null)
  const bySvg = useMemo(() => new Map(berths.filter((b) => b.svg_id).map((b) => [b.svg_id!, b])), [berths])

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${NARROW_PX - 1}px)`)
    const on = () => { setNarrow(mq.matches); setView({ scale: 1, tx: 0, ty: 0 }) }
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    let live = true
    // a file NAME from the server (the database refuses paths); same origin, our own drawing
    fetch(`/maps/${encodeURIComponent(file)}`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((text) => { if (live) setSvg(text) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [file])

  // class per berth + where the alarm anchors are; after the drawing is in the DOM
  useEffect(() => {
    const root = host.current?.querySelector('svg')
    if (!root) return
    const vb = root.viewBox.baseVal
    const next: Anchor[] = []
    root.querySelectorAll<SVGGraphicsElement>('[id^="berth-"]').forEach((el) => {
      const b = bySvg.get(el.id)
      el.setAttribute('class', ['berth', `tone-${b ? b.berth_colour : 'grey'}`,
        el.id === selected ? 'is-selected' : ''].join(' ').trim())
      el.setAttribute('data-colour', b ? b.berth_colour : 'grey')
      if (b) {
        el.setAttribute('tabindex', '0')
        el.setAttribute('role', 'button')
        el.setAttribute('aria-label', describe(b))
      }
      if (b && b.alarm.length > 0) {
        const r = el.getBBox()
        next.push({ id: el.id, x: r.x + r.width / 2, y: r.y })
      }
    })
    setAnchors(next)
    if (vb && vb.width > 0) setBox((p) => ({ ...p, vbX: vb.x, vbY: vb.y, vbW: vb.width, vbH: vb.height }))
  }, [svg, bySvg, selected])

  // the frame's width, for drawing units -> screen pixels
  useEffect(() => {
    const el = frame.current
    if (!el) return
    const ro = new ResizeObserver(() => setBox((p) => ({ ...p, w: el.clientWidth })))
    ro.observe(el)
    return () => ro.disconnect()
  }, [svg])

  const toScreen = useCallback((x: number, y: number) => {
    const k = box.w / box.vbW
    return { left: (x - box.vbX) * k * view.scale + view.tx, top: (y - box.vbY) * k * view.scale + view.ty }
  }, [box, view])

  // O66: merge markers that would overlap at this zoom
  const markers = useMemo(() => {
    const out: { left: number; top: number; ids: string[] }[] = []
    for (const a of anchors) {
      const p = toScreen(a.x, a.y)
      const near = out.find((m) => Math.abs(m.left - p.left) < MERGE_X && Math.abs(m.top - p.top) < MERGE_Y)
      if (near) near.ids.push(a.id)
      else out.push({ ...p, ids: [a.id] })
    }
    return out
  }, [anchors, toScreen])

  // ── zoom and pan (narrow screens only) ────────────────────────────────────
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<{ d: number; scale: number } | null>(null)
  const moved = useRef(false)

  const clamp = useCallback((v: View): View => {
    const w = box.w, h = box.w * (box.vbH / box.vbW)
    const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale))
    const minX = w - w * scale, minY = h - h * scale
    return { scale, tx: Math.min(0, Math.max(minX, v.tx)), ty: Math.min(0, Math.max(minY, v.ty)) }
  }, [box])

  const zoomAt = useCallback((factor: number, cx?: number, cy?: number) => {
    setView((v) => {
      const x = cx ?? box.w / 2, y = cy ?? (box.w * box.vbH / box.vbW) / 2
      const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor))
      const k = scale / v.scale
      return clamp({ scale, tx: x - (x - v.tx) * k, ty: y - (y - v.ty) * k })
    })
  }, [box, clamp])

  const onPointerDown = (e: React.PointerEvent) => {
    if (!narrow) return
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    moved.current = false
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      pinch.current = { d: Math.hypot(a.x - b.x, a.y - b.y), scale: view.scale }
    }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!narrow || !pointers.current.has(e.pointerId)) return
    const prev = pointers.current.get(e.pointerId)!
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (pointers.current.size === 2 && pinch.current) {
      const [a, b] = [...pointers.current.values()]
      const r = frame.current!.getBoundingClientRect()
      const factor = (Math.hypot(a.x - b.x, a.y - b.y) / pinch.current.d) * pinch.current.scale / view.scale
      zoomAt(factor, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top)
      moved.current = true
    } else if (pointers.current.size === 1 && view.scale > 1) {
      const dx = e.clientX - prev.x, dy = e.clientY - prev.y
      if (Math.abs(dx) + Math.abs(dy) > 2) moved.current = true
      setView((v) => clamp({ ...v, tx: v.tx + dx, ty: v.ty + dy }))
    }
  }
  const onPointerUp = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId)
    if (pointers.current.size < 2) pinch.current = null
  }

  const pick = (e: React.SyntheticEvent) => {
    if (moved.current) { moved.current = false; return }
    const el = (e.target as Element).closest('[id^="berth-"]')
    if (el && bySvg.has(el.id)) onSelect(el.id)
  }

  const showTip = (e: React.SyntheticEvent) => {
    const el = (e.target as Element).closest?.('[id^="berth-"]') as SVGGraphicsElement | null
    const b = el ? bySvg.get(el.id) : undefined
    if (!el || !b || !frame.current) { setTip(null); return }
    const r = el.getBoundingClientRect(), f = frame.current.getBoundingClientRect()
    setTip({ text: describe(b), left: r.left + r.width / 2 - f.left, top: r.top - f.top })
  }

  if (failed) {
    return <p className="text-sm text-fg-muted">The map could not be loaded; the berth list below is complete.</p>
  }

  return (
    <div className="relative" data-map-host data-narrow={narrow ? 'yes' : 'no'}>
      <div
        ref={frame}
        className={`relative overflow-hidden rounded-xl ${narrow ? 'touch-none' : ''}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onMouseOver={showTip}
        onFocus={showTip}
        onMouseLeave={() => setTip(null)}
        onBlur={() => setTip(null)}
      >
        <div
          ref={host}
          className="map-drawing origin-top-left"
          style={{ transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` }}
          onClick={pick}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') pick(e) }}
          // our own static drawing from /maps/, never data from a cabinet or a user
          dangerouslySetInnerHTML={svg ? { __html: svg } : undefined}
        />
        {markers.map((m) => {
          const named = m.ids.map((id) => bySvg.get(id)!).filter(Boolean)
          const count = named.reduce((n, b) => n + b.alarm.length, 0)
          return (
            <span key={m.ids.join('|')} className="map-alarm"
              style={{ left: `${m.left}px`, top: `${m.top}px` }}
              data-alarm-marker={named.map((b) => b.number).join(',')}
              title={named.map(describe).join('\n')}>
              <StatusGlyph icon="alert" className="w-3 h-3" />
              Alarm {count}
            </span>
          )
        })}
        {tip && (
          <span role="tooltip" className="map-tip" style={{ left: `${tip.left}px`, top: `${tip.top}px` }}>
            {tip.text}
          </span>
        )}
      </div>
      {narrow && (
        <div className="absolute right-2 top-2 flex flex-col gap-1" data-zoom-controls>
          <button className="btn-secondary btn-sm !px-2" aria-label="Zoom in" onClick={() => zoomAt(1.5)}>+</button>
          <button className="btn-secondary btn-sm !px-2" aria-label="Zoom out" onClick={() => zoomAt(1 / 1.5)}>−</button>
        </div>
      )}
    </div>
  )
}
