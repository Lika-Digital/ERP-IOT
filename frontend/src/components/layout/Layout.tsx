import { useEffect, useState } from 'react'
import { Outlet, NavLink, useParams, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useThemeStore } from '../../store/themeStore'
import logo from '../../assets/lika-logo.png'
import { useMarinaName } from '../../hooks/useMarinaName'

// 24px stroke icons, one path each
const ICONS = {
  marinas: 'M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6',
  users: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm13 10v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8',
  security: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zm-3-10 2 2 4-4',
  dashboard: 'M3 3h7v9H3zm11 0h7v5h-7zm0 9h7v9h-7zM3 16h7v5H3z',
  control: 'M13 2 3 14h9l-1 8 10-12h-9l1-8z',
  energy: 'M18 20V10M12 20V4M6 20v-6',
  alarms: 'M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  berths: 'M12 22V8m0 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM5 12H2a10 10 0 0 0 20 0h-3',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2m0 18v2M4.2 4.2l1.4 1.4m12.8 12.8 1.4 1.4M1 12h2m18 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  menu: 'M3 6h18M3 12h18M3 18h18',
  close: 'M18 6 6 18M6 6l12 12',
}

function Icon({ d, className = 'w-[18px] h-[18px]' }: { d: string; className?: string }) {
  return (
    <svg className={`${className} shrink-0`} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3 py-2.5 rounded-control text-sm font-medium transition-colors border-l-[3px] ${
    isActive
      ? 'bg-sidebar-2 text-sidebar-fg border-accent'
      : 'text-sidebar-muted border-transparent hover:text-sidebar-fg hover:bg-sidebar-2'
  }`

export default function Layout() {
  const { marinaId } = useParams<{ marinaId?: string }>()
  const marinaName = useMarinaName(marinaId ? Number(marinaId) : null)
  const { role, email, fullName, logout } = useAuthStore()
  const { theme, toggle } = useThemeStore()
  const navigate = useNavigate()
  const location = useLocation()

  // mobile: the sidebar is a drawer behind a hamburger; a nav tap closes it
  const [open, setOpen] = useState(false)
  useEffect(() => { setOpen(false) }, [location.pathname])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const themeLabel = theme === 'dark' ? 'Light theme' : 'Dark theme'
  const who = fullName || email

  return (
    <div className="flex h-screen bg-canvas">
      {open && (
        <div className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={() => setOpen(false)} aria-hidden="true" />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 bg-sidebar text-sidebar-fg flex flex-col transform
          transition-transform duration-200 md:static md:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}
        data-sidebar
      >
        <div className="p-4 flex items-center justify-between gap-2">
          <NavLink to="/marinas" className="block rounded-control overflow-hidden" aria-label="Lika — home">
            <img src={logo} alt="Lika" className="h-9 w-auto" />
          </NavLink>
          <button className="md:hidden p-2 text-sidebar-muted hover:text-sidebar-fg" onClick={() => setOpen(false)}
            aria-label="Close menu">
            <Icon d={ICONS.close} />
          </button>
        </div>
        <p className="px-5 -mt-1 mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted">
          Marina ERP
        </p>

        <nav className="flex-1 min-h-0 overflow-y-auto px-3 space-y-1">
          <NavLink to="/marinas" className={navLinkClass} end>
            <Icon d={ICONS.marinas} /> All marinas
          </NavLink>
          {role === 'admin' && (
            <NavLink to="/users" className={navLinkClass} data-nav="users">
              <Icon d={ICONS.users} /> Users
            </NavLink>
          )}
          {role === 'admin' && (
            <NavLink to="/security" className={navLinkClass} data-nav="security">
              <Icon d={ICONS.security} /> Security
            </NavLink>
          )}

          {marinaId && (
            <>
              <div className="pt-4 pb-1 px-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-sidebar-muted">
                {marinaName ?? 'Marina'}
              </div>
              <NavLink to={`/marinas/${marinaId}/dashboard`} className={navLinkClass}>
                <Icon d={ICONS.dashboard} /> Dashboard
              </NavLink>
              <NavLink to={`/marinas/${marinaId}/control`} className={navLinkClass}>
                <Icon d={ICONS.control} /> Pedestal control
              </NavLink>
              <NavLink to={`/marinas/${marinaId}/energy`} className={navLinkClass}>
                <Icon d={ICONS.energy} /> Energy
              </NavLink>
              <NavLink to={`/marinas/${marinaId}/alarms`} className={navLinkClass}>
                <Icon d={ICONS.alarms} /> Alarms
              </NavLink>
              <NavLink to={`/marinas/${marinaId}/berths`} className={navLinkClass}>
                <Icon d={ICONS.berths} /> Berths
              </NavLink>
            </>
          )}
        </nav>

        <div className="shrink-0 p-4 border-t border-sidebar-2 space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-accent text-accent-ink flex items-center justify-center text-xs font-bold">
              {who?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="min-w-0">
              <p className="text-xs text-sidebar-fg truncate">{who}</p>
              <p className="text-xs text-sidebar-muted">{role === 'admin' ? 'Admin' : 'Marina Manager'}</p>
            </div>
          </div>
          <button onClick={toggle} className="w-full flex items-center gap-2 text-xs text-sidebar-muted hover:text-sidebar-fg"
            data-theme-toggle>
            <Icon d={theme === 'dark' ? ICONS.sun : ICONS.moon} className="w-4 h-4" /> {themeLabel}
          </button>
          <button onClick={handleLogout} className="w-full btn btn-sm bg-sidebar-2 text-sidebar-fg hover:bg-accent hover:text-accent-ink">
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-auto flex flex-col min-w-0">
        <header className="md:hidden sticky top-0 z-20 flex items-center gap-3 px-4 h-14 bg-sidebar text-sidebar-fg">
          <button onClick={() => setOpen(true)} className="p-2 -ml-2" aria-label="Open menu" data-menu>
            <Icon d={ICONS.menu} className="w-6 h-6" />
          </button>
          <img src={logo} alt="Lika" className="h-7 w-auto rounded" />
          <button onClick={toggle} className="ml-auto p-2 text-sidebar-muted hover:text-sidebar-fg" aria-label={themeLabel}>
            <Icon d={theme === 'dark' ? ICONS.sun : ICONS.moon} />
          </button>
        </header>
        <Outlet />
      </main>
    </div>
  )
}
