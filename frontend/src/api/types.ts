// Mirrors the backend's actual wire contract (src/backend/api/*.py),
// confirmed by reading the Pydantic models directly, not guessed.

export type PolicyType = 'act' | 'smolvla'

// JobOut.status is the *display* status (job_service collapses
// initializing/training into "running" server-side) -- never the
// internal queued/initializing/training/completed/failed/cancelled.
export type DisplayJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface TokenOut {
  access_token: string
  token_type: string
}

export interface JobProgress {
  step: number
  total_steps: number
  loss: number
}

export interface JobOut {
  id: string
  policy: PolicyType
  source_type: 'hf_hub' | 'zip_upload'
  training_steps: number
  status: DisplayJobStatus
  queue_position: number | null
  progress: JobProgress | null
  error_message: string | null
  created_at: string
}

export interface UploadTargetOut {
  upload_id: string
  upload_url: string
}
