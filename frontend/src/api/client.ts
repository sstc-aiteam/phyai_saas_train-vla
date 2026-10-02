import { ApiError } from './errors'
import type { JobOut, PolicyType, TokenOut, UploadTargetOut } from './types'

// Interface first, real fetch-based implementation below -- tests inject a
// hand-written FakeApiClient implementing the same shape instead of mocking
// fetch, matching the backend/worker's ports-and-fakes convention.
export interface ApiClient {
  register(email: string, password: string, captchaToken: string): Promise<TokenOut>
  login(email: string, password: string): Promise<TokenOut>
  changePassword(oldPassword: string, newPassword: string): Promise<void>
  createZipUploadTarget(): Promise<UploadTargetOut>
  uploadZipFile(uploadUrl: string, file: File): Promise<void>
  confirmZipUpload(uploadId: string, policy: PolicyType, trainingSteps: number): Promise<JobOut>
  submitHfDataset(repoId: string, policy: PolicyType, trainingSteps: number): Promise<JobOut>
  listJobs(): Promise<JobOut[]>
  cancelJob(jobId: string): Promise<JobOut>
  getDownloadUrl(jobId: string): Promise<string>
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // body wasn't JSON (or had no `detail`) -- fall through to a generic message
  }
  return `Request failed with status ${response.status}`
}

export function createApiClient(baseUrl: string, getToken: () => string | null): ApiClient {
  async function request<T>(path: string, options: RequestInit = {}, auth = true): Promise<T> {
    const headers = new Headers(options.headers)
    headers.set('Content-Type', 'application/json')
    if (auth) {
      const token = getToken()
      if (token) headers.set('Authorization', `Bearer ${token}`)
    }

    const response = await fetch(`${baseUrl}${path}`, { ...options, headers })
    if (!response.ok) {
      throw new ApiError(response.status, await parseErrorDetail(response))
    }
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  return {
    register(email, password, captchaToken) {
      return request<TokenOut>(
        '/auth/register',
        { method: 'POST', body: JSON.stringify({ email, password, captcha_token: captchaToken }) },
        false,
      )
    },

    login(email, password) {
      return request<TokenOut>(
        '/auth/login',
        { method: 'POST', body: JSON.stringify({ email, password }) },
        false,
      )
    },

    async changePassword(oldPassword, newPassword) {
      await request<void>('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      })
    },

    createZipUploadTarget() {
      return request<UploadTargetOut>('/uploads/zip/target', { method: 'POST', body: '{}' })
    },

    async uploadZipFile(uploadUrl, file) {
      // Direct browser -> GCS PUT against the signed URL, not our backend
      // (spec: zip upload bypasses the backend entirely). Needs the GCS
      // bucket's own CORS policy, not this app's API CORS config -- see
      // deploy/gcs-cors.json.
      const response = await fetch(uploadUrl, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': 'application/zip' },
      })
      if (!response.ok) {
        throw new ApiError(response.status, `Dataset upload failed with status ${response.status}`)
      }
    },

    confirmZipUpload(uploadId, policy, trainingSteps) {
      return request<JobOut>('/uploads/zip/confirm', {
        method: 'POST',
        body: JSON.stringify({ upload_id: uploadId, policy, training_steps: trainingSteps }),
      })
    },

    submitHfDataset(repoId, policy, trainingSteps) {
      return request<JobOut>('/uploads/hf-dataset', {
        method: 'POST',
        body: JSON.stringify({ repo_id: repoId, policy, training_steps: trainingSteps }),
      })
    },

    listJobs() {
      return request<JobOut[]>('/jobs')
    },

    cancelJob(jobId) {
      return request<JobOut>(`/jobs/${jobId}/cancel`, { method: 'POST' })
    },

    async getDownloadUrl(jobId) {
      const result = await request<{ url: string }>(`/jobs/${jobId}/download-url`)
      return result.url
    },
  }
}
