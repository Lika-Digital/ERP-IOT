import { useThemeStore } from '../store/themeStore'

/**
 * A token as a colour string, for places CSS classes cannot reach (chart fills).
 * Re-reads on a theme switch, so a chart follows the theme like everything else.
 */
export function useToken(...names: string[]): string[] {
  useThemeStore((s) => s.theme)          // subscribe: a theme switch re-renders the caller
  const css = getComputedStyle(document.documentElement)
  return names.map((n) => `rgb(${css.getPropertyValue(`--${n}`).trim().split(/\s+/).join(', ')})`)
}
