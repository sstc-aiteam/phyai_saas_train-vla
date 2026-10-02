import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApiClient } from '../api/ApiClientContext'
import type { PolicyType } from '../api/types'
import { useAuthErrorHandler } from '../auth/useAuthErrorHandler'

// Spec section 6: 20,000 is the hard cap on training steps, enforced
// server-side too (Pydantic Field(gt=0, le=20000) on the upload endpoints) --
// this is just so the form can reject obviously-bad input before a round trip.
const MAX_TRAINING_STEPS = 20_000

type SourceMode = 'hf_hub' | 'zip_upload'

export function NewJobPage() {
  const [sourceMode, setSourceMode] = useState<SourceMode>('hf_hub')
  const [repoId, setRepoId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [policy, setPolicy] = useState<PolicyType>('act')
  const [trainingSteps, setTrainingSteps] = useState(1000)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const apiClient = useApiClient()
  const handleApiError = useAuthErrorHandler()
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (sourceMode === 'hf_hub') {
        await apiClient.submitHfDataset(repoId, policy, trainingSteps)
      } else {
        if (!file) {
          setError('Choose a zip file to upload.')
          return
        }
        const { upload_id, upload_url } = await apiClient.createZipUploadTarget()
        await apiClient.uploadZipFile(upload_url, file)
        await apiClient.confirmZipUpload(upload_id, policy, trainingSteps)
      }
      navigate('/jobs')
    } catch (err) {
      setError(handleApiError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>New training job</h1>

      <fieldset>
        <legend>Dataset source</legend>
        <label>
          <input
            type="radio"
            name="sourceMode"
            checked={sourceMode === 'hf_hub'}
            onChange={() => setSourceMode('hf_hub')}
          />
          Hugging Face Hub dataset (public only)
        </label>
        <label>
          <input
            type="radio"
            name="sourceMode"
            checked={sourceMode === 'zip_upload'}
            onChange={() => setSourceMode('zip_upload')}
          />
          Upload a zip file (max 2GB)
        </label>
      </fieldset>

      {sourceMode === 'hf_hub' ? (
        // key is required here: without it, React reuses the same <input>
        // DOM node across the text/file branches and just mutates its
        // `type` attribute in place, which breaks React's controlled-input
        // value tracking (text's `value` prop vs file's lack of one) --
        // surfaced as a "controlled to uncontrolled" warning and a file
        // input that silently stops registering uploads.
        <label key="hf">
          HF repo id
          <input
            type="text"
            required
            placeholder="lerobot/pusht"
            value={repoId}
            onChange={(e) => setRepoId(e.target.value)}
          />
        </label>
      ) : (
        <label key="zip">
          Dataset zip file
          {/* Not `required`: validated manually below instead (the "if
              (!file)" check) -- the browser's native required-field
              validation for file inputs is unreliable (jsdom's constraint
              validation API never marks a file input as valid even once
              `.files` is set, so rely on this app's own check for both
              real browsers and tests). */}
          <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      )}

      <label>
        Policy
        <select value={policy} onChange={(e) => setPolicy(e.target.value as PolicyType)}>
          <option value="act">ACT</option>
          <option value="smolvla">SmolVLA</option>
        </select>
      </label>

      <label>
        Training steps
        <input
          type="number"
          required
          min={1}
          max={MAX_TRAINING_STEPS}
          value={trainingSteps}
          onChange={(e) => setTrainingSteps(Number(e.target.value))}
        />
      </label>

      {error && <p className="error-message">{error}</p>}
      <button type="submit" disabled={submitting}>
        Submit job
      </button>
    </form>
  )
}
