import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { JobsPage } from '../../src/pages/JobsPage'
import { FakeApiClient, makeJob } from '../api/fakeApiClient'
import { renderWithProviders } from '../test-utils'

beforeEach(() => {
  vi.stubGlobal('open', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('JobsPage', () => {
  it('shows a cancel button for queued/running jobs but not for terminal ones', async () => {
    const client = new FakeApiClient()
    client.jobs = [
      makeJob({ id: 'job-queued', status: 'queued' }),
      makeJob({ id: 'job-completed', status: 'completed' }),
    ]
    renderWithProviders(<JobsPage />, { client, initialPath: '/jobs' })

    await screen.findAllByText('ACT', { exact: false })
    expect(screen.getAllByRole('button', { name: 'Cancel' })).toHaveLength(1)
  })

  it('shows a download button only for a completed job, and opens the signed URL', async () => {
    const client = new FakeApiClient()
    client.jobs = [makeJob({ id: 'job-completed', status: 'completed' })]
    renderWithProviders(<JobsPage />, { client, initialPath: '/jobs' })

    const downloadButton = await screen.findByRole('button', { name: 'Download checkpoint' })
    await userEvent.click(downloadButton)

    expect(window.open).toHaveBeenCalledWith('https://storage.example.com/checkpoints/job-completed.zip', '_blank')
  })

  it('cancelling a job calls cancelJob and refreshes the list', async () => {
    const client = new FakeApiClient()
    client.jobs = [makeJob({ id: 'job-queued', status: 'queued' })]
    renderWithProviders(<JobsPage />, { client, initialPath: '/jobs' })

    const cancelButton = await screen.findByRole('button', { name: 'Cancel' })
    await userEvent.click(cancelButton)

    expect(client.calls.map((c) => c.method)).toEqual(['listJobs', 'cancelJob', 'listJobs'])
    expect(await screen.findByText('Cancelled')).toBeInTheDocument()
  })

  it('shows "No jobs yet." when the list is empty', async () => {
    const client = new FakeApiClient()
    renderWithProviders(<JobsPage />, { client, initialPath: '/jobs' })

    expect(await screen.findByText('No jobs yet.')).toBeInTheDocument()
  })
})
