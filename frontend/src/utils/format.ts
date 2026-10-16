/**
 * Every number, date and time on screen goes through here (spec §6.0, T4): the
 * interface is English, so is the format — en-GB, 24-hour time. Nothing on a
 * screen uses the browser's own locale (a Croatian browser wrote 595,1 kWh).
 */
export const LOCALE = 'en-GB'

/** A number from the cabinet, or "—" when it did not come. Missing is never 0. */
export function num(v: number | null | undefined, digits = 1, unit = ''): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const s = v.toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits })
  return unit ? `${s} ${unit}` : s
}

/** A whole percentage, English style: 78%. */
export function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : `${Math.round(v)}%`
}

/** A signed change: +8%, −3%, ±0%. */
export function delta(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : v < 0 ? '−' : '±'}${Math.abs(Math.round(v))}%`
}

/** 06:59 */
export function time(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }) : '—'
}

/** 16/10/2026, 06:59 */
export function dateTime(iso: string | null | undefined): string {
  return iso
    ? new Date(iso).toLocaleString(LOCALE, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—'
}
