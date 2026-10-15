import logo from '../../assets/lika-logo.png'

/** The frame around every sign-in step: login, 2FA, one-time setup link. */
export default function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-sidebar flex items-center justify-center p-4 relative overflow-hidden">
      {/* the Lika dot grid, faint, as texture */}
      <div
        className="absolute inset-0 opacity-[0.07] pointer-events-none"
        style={{ backgroundImage: 'radial-gradient(rgb(var(--accent)) 2px, transparent 2.5px)', backgroundSize: '28px 28px' }}
        aria-hidden="true"
      />
      <div className="w-full max-w-md relative">
        <div className="flex flex-col items-center mb-8">
          <img src={logo} alt="Lika" className="h-14 w-auto rounded-card shadow-card" />
          <p className="mt-4 text-[11px] font-semibold uppercase tracking-[0.18em] text-sidebar-muted">
            Marina ERP
          </p>
        </div>

        <div className="bg-surface text-fg rounded-card shadow-card border border-line p-6 sm:p-8">
          <h1 className="text-xl font-bold tracking-tight mb-6">{title}</h1>
          {children}
        </div>

        <p className="text-center text-sidebar-muted text-xs mt-6">Lika Digital · ERP-IOT</p>
      </div>
    </div>
  )
}
