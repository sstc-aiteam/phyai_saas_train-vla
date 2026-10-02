import { useCallback, useEffect, useState } from 'react'
import type { ApiClient } from '../api/client'
import type { JobOut } from '../api/types'
import { useAuthErrorHandler } from '../auth/useAuthErrorHandler'

const ACTIVE_STATUSES = new Set(['queued', 'running'])

export function useJobsPolling(apiClient: ApiClient, intervalMs = 4000) {
  const [jobs, setJobs] = useState<JobOut[]>([])
  const [error, setError] = useState<string | null>(null)
  const handleApiError = useAuthErrorHandler()

  const refresh = useCallback(async () => {
    try {
      const result = await apiClient.listJobs()
      setJobs(result)
      setError(null)
    } catch (err) {
      setError(handleApiError(err))
    }
  }, [apiClient, handleApiError])

  // Always fetch once on mount, regardless of what's currently in `jobs`.
  useEffect(() => {
    refresh()
  }, [refresh])

  // Only keep polling while at least one job is still queued/running --
  // no point hammering the API once everything's in a terminal state.
  useEffect(() => {
    const hasActiveJob = jobs.some((job) => ACTIVE_STATUSES.has(job.status))
    if (!hasActiveJob) return undefined

    const id = setInterval(refresh, intervalMs)
    return () => clearInterval(id)
  }, [jobs, intervalMs, refresh])

  return { jobs, error, refresh }
}
