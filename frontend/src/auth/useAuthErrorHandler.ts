import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/errors'
import { useAuth } from './AuthContext'

// Centralizes the one cross-cutting rule every page needs: a 401 means the
// token is gone/expired, so clear auth state and bounce to /login instead
// of showing an error message that would just reappear on retry.
//
// Must return a *stable* function reference (useCallback, not a fresh
// closure every render): callers like useJobsPolling put this in a
// useCallback's own dependency array, and an unstable handler there would
// recreate that callback every render, retrigger its mount effect, and
// cause an unbounded refetch loop -- caught by a test asserting an exact
// call count, not a hang, but it's the same underlying bug.
export function useAuthErrorHandler() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  return useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          logout()
          navigate('/login')
          return ''
        }
        return err.message
      }
      return 'Something went wrong. Please try again.'
    },
    [logout, navigate],
  )
}
