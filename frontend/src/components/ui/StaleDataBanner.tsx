interface StaleDataBannerProps {
  isStale: boolean
  onRefresh?: () => void
}

export default function StaleDataBanner({ isStale, onRefresh }: StaleDataBannerProps) {
  if (!isStale) return null

  return (
    <div className="flex items-center gap-3 bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-3 mb-4">
      <svg
        className="w-5 h-5 text-yellow-500 shrink-0"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <div className="flex-1">
        <p className="text-sm font-medium text-yellow-800">Showing cached data</p>
        <p className="text-xs text-yellow-600">
          The Pedestal SW is currently unreachable. Data may be outdated.
        </p>
      </div>
      {onRefresh && (
        <button
          onClick={onRefresh}
          className="text-sm text-yellow-700 font-medium hover:text-yellow-900"
        >
          Retry
        </button>
      )}
    </div>
  )
}
