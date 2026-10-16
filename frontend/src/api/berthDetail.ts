import api from './index'
import type { MapBerth } from './dashboard'

// A berth's detail (D27 phase 1, D30; spec §6.10, §6.12). The detail never carries the
// owner — only whether one is recorded; reading it is its own, audited request (D15).

export interface BerthFunction {
  key: string
  title: string
  available: boolean
  sentence: string | null
  requires: string
}

/** P1: the Admin's record that the cabinet's gateway allows the upload (spec §6.12). */
export interface UploadRecord {
  enabled: boolean
  set_by: string | null
  reason: string | null
  note: string | null
  at: string | null
}

/** A reference photo SENT to the cabinet — its hash, never the picture (P2). */
export interface SentPhoto {
  sha256: string
  size_bytes: number
  uploaded_by: string
  uploaded_at: string
  outcome: string | null
}

export interface BerthDetail {
  berth: MapBerth | null
  cabinet: { display_id: string; simulated: boolean } | null
  vessel: { name: string; registration: string | null; has_owner: boolean; since: string } | null
  analysis: {
    occupied: boolean | null
    match: 'match' | 'no_match' | null
    score: number | null
    analysed_at: string | null
    reference_images: number | null
    is_stale: boolean
    data_as_of: string | null
  } | null
  functions: BerthFunction[]
  reference: { cabinet_id: number; record: UploadRecord | null; photos: SentPhoto[] } | null
  can_edit: boolean
}

export interface VesselInput {
  name: string
  registration: string | null
  owner_name?: string | null      // omitted: the owner stays as recorded
  owner_contact?: string | null
  reason: string
}

export const getBerthDetail = (marinaId: number, berthId: number) =>
  api.get<BerthDetail>(`/marinas/${marinaId}/berths/${berthId}/detail`).then((r) => r.data)

export const getVesselOwner = (marinaId: number, berthId: number) =>
  api.get<{ owner_name: string | null; owner_contact: string | null }>(
    `/marinas/${marinaId}/berths/${berthId}/vessel/owner`).then((r) => r.data)

export const setVessel = (marinaId: number, berthId: number, body: VesselInput) =>
  api.put(`/marinas/${marinaId}/berths/${berthId}/vessel`, body).then((r) => r.data)

export const setUploadRecord = (marinaId: number, cabinetId: number, enabled: boolean, reason: string) =>
  api.put<{ ok: boolean; record: UploadRecord }>(`/marinas/${marinaId}/cabinets/${cabinetId}/reference-upload`,
    { enabled, reason }).then((r) => r.data)

/** P5: the file goes to the cabinet as a clean JPEG; the ERP keeps only its sha256. */
export const uploadReferencePhoto = (marinaId: number, berthId: number, file: File, reason: string) => {
  const form = new FormData()
  form.append('file', file)
  form.append('reason', reason)
  form.append('no_people_confirmed', 'true')
  return api.post<{ ok: boolean; sha256: string; size_bytes: number }>(
    `/marinas/${marinaId}/berths/${berthId}/reference-photo`, form).then((r) => r.data)
}

export const clearVessel = (marinaId: number, berthId: number, reason: string) =>
  api.delete(`/marinas/${marinaId}/berths/${berthId}/vessel`, { data: { reason } }).then((r) => r.data)
