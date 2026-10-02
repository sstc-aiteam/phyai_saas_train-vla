import { createContext, useContext, useMemo, type ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'
import { createApiClient, type ApiClient } from './client'

const ApiClientContext = createContext<ApiClient | null>(null)

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

interface ApiClientProviderProps {
  children: ReactNode
  // Tests pass a FakeApiClient here instead of letting the real
  // fetch-based client get built, matching the backend's ports-and-fakes
  // convention -- no fetch mocking needed.
  client?: ApiClient
}

export function ApiClientProvider({ children, client }: ApiClientProviderProps) {
  const { token } = useAuth()
  const defaultClient = useMemo(() => createApiClient(BASE_URL, () => token), [token])
  return <ApiClientContext.Provider value={client ?? defaultClient}>{children}</ApiClientContext.Provider>
}

export function useApiClient(): ApiClient {
  const ctx = useContext(ApiClientContext)
  if (!ctx) throw new Error('useApiClient must be used within an ApiClientProvider')
  return ctx
}
