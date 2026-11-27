import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../services/api'

export interface AuthUser {
  id: number
  username: string
  email: string | null
  display_name: string
  role: 'admin' | 'operator' | string
  mfa_enabled: boolean
  last_login: number | null
}

export type LoginResult = { mfa_required: true } | { mfa_required: false; user: AuthUser }

interface AuthState {
  status: 'loading' | 'signed-out' | 'signed-in'
  user: AuthUser | null
  login: (username: string, password: string, remember: boolean, otp?: string) => Promise<LoginResult>
  accept: (user: AuthUser) => void
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState['status']>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)

  useEffect(() => {
    api
      .get<AuthUser>('/api/auth/me')
      .then((u) => {
        setUser(u)
        setStatus('signed-in')
      })
      .catch(() => setStatus('signed-out'))
    const expired = () => {
      setUser(null)
      setStatus('signed-out')
    }
    window.addEventListener('auth:expired', expired)
    return () => window.removeEventListener('auth:expired', expired)
  }, [])

  const login = useCallback(
    (username: string, password: string, remember: boolean, otp?: string) =>
      api.post<LoginResult>('/api/auth/login', { username, password, remember, otp: otp || null }),
    [],
  )

  const accept = useCallback((u: AuthUser) => {
    setUser(u)
    setStatus('signed-in')
  }, [])

  const logout = useCallback(async () => {
    await api.post('/api/auth/logout', {}).catch(() => undefined)
    setUser(null)
    setStatus('signed-out')
  }, [])

  return <AuthContext.Provider value={{ status, user, login, accept, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
