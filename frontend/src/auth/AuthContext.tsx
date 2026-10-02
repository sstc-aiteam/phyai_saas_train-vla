import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'lerobot.auth'

interface StoredAuth {
  token: string
  email: string
}

interface AuthContextValue {
  token: string | null
  email: string | null
  // Set on successful register/login. `email` is only ever used for
  // display -- the backend's JWT carries no email claim (just the user
  // id as `sub`), and authorization always goes through the token, never
  // the locally-remembered email.
  login: (token: string, email: string) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readStoredAuth(): StoredAuth | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as StoredAuth) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<StoredAuth | null>(readStoredAuth)

  const login = useCallback((token: string, email: string) => {
    const next = { token, email }
    setAuth(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // localStorage unavailable (private mode, etc.) -- session still
      // works for this page load via React state, just won't survive a reload.
    }
  }, [])

  const logout = useCallback(() => {
    setAuth(null)
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // see above
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ token: auth?.token ?? null, email: auth?.email ?? null, login, logout }),
    [auth, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
