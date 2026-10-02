import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider, useAuth } from '../../src/auth/AuthContext'
import { useAuthErrorHandler } from '../../src/auth/useAuthErrorHandler'
import { ApiError } from '../../src/api/errors'

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <MemoryRouter initialEntries={['/jobs']}>
        <Routes>
          <Route path="*" element={<>{children}</>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  )
}

describe('useAuthErrorHandler', () => {
  it('returns the error message for a non-401 ApiError, without logging out', () => {
    const { result } = renderHook(
      () => ({ auth: useAuth(), handle: useAuthErrorHandler() }),
      { wrapper },
    )
    act(() => result.current.auth.login('tok', 'a@example.com'))

    let message = ''
    act(() => {
      message = result.current.handle(new ApiError(429, 'Daily job quota exceeded.'))
    })

    expect(message).toBe('Daily job quota exceeded.')
    expect(result.current.auth.token).toBe('tok')
  })

  it('logs out and returns an empty message on a 401 ApiError', () => {
    const { result } = renderHook(
      () => ({ auth: useAuth(), handle: useAuthErrorHandler() }),
      { wrapper },
    )
    act(() => result.current.auth.login('tok', 'a@example.com'))

    let message = ''
    act(() => {
      message = result.current.handle(new ApiError(401, 'Invalid or expired token'))
    })

    expect(message).toBe('')
    expect(result.current.auth.token).toBeNull()
  })

  it('returns a generic message for a non-ApiError', () => {
    const { result } = renderHook(() => useAuthErrorHandler(), { wrapper })

    const message = result.current(new TypeError('network down'))

    expect(message).toBe('Something went wrong. Please try again.')
  })
})
