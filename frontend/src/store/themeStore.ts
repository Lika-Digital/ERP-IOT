import { create } from 'zustand'

// Light / dark, as on the cabinet (themeStore + `.light` on <html>). The choice is
// saved under 'erp-theme'; without one, index.html follows the system preference.
export type Theme = 'light' | 'dark'

const KEY = 'erp-theme'

function current(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

function apply(theme: Theme) {
  const root = document.documentElement
  root.classList.remove('light', 'dark')
  root.classList.add(theme)
}

interface ThemeState {
  theme: Theme
  toggle: () => void
}

export const useThemeStore = create<ThemeState>()((set, get) => ({
  theme: current(),
  toggle: () => {
    const next: Theme = get().theme === 'dark' ? 'light' : 'dark'
    apply(next)
    try { localStorage.setItem(KEY, next) } catch { /* private mode: not saved */ }
    set({ theme: next })
  },
}))
