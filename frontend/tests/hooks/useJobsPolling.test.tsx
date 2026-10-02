import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../../src/auth/AuthContext'
import { useJobsPolling } from '../../src/hooks/useJobsPolling'
import { MemoryRouter } from 'react-router-dom'
import { FakeApiClient, makeJob } from '../api/fakeApiClient'

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <MemoryRouter>{children}</MemoryRouter>
    </AuthProvider>
  )
}

function countOf(client: FakeApiClient): number {
  return client.calls.filter((c) => c.method === 'listJobs').length
}

describe('useJobsPolling', () => {
  it('fetches once on mount even with no active jobs', async () => {
    const client = new FakeApiClient()
    client.jobs = [makeJob({ status: 'completed' })]

    const { result } = renderHook(() => useJobsPolling(client, 20), { wrapper })

    await waitFor(() => expect(result.current.jobs).toHaveLength(1))
    expect(countOf(client)).toBe(1)
  })

  it('does not keep polling once every job is terminal', async () => {
    const client = new FakeApiClient()
    client.jobs = [makeJob({ status: 'completed' })]
    renderHook(() => useJobsPolling(client, 20), { wrapper })

    await waitFor(() => expect(countOf(client)).toBe(1))
    // Give the (absent) interval a chance to fire if the bug regresses.
    await new Promise((resolve) => setTimeout(resolve, 100))

    expect(countOf(client)).toBe(1)
  })

  it('keeps polling while a job is still queued or running', async () => {
    const client = new FakeApiClient()
    client.jobs = [makeJob({ status: 'queued' })]
    renderHook(() => useJobsPolling(client, 20), { wrapper })

    await waitFor(() => expect(countOf(client)).toBeGreaterThanOrEqual(3), { timeout: 2000 })
  })
})
