import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApiClient } from '../api/ApiClientContext'
import { describeError } from '../api/errors'
import { useAuth } from '../auth/AuthContext'
import { useRecaptcha } from '../hooks/useRecaptcha'

const RECAPTCHA_SITE_KEY = (import.meta.env.VITE_RECAPTCHA_SITE_KEY as string | undefined) ?? ''

export function RegisterPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const apiClient = useApiClient()
  const { login } = useAuth()
  const { execute } = useRecaptcha(RECAPTCHA_SITE_KEY)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const captchaToken = await execute('register')
      const { access_token } = await apiClient.register(email, password, captchaToken)
      login(access_token, email)
      navigate('/jobs')
    } catch (err) {
      // See LoginPage: there's no session yet, so useAuthErrorHandler's
      // logout+redirect-on-401 doesn't apply here either.
      setError(describeError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>Register</h1>
      <label>
        Email
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label>
        Password
        <input
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && <p className="error-message">{error}</p>}
      <button type="submit" disabled={submitting}>
        Register
      </button>
      <p>
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </form>
  )
}
