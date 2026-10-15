import api from './index'

// Everything here is computed by the server (spec §3). The frontend renders
// berth_colour and status_sentence and never derives a status itself
// (TC-ERP-SIM-15 scans this tree for status_code literals).

export type BerthColour = 'grey' | 'red' | 'orange' | 'yellow' | 'blue' | 'green'

export interface Outlet {
  name: string
  medium: 'electricity' | 'water'
  phases?: number | null
  rated_amps?: number | null
  rated_lpm?: number
  current_amps?: (number | null)[]
  power_kw?: number | null
  state?: string
  // on | off | unknown — decided by the server from the cabinet's state; controls follow it
  switch: 'on' | 'off' | 'unknown'
  breaker_tripped?: boolean
  shared_with_berths?: number[]
  // Present ONLY when a control can actually work (D3). Absent = no control in the DOM.
  controls?: ('activate' | 'stop')[]
}

export interface BerthView {
  berth_id: number
  name: string | null
  pedestal: { pk: number | null; display_id: string | null }
  status_code: string
  status: 'ok' | 'attention' | 'unknown'
  berth_colour: BerthColour
  status_sentence: string
  signals: { connection: string; vessel: string; power: string; reservation: string }
  data_as_of: string | null
  outlets: Outlet[]
}

export interface Outcome {
  code: string
  sentence: string
  endpoint: string | null
  is_stale: boolean
  data_as_of: string | null
}

export interface BerthsResponse {
  marina_id: number
  berths: BerthView[]
  is_stale: boolean
  cabinet: { outcome: Outcome; configured: boolean; device_type: string | null }
}

export const getBerths = (marinaId: number): Promise<BerthsResponse> =>
  api.get(`/marinas/${marinaId}/berths`).then((r) => r.data)

export const outletCommand = (
  marinaId: number,
  pedestalPk: number,
  outlet: string,
  action: 'activate' | 'stop',
  reason: string
) =>
  api
    .post(`/marinas/${marinaId}/pedestals/${pedestalPk}/outlets/${outlet}/cmd`, { action, reason })
    .then((r) => r.data)
