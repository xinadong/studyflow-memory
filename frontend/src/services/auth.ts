import { apiRequest } from './api'

export interface AuthUser {
  id: string
  email: string
  created_at: string
}

export interface Credentials {
  email: string
  password: string
}

export const registerAccount = (payload: Credentials) => apiRequest<AuthUser>('/auth/register', {
  method: 'POST',
  body: JSON.stringify(payload),
})

export const loginAccount = (payload: Credentials) => apiRequest<AuthUser>('/auth/login', {
  method: 'POST',
  body: JSON.stringify(payload),
})

export const getCurrentUser = () => apiRequest<AuthUser>('/auth/me')

export const logoutAccount = () => apiRequest<void>('/auth/logout', { method: 'POST' })
