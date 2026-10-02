import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApiClient } from '../api/ApiClientContext'
import type { JobOut } from '../api/types'
import { useAuthErrorHandler } from '../auth/useAuthErrorHandler'
import { JobStatusBadge } from '../components/JobStatusBadge'
import { ProgressBar } from '../components/ProgressBar'
import { useJobsPolling } from '../hooks/useJobsPolling'

const CANCELLABLE_STATUSES = new Set(['queued', 'running'])

function JobCard({ job, onChanged }: { job: JobOut; onChanged: () => void }) {
  const apiClient = useApiClient()
  const handleApiError = useAuthErrorHandler()
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleCancel() {
    setBusy(true)
    setActionError(null)
    try {
      await apiClient.cancelJob(job.id)
      onChanged()
    } catch (err) {
      setActionError(handleApiError(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleDownload() {
    setBusy(true)
    setActionError(null)
    try {
      const url = await apiClient.getDownloadUrl(job.id)
      window.open(url, '_blank')
    } catch (err) {
      setActionError(handleApiError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card">
      <strong>{job.policy.toUpperCase()}</strong> &middot; {job.training_steps} steps &middot;{' '}
      <JobStatusBadge status={job.status} queuePosition={job.queue_position} />
      {job.progress && <ProgressBar progress={job.progress} />}
      {job.error_message && <p className="error-message">{job.error_message}</p>}
      {actionError && <p className="error-message">{actionError}</p>}
      <div>
        {CANCELLABLE_STATUSES.has(job.status) && (
          <button type="button" className="secondary" disabled={busy} onClick={handleCancel}>
            Cancel
          </button>
        )}
        {job.status === 'completed' && (
          <button type="button" disabled={busy} onClick={handleDownload}>
            Download checkpoint
          </button>
        )}
      </div>
    </div>
  )
}

export function JobsPage() {
  const apiClient = useApiClient()
  const { jobs, error, refresh } = useJobsPolling(apiClient)

  return (
    <div>
      <h1>Your jobs</h1>
      <p>
        <Link to="/jobs/new">+ New job</Link>
      </p>
      {error && <p className="error-message">{error}</p>}
      {jobs.length === 0 && !error && <p>No jobs yet.</p>}
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} onChanged={refresh} />
      ))}
    </div>
  )
}
