import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApiClient } from '../api/ApiClientContext'
import { describeError } from '../api/errors'
import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const apiClient = useApiClient()
  const { login } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const { access_token } = await apiClient.login(email, password)
      login(access_token, email)
      navigate('/jobs')
    } catch (err) {
      // Deliberately not useAuthErrorHandler: a 401 here means "wrong
      // credentials," not "session expired" -- there's no session to log
      // out of yet, and redirecting to /login from /login would be absurd.
      setError(describeError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>Log in</h1>
      <label>
        Email
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        Password
        <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      {error && <p className="error-message">{error}</p>}
      <button type="submit" disabled={submitting}>
        Log in
      </button>
      <p>
        Need an account? <Link to="/register">Register</Link>
      </p>
    </form>
  )
}
