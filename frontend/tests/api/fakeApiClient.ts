import type { ApiClient } from '../../src/api/client'
import { ApiError } from '../../src/api/errors'
import type { JobOut, PolicyType, TokenOut, UploadTargetOut } from '../../src/api/types'

// Hand-rolled fake implementing the real ApiClient interface, mirroring
// tests/backend/fakes/* in the Python side -- tests configure its state
// directly and assert on `calls`, instead of mocking fetch.
export class FakeApiClient implements ApiClient {
  jobs: JobOut[] = []
  calls: { method: string; args: unknown[] }[] = []

  // Set to an ApiError (or any Error) to make the next matching call throw.
  nextError: { method: string; error: Error } | null = null

  private record(method: string, args: unknown[]) {
    this.calls.push({ method, args })
    if (this.nextError?.method === method) {
      const err = this.nextError.error
      this.nextError = null
      throw err
    }
  }

  async register(email: string, password: string, captchaToken: string): Promise<TokenOut> {
    this.record('register', [email, password, captchaToken])
    return { access_token: 'fake-token', token_type: 'bearer' }
  }

  async login(email: string, password: string): Promise<TokenOut> {
    this.record('login', [email, password])
    return { access_token: 'fake-token', token_type: 'bearer' }
  }

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    this.record('changePassword', [oldPassword, newPassword])
  }

  async createZipUploadTarget(): Promise<UploadTargetOut> {
    this.record('createZipUploadTarget', [])
    return { upload_id: 'upload-1', upload_url: 'https://storage.example.com/signed-put' }
  }

  async uploadZipFile(uploadUrl: string, file: File): Promise<void> {
    this.record('uploadZipFile', [uploadUrl, file])
  }

  async confirmZipUpload(uploadId: string, policy: PolicyType, trainingSteps: number): Promise<JobOut> {
    this.record('confirmZipUpload', [uploadId, policy, trainingSteps])
    const job = makeJob({ policy, training_steps: trainingSteps, source_type: 'zip_upload' })
    this.jobs.push(job)
    return job
  }

  async submitHfDataset(repoId: string, policy: PolicyType, trainingSteps: number): Promise<JobOut> {
    this.record('submitHfDataset', [repoId, policy, trainingSteps])
    const job = makeJob({ policy, training_steps: trainingSteps, source_type: 'hf_hub' })
    this.jobs.push(job)
    return job
  }

  async listJobs(): Promise<JobOut[]> {
    this.record('listJobs', [])
    return this.jobs
  }

  async cancelJob(jobId: string): Promise<JobOut> {
    this.record('cancelJob', [jobId])
    const job = this.jobs.find((j) => j.id === jobId)
    if (!job) throw new ApiError(404, 'Job not found')
    job.status = 'cancelled'
    return job
  }

  async getDownloadUrl(jobId: string): Promise<string> {
    this.record('getDownloadUrl', [jobId])
    return `https://storage.example.com/checkpoints/${jobId}.zip`
  }
}

let jobCounter = 0

export function makeJob(overrides: Partial<JobOut> = {}): JobOut {
  jobCounter += 1
  return {
    id: `job-${jobCounter}`,
    policy: 'act',
    source_type: 'hf_hub',
    training_steps: 1000,
    status: 'queued',
    queue_position: 1,
    progress: null,
    error_message: null,
    created_at: new Date().toISOString(),
    ...overrides,
  }
}
