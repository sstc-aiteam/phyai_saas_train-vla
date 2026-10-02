import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { LoginPage } from '../../src/pages/LoginPage'
import { ApiError } from '../../src/api/errors'
import { FakeApiClient } from '../api/fakeApiClient'
import { renderWithProviders } from '../test-utils'

describe('LoginPage', () => {
  it('logs in and navigates to /jobs on success', async () => {
    const client = new FakeApiClient()
    renderWithProviders(<LoginPage />, {
      client,
      initialPath: '/login',
      routes: { '/jobs': <div>JOBS PAGE</div> },
    })

    await userEvent.type(screen.getByLabelText('Email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'password123')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('JOBS PAGE')).toBeInTheDocument()
  })

  it('shows an error message for invalid credentials and stays on the page', async () => {
    const client = new FakeApiClient()
    client.nextError = { method: 'login', error: new ApiError(401, 'Invalid email or password') }

    renderWithProviders(<LoginPage />, {
      client,
      initialPath: '/login',
      routes: { '/jobs': <div>JOBS PAGE</div> },
    })

    await userEvent.type(screen.getByLabelText('Email'), 'a@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByText('Invalid email or password')).toBeInTheDocument()
    expect(screen.queryByText('JOBS PAGE')).not.toBeInTheDocument()
  })
})
