import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type UserRole = 'super_admin' | 'marina_manager'

interface AuthState {
  token: string | null
  role: UserRole | null
  email: string | null
  fullName: string | null
  marinaIds: number[]           // Empty = all marinas (super_admin)
  isAuthenticated: boolean

  setAuth: (
    token: string,
    role: UserRole,
    email: string,
    marinaIds: number[],
    fullName?: string | null
  ) => void

  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      email: null,
      fullName: null,
      marinaIds: [],
      isAuthenticated: false,

      setAuth: (token, role, email, marinaIds, fullName = null) => {
        set({ token, role, email, fullName, marinaIds, isAuthenticated: true })
      },

      logout: () => {
        set({
          token: null,
          role: null,
          email: null,
          fullName: null,
          marinaIds: [],
          isAuthenticated: false,
        })
      },
    }),
    {
      name: 'erp-iot-auth',
      partialize: (state) => ({
        token: state.token,
        role: state.role,
        email: state.email,
        fullName: state.fullName,
        marinaIds: state.marinaIds,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
