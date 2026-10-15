/** A number from the cabinet, or "—" when it did not come. Missing is never 0. */
export function num(v: number | null | undefined, digits = 1, unit = ''): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return unit ? `${v.toFixed(digits)} ${unit}` : v.toFixed(digits)
}
