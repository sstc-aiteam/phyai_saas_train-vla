import type { DisplayJobStatus } from '../api/types'

const LABELS: Record<DisplayJobStatus, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export function JobStatusBadge({ status, queuePosition }: { status: DisplayJobStatus; queuePosition: number | null }) {
  const label = LABELS[status]
  if (status === 'queued' && queuePosition != null) {
    return <span>{label} (position {queuePosition})</span>
  }
  return <span>{label}</span>
}
