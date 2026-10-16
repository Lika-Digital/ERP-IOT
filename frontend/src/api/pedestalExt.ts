/**
 * pedestalExt.ts — API call for per-pedestal berth occupancy. No camera (D30).
 * All calls are marina-scoped: /api/marinas/{marinaId}/pedestals/{pedestalId}/...
 */
import api from './index'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface BerthOccupancy {
  berth_id: number
  berth_name: string | null
  occupied: boolean | null
  last_analyzed?: string | null
  note?: string | null
}

export interface BerthOccupancyPayload {
  pedestal_id: string | number
  berths: BerthOccupancy[]
  message?: string
}

export interface BerthOccupancyResponse {
  marina_id: number
  pedestal_id: number
  is_stale: boolean
  data: BerthOccupancyPayload
}

// ── API calls ─────────────────────────────────────────────────────────────────

/** Fetch current berth occupancy for a specific pedestal. */
export const getBerthOccupancy = (marinaId: number, pedestalId: number) =>
  api
    .get<BerthOccupancyResponse>(
      `/marinas/${marinaId}/pedestals/${pedestalId}/berths/occupancy`
    )
    .then((r) => r.data)
