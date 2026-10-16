import api from './index'

export interface LoginRequest {
  email: string
  password: string
}

/** A correct password opens only the 2FA step (D20). */
export interface MfaChallenge {
  mfa_token: string
  token_type: 'mfa'
  mfa_enrolled: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface EnrollStart {
  secret: string
  otpauth_uri: string
  qr_svg: string
}

export interface EnrollDone extends TokenResponse {
  backup_codes: string[]
}

export interface UserMeResponse {
  id: number
  email: string
  full_name: string | null
  role: string
  marina_ids: number[]
  is_active: boolean
}

const asMfa = (mfaToken: string) => ({ headers: { Authorization: `Bearer ${mfaToken}` } })

export const login = (data: LoginRequest) =>
  api.post<MfaChallenge>('/auth/login', data).then((r) => r.data)

export const verifyMfa = (mfaToken: string, code: string) =>
  api.post<TokenResponse>('/auth/mfa/verify', { code }, asMfa(mfaToken)).then((r) => r.data)

export const startEnrolment = (mfaToken: string) =>
  api.post<EnrollStart>('/auth/mfa/enroll/start', null, asMfa(mfaToken)).then((r) => r.data)

export const confirmEnrolment = (mfaToken: string, code: string) =>
  api.post<EnrollDone>('/auth/mfa/enroll/confirm', { code }, asMfa(mfaToken)).then((r) => r.data)

export const checkSetupLink = (token: string) =>
  api.post<{ email: string }>('/auth/setup/check', { token }).then((r) => r.data)

export const completeSetup = (token: string, password: string) =>
  api.post<MfaChallenge>('/auth/setup', { token, password }).then((r) => r.data)

export const regenerateBackupCodes = (code: string) =>
  api.post<{ backup_codes: string[] }>('/auth/mfa/backup-codes', { code }).then((r) => r.data)

export const getMe = (token?: string) =>
  api
    .get<UserMeResponse>('/auth/me', token ? { headers: { Authorization: `Bearer ${token}` } } : undefined)
    .then((r) => r.data)

export const refreshToken = () =>
  api.post<TokenResponse>('/auth/refresh').then((r) => r.data)

/** No answer from the backend: no response at all, or the proxy in front of it
 *  (nginx 502/504, the dev proxy's 500) answering for it — spec §8.4 P3. */
export function isUnreachable(err: unknown): boolean {
  const r = (err as { response?: { status?: number } })?.response
  return !r || (r.status ?? 0) >= 500
}

/** The server's sentence, or the fallback. */
export function detailOf(err: unknown, fallback: string): string {
  const d = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' && d ? d : fallback
}
