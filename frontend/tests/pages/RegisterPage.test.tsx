import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { RegisterPage } from '../../src/pages/RegisterPage'
import { FakeApiClient } from '../api/fakeApiClient'
import { renderWithProviders } from '../test-utils'

beforeEach(() => {
  window.grecaptcha = {
    ready: (callback) => callback(),
    execute: async () => 'fake-captcha-token',
  }
})

afterEach(() => {
  delete window.grecaptcha
})

describe('RegisterPage', () => {
  it('registers with a recaptcha token and navigates to /jobs on success', async () => {
    const client = new FakeApiClient()
    renderWithProviders(<RegisterPage />, {
      client,
      initialPath: '/register',
      routes: { '/jobs': <div>JOBS PAGE</div> },
    })

    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'password123')
    await userEvent.click(screen.getByRole('button', { name: 'Register' }))

    expect(await screen.findByText('JOBS PAGE')).toBeInTheDocument()
    expect(client.calls).toEqual([
      { method: 'register', args: ['new@example.com', 'password123', 'fake-captcha-token'] },
    ])
  })

  it('shows the backend error message and does not navigate on failure', async () => {
    const client = new FakeApiClient()
    const { ApiError } = await import('../../src/api/errors')
    client.nextError = { method: 'register', error: new ApiError(400, 'reCAPTCHA verification failed') }

    renderWithProviders(<RegisterPage />, {
      client,
      initialPath: '/register',
      routes: { '/jobs': <div>JOBS PAGE</div> },
    })

    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'password123')
    await userEvent.click(screen.getByRole('button', { name: 'Register' }))

    expect(await screen.findByText('reCAPTCHA verification failed')).toBeInTheDocument()
    expect(screen.queryByText('JOBS PAGE')).not.toBeInTheDocument()
  })
})
