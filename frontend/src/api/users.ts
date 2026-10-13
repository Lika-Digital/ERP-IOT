import api from './index'

export type Role = 'admin' | 'marina_manager'

export interface UserRow {
  id: number
  email: string
  full_name: string | null
  role: Role
  is_active: boolean
  marina_ids: number[]
  password_set: boolean
  mfa_enrolled: boolean
  locked_until: string | null
  last_login: string | null
  created_at: string
}

export interface SetupLink {
  link: string
  expires_at: string
}

export interface UserCreate {
  email: string
  full_name?: string | null
  role: Role
  marina_ids: number[]
}

export interface UserUpdate {
  full_name?: string | null
  role?: Role
  is_active?: boolean
  marina_ids?: number[]
}

export interface AuthAuditRow {
  id: number
  user_id: number | null
  email_tried: string | null
  event: string
  detail: string | null
  actor_id: number | null
  source_ip: string | null
  created_at: string
}

export const listUsers = () => api.get<UserRow[]>('/users').then((r) => r.data)

export const createUser = (body: UserCreate) =>
  api.post<{ user: UserRow; setup: SetupLink }>('/users', body).then((r) => r.data)

export const updateUser = (id: number, body: UserUpdate) =>
  api.patch<UserRow>(`/users/${id}`, body).then((r) => r.data)

export const newSetupLink = (id: number) =>
  api.post<SetupLink>(`/users/${id}/setup-link`).then((r) => r.data)

export const resetMfa = (id: number, reason: string) =>
  api.post<UserRow>(`/users/${id}/mfa-reset`, { reason }).then((r) => r.data)

export const unlockUser = (id: number, reason: string) =>
  api.post<UserRow>(`/users/${id}/unlock`, { reason }).then((r) => r.data)

export const authAudit = (limit = 100) =>
  api.get<AuthAuditRow[]>('/users/audit', { params: { limit } }).then((r) => r.data)
