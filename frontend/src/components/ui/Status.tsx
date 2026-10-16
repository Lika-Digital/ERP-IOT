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
    <span className={`inline-flex items-center gap-1.5 rounded-full border font-semibold whitespace-nowrap ${pad} ${TONE[tone]}`}
      data-status={tone}>
      <StatusGlyph icon={icon} className={size === 'md' ? 'w-4 h-4' : 'w-3.5 h-3.5'} />
      {word}
    </span>
  )
}

/* ── Lookup tables: server key -> how it is shown. Never a decision. ───────── */

type Look = { tone: Tone; icon: StatusIcon; word: string }

/**
 * Berth: keyed by the server's `berth_colour` (D2, spec §3.2). One colour, one
 * word — the same word never appears in two colours.
 */
export const BERTH_COLOUR: Record<Tone, Look> = {
  green: { tone: 'green', icon: 'ok', word: 'Free' },
  blue: { tone: 'blue', icon: 'ok', word: 'Occupied — correct vessel' },
  yellow: { tone: 'yellow', icon: 'info', word: 'Reserved' },
  orange: { tone: 'orange', icon: 'attention', word: 'Power without vessel' },
  red: { tone: 'red', icon: 'alert', word: 'Wrong vessel' },
  grey: { tone: 'grey', icon: 'unknown', word: 'Unknown' },
}

/** Outlet / valve: the server's `switch` (on | off | unknown). */
export const SWITCH: Record<string, Look> = {
  on: { tone: 'green', icon: 'ok', word: 'On' },
  off: { tone: 'grey', icon: 'paused', word: 'Off' },
  unknown: { tone: 'grey', icon: 'unknown', word: 'Unknown' },
}

/** Security alarm severity (D21). */
export const SEVERITY: Record<string, Look> = {
  critical: { tone: 'red', icon: 'alert', word: 'Critical' },
  warning: { tone: 'orange', icon: 'attention', word: 'Warning' },
  info: { tone: 'blue', icon: 'info', word: 'Info' },
}

/** Security alarm state and rule mode (D21). */
export const ALARM_STATE: Record<string, Look> = {
  open: { tone: 'red', icon: 'attention', word: 'Open' },
  acknowledged: { tone: 'yellow', icon: 'ok', word: 'Acknowledged' },
  closed: { tone: 'grey', icon: 'ok', word: 'Closed' },
}
export const RULE_MODE: Record<string, Look> = {
  active: { tone: 'green', icon: 'ok', word: 'Active' },
  shadow: { tone: 'grey', icon: 'paused', word: 'Shadow' },
}

/** Users (D20): what the server reports about an account, one look per fact. */
export const ACCOUNT: Record<string, Look> = {
  password_set: { tone: 'green', icon: 'ok', word: 'Password set' },
  link_pending: { tone: 'yellow', icon: 'info', word: 'Link pending' },
  mfa_linked: { tone: 'green', icon: 'ok', word: '2FA linked' },
  mfa_missing: { tone: 'yellow', icon: 'attention', word: '2FA not linked' },
  active: { tone: 'green', icon: 'ok', word: 'Active' },
  locked: { tone: 'red', icon: 'alert', word: 'Locked' },
  disabled: { tone: 'grey', icon: 'paused', word: 'Disabled' },
}

/** Cabinet sessions as the server lists them: waiting for approval, or running. */
export const SESSION: Record<'pending' | 'active', Look> = {
  pending: { tone: 'yellow', icon: 'info', word: 'Waiting for approval' },
  active: { tone: 'green', icon: 'ok', word: 'Active' },
}

/** Marina record status, as stored on the server. */
export const MARINA: Record<string, Look> = {
  active: { tone: 'green', icon: 'ok', word: 'Active' },
  maintenance: { tone: 'yellow', icon: 'attention', word: 'Maintenance' },
  inactive: { tone: 'grey', icon: 'paused', word: 'Inactive' },
}

/** A connection test the operator just ran. */
export const CONNECTION: Record<'ok' | 'failed', Look> = {
  ok: { tone: 'green', icon: 'ok', word: 'Connection OK' },
  failed: { tone: 'red', icon: 'alert', word: 'Connection failed' },
}

/** Camera occupancy as the cabinet reports it (true / false / not analysed). */
export const OCCUPANCY: Record<'occupied' | 'vacant' | 'none', Look> = {
  occupied: { tone: 'blue', icon: 'ok', word: 'Occupied' },
  vacant: { tone: 'green', icon: 'ok', word: 'Free' },
  none: { tone: 'grey', icon: 'unknown', word: 'Not analysed' },
}

/** A sensor or device the cabinet reports as reachable or not; a reading in alarm. */
export const REACH: Record<'yes' | 'no', Look> = {
  yes: { tone: 'green', icon: 'ok', word: 'Reachable' },
  no: { tone: 'red', icon: 'alert', word: 'Unreachable' },
}
export const READING_ALARM: Look = { tone: 'red', icon: 'alert', word: 'Alarm' }

/** Dashboard card freshness (D23, §6.6): stale is grey, never a number in full colour. */
export const CARD_STATE: Record<'fresh' | 'partial' | 'stale', Look> = {
  fresh: { tone: 'green', icon: 'ok', word: 'Current' },
  partial: { tone: 'yellow', icon: 'attention', word: 'Partial' },
  stale: { tone: 'grey', icon: 'unknown', word: 'No current data' },
}

/** A cabinet's connection, as the server computes it from the heartbeat (D2, O51). */
export const CABINET_LINK: Record<'ONLINE' | 'STALE' | 'OFFLINE', Look> = {
  ONLINE: { tone: 'green', icon: 'ok', word: 'Online' },
  STALE: { tone: 'yellow', icon: 'attention', word: 'Late' },
  OFFLINE: { tone: 'grey', icon: 'unknown', word: 'Offline' },
}

/** A cabinet alarm on a berth: a marker next to the colour, never the colour (v17). */
export const BERTH_ALARM: Look = { tone: 'red', icon: 'alert', word: 'Alarm' }

/** Simulated data (D28): seen by Admin and Marina Manager alike. */
export const SIMULATED: Look = { tone: 'grey', icon: 'info', word: 'SIM' }
