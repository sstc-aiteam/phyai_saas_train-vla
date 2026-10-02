import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AccountPage } from '../../src/pages/AccountPage'
import { ApiError } from '../../src/api/errors'
import { FakeApiClient } from '../api/fakeApiClient'
import { renderWithProviders } from '../test-utils'

describe('AccountPage', () => {
  it('changes the password and shows a success message', async () => {
    const client = new FakeApiClient()
    renderWithProviders(<AccountPage />, { client, initialPath: '/account' })

    await userEvent.type(screen.getByLabelText('Current password'), 'old-password')
    await userEvent.type(screen.getByLabelText('New password'), 'new-password123')
    await userEvent.click(screen.getByRole('button', { name: 'Update password' }))

    expect(await screen.findByText('Password updated.')).toBeInTheDocument()
    expect(client.calls).toEqual([{ method: 'changePassword', args: ['old-password', 'new-password123'] }])
  })

  it('shows an error message when the old password is wrong, without logging out', async () => {
    // Backend returns 400 for this (not 401) specifically so this case
    // stays distinguishable from an expired/invalid session token -- see
    // WrongOldPasswordError in auth_service.py.
    const client = new FakeApiClient()
    client.nextError = { method: 'changePassword', error: new ApiError(400, 'Old password is incorrect') }
    renderWithProviders(<AccountPage />, { client, initialPath: '/account' })

    await userEvent.type(screen.getByLabelText('Current password'), 'wrong')
    await userEvent.type(screen.getByLabelText('New password'), 'new-password123')
    await userEvent.click(screen.getByRole('button', { name: 'Update password' }))

    expect(await screen.findByText('Old password is incorrect')).toBeInTheDocument()
  })
})
