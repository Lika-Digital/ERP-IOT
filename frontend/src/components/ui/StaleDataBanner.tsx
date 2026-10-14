import { StatusGlyph } from './Status'

interface StaleDataBannerProps {
  isStale: boolean
  onRefresh?: () => void
}

export default function StaleDataBanner({ isStale, onRefresh }: StaleDataBannerProps) {
  if (!isStale) return null

  return (
    <div className="notice-warn flex items-center gap-3 mb-4" role="status" data-stale>
      <StatusGlyph icon="attention" className="w-5 h-5" />
      <div className="flex-1">
        <p className="font-semibold">Showing cached data</p>
        <p className="text-xs">The Pedestal SW is currently unreachable. Data may be outdated.</p>
      </div>
      {onRefresh && (
        <button onClick={onRefresh} className="font-semibold underline underline-offset-2">
          Retry
        </button>
      )}
    </div>
  )
}
