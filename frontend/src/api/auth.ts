import api from './index'

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserMeResponse {
  id: number
  email: string
  full_name: string | null
  role: string
  marina_ids: number[]
  is_active: boolean
}

export const login = (data: LoginRequest) =>
  api.post<TokenResponse>('/auth/login', data).then((r) => r.data)

export const getMe = () =>
  api.get<UserMeResponse>('/auth/me').then((r) => r.data)

export const refreshToken = () =>
  api.post<TokenResponse>('/auth/refresh').then((r) => r.data)
