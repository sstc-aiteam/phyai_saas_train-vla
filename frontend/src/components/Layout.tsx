import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Layout({ children }: { children: ReactNode }) {
  const { email, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div>
      <nav>
        <NavLink to="/jobs">Jobs</NavLink>
        <NavLink to="/jobs/new">New job</NavLink>
        <NavLink to="/account">Account</NavLink>
        <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>{email}</span>
        <button type="button" className="secondary" onClick={handleLogout}>
          Log out
        </button>
      </nav>
      {children}
    </div>
  )
}
