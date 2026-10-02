import { useState, type FormEvent } from 'react'
import { useApiClient } from '../api/ApiClientContext'
import { useAuthErrorHandler } from '../auth/useAuthErrorHandler'

export function AccountPage() {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const apiClient = useApiClient()
  const handleApiError = useAuthErrorHandler()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    setSuccess(false)
    try {
      await apiClient.changePassword(oldPassword, newPassword)
      setSuccess(true)
      setOldPassword('')
      setNewPassword('')
    } catch (err) {
      setError(handleApiError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>Change password</h1>
      <label>
        Current password
        <input
          type="password"
          required
          value={oldPassword}
          onChange={(e) => setOldPassword(e.target.value)}
        />
      </label>
      <label>
        New password
        <input
          type="password"
          required
          minLength={8}
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
      </label>
      {error && <p className="error-message">{error}</p>}
      {success && <p>Password updated.</p>}
      <button type="submit" disabled={submitting}>
        Update password
      </button>
    </form>
  )
}
