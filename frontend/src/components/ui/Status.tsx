/**
 * Status — always icon + word + colour, all three (TC-UIR-01).
 *
 * The status itself comes from the server (spec §3): the caller passes the
 * server's key through a lookup table below, never a value it worked out.
 */
export type Tone = 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'grey'
export type StatusIcon = 'ok' | 'attention' | 'alert' | 'unknown' | 'info' | 'paused'

interface StatusProps {
  tone: Tone
  icon: StatusIcon
  word: string
  size?: 'sm' | 'md'
}

const TONE: Record<Tone, string> = {
  green: 'bg-st-green-bg text-st-green-fg border-st-green-line',
  yellow: 'bg-st-yellow-bg text-st-yellow-fg border-st-yellow-line',
  orange: 'bg-st-orange-bg text-st-orange-fg border-st-orange-line',
  red: 'bg-st-red-bg text-st-red-fg border-st-red-line',
  blue: 'bg-st-blue-bg text-st-blue-fg border-st-blue-line',
  grey: 'bg-st-grey-bg text-st-grey-fg border-st-grey-line',
}

// 24px stroke icons; shape differs per meaning, so the status reads without colour
const PATHS: Record<StatusIcon, string> = {
  ok: 'M20 6 9 17l-5-5',
  attention: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  alert: 'M12 8v5m0 3h.01M7.9 2h8.2L22 7.9v8.2L16.1 22H7.9L2 16.1V7.9z',
  unknown: 'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3m.1 4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z',
  info: 'M12 16v-4m0-4h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z',
  paused: 'M10 15V9m4 6V9M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z',
}

export function StatusGlyph({ icon, className = 'w-4 h-4' }: { icon: StatusIcon; className?: string }) {
  return (
    <svg className={`${className} shrink-0`} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[icon]} />
    </svg>
  )
}

export default function Status({ tone, icon, word, size = 'sm' }: StatusProps) {
  const pad = size === 'md' ? 'px-3 py-1 text-sm' : 'px-2.5 py-0.5 text-xs'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border font-semibold ${pad} ${TONE[tone]}`}
      data-status={tone}>
      <StatusGlyph icon={icon} className={size === 'md' ? 'w-4 h-4' : 'w-3.5 h-3.5'} />
      {word}
    </span>
  )
}

/* ── Lookup tables: server key -> how it is shown. Never a decision. ───────── */

/** Berth: the server's `status` category (ok | attention | unknown), §3. */
export const BERTH_STATUS: Record<string, { icon: StatusIcon; word: string }> = {
  ok: { icon: 'ok', word: 'U redu' },
  attention: { icon: 'attention', word: 'Pažnja' },
  unknown: { icon: 'unknown', word: 'Nepoznato' },
}

/** Security alarm severity (D21). */
export const SEVERITY: Record<string, { tone: Tone; icon: StatusIcon; word: string }> = {
  critical: { tone: 'red', icon: 'alert', word: 'critical' },
  warning: { tone: 'orange', icon: 'attention', word: 'warning' },
  info: { tone: 'blue', icon: 'info', word: 'info' },
}

/** Security alarm state and rule mode (D21). */
export const ALARM_STATE: Record<string, { tone: Tone; icon: StatusIcon; word: string }> = {
  open: { tone: 'red', icon: 'attention', word: 'open' },
  acknowledged: { tone: 'yellow', icon: 'ok', word: 'acknowledged' },
  closed: { tone: 'grey', icon: 'ok', word: 'closed' },
}
export const RULE_MODE: Record<string, { tone: Tone; icon: StatusIcon; word: string }> = {
  active: { tone: 'green', icon: 'ok', word: 'active' },
  shadow: { tone: 'grey', icon: 'paused', word: 'shadow' },
}
