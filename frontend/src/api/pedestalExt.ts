/**
 * pedestalExt.ts — API calls for per-pedestal berth occupancy and camera endpoints.
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

export interface CameraStreamPayload {
  pedestal_id: string | number
  stream_url: string
  reachable: boolean
  last_checked: string | null
}

export interface CameraStreamResponse {
  marina_id: number
  pedestal_id: number
  is_stale: boolean
  data: CameraStreamPayload
}

// ── API calls ─────────────────────────────────────────────────────────────────

/** Fetch current berth occupancy for a specific pedestal. */
export const getBerthOccupancy = (marinaId: number, pedestalId: number) =>
  api
    .get<BerthOccupancyResponse>(
      `/marinas/${marinaId}/pedestals/${pedestalId}/berths/occupancy`
    )
    .then((r) => r.data)

/**
 * Fetch a live JPEG camera frame for a specific pedestal.
 * Returns an object URL (revoke with URL.revokeObjectURL when done).
 */
export const getCameraFrame = async (
  marinaId: number,
  pedestalId: number
): Promise<string> => {
  const response = await api.get<Blob>(
    `/marinas/${marinaId}/pedestals/${pedestalId}/camera/frame`,
    { responseType: 'blob' }
  )
  return URL.createObjectURL(response.data)
}

/** Fetch the RTSP stream URL and reachability for a specific pedestal camera. */
export const getCameraStreamUrl = (marinaId: number, pedestalId: number) =>
  api
    .get<CameraStreamResponse>(
      `/marinas/${marinaId}/pedestals/${pedestalId}/camera/stream`
    )
    .then((r) => r.data)
