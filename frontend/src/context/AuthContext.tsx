import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react'
import { AuthState, User } from '../types'
import * as api from '../services/api'

function loadInitialAuth(): AuthState {
  const token = api.getJwtToken()
  if (token) {
    try {
      const parts = token.split('.')
      if (parts.length === 3) {
        const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
        const pad = b64.length % 4
        const padded = pad ? b64 + '='.repeat(4 - pad) : b64
        const payload = JSON.parse(decodeURIComponent(escape(atob(padded))))
        if (payload.exp && payload.exp * 1000 > Date.now()) {
          return {
            isAuthenticated: true,
            user: { user_id: payload.user_id || payload.sub || 'unknown', role: payload.role || 'user' },
            token,
          }
        }
      }
    } catch {
      api.clearJwtToken()
    }
  }
  return { isAuthenticated: false, user: null, token: null }
}

interface AuthContextType {
  auth: AuthState
  login: (userId: string, password: string) => Promise<void>
  register: (userId: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [auth, setAuth] = useState<AuthState>(loadInitialAuth)

  const login = useCallback(async (userId: string, password: string) => {
    const result = await api.authLogin(userId, password)
    api.setJwtToken(result.access_token)
    const user: User = { user_id: result.user_id, role: result.role || 'user' }
    setAuth({ isAuthenticated: true, user, token: result.access_token })
  }, [])

  const register = useCallback(async (userId: string, password: string) => {
    const result = await api.authRegister(userId, password)
    api.setJwtToken(result.access_token)
    const user: User = { user_id: result.user_id, role: result.role || 'user' }
    setAuth({ isAuthenticated: true, user, token: result.access_token })
  }, [])

  const logout = useCallback(() => {
    api.authLogout()
    api.clearJwtToken()
    setAuth({ isAuthenticated: false, user: null, token: null })
  }, [])

  useEffect(() => {
    api.onAuthExpired(() => {
      setAuth({ isAuthenticated: false, user: null, token: null })
    })
    return () => api.onAuthExpired(null)
  }, [])

  const value: AuthContextType = { auth, login, register, logout }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export { AuthContext }
export type { AuthContextType }
