import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { NewJobPage } from '../../src/pages/NewJobPage'
import { FakeApiClient } from '../api/fakeApiClient'
import { renderWithProviders } from '../test-utils'

describe('NewJobPage', () => {
  it('submits the HF Hub path by calling submitHfDataset with the form values', async () => {
    const client = new FakeApiClient()
    renderWithProviders(<NewJobPage />, {
      client,
      initialPath: '/jobs/new',
      routes: { '/jobs': <div>JOBS PAGE</div> },
    })

    await userEvent.type(screen.getByLabelText('HF repo id'), 'lerobot/pusht')
    await userEvent.selectOptions(screen.getByLabelText('Policy'), 'smolvla')
    const steps = screen.getByLabelText('Training steps')
    await userEvent.clear(steps)
    await userEvent.type(steps, '500')
    await userEvent.click(screen.getByRole('button', { name: 'Submit job' }))

    expect(await screen.findByText('JOBS PAGE')).toBeInTheDocument()
    expect(client.calls).toEqual([{ method: 'submitHfDataset', args: ['lerobot/pusht', 'smolvla', 500] }])
  })

  it('submits the zip path as target -> upload -> confirm, in order', async () => {
    const client = new FakeApiClient()
    renderWithProviders(<NewJobPage />, {
      client,
      initialPath: '/jobs/new',
      routes: { '/jobs': <div>JOBS PAGE</div> },
    })

    await userEvent.click(screen.getByLabelText('Upload a zip file (max 2GB)'))
    const file = new File(['zip-bytes'], 'dataset.zip', { type: 'application/zip' })
    await userEvent.upload(screen.getByLabelText('Dataset zip file'), file)
    await userEvent.click(screen.getByRole('button', { name: 'Submit job' }))

    expect(await screen.findByText('JOBS PAGE')).toBeInTheDocument()
    expect(client.calls.map((c) => c.method)).toEqual([
      'createZipUploadTarget',
      'uploadZipFile',
      'confirmZipUpload',
    ])
    expect(client.calls[1].args[0]).toBe('https://storage.example.com/signed-put')
    expect(client.calls[2].args).toEqual(['upload-1', 'act', 1000])
  })

  it('shows an inline error and does not navigate when the backend rejects the dataset', async () => {
    const client = new FakeApiClient()
    const { ApiError } = await import('../../src/api/errors')
    client.nextError = { method: 'submitHfDataset', error: new ApiError(404, 'HF dataset repo not found') }

    renderWithProviders(<NewJobPage />, {
      client,
      initialPath: '/jobs/new',
      routes: { '/jobs': <div>JOBS PAGE</div> },
    })

    await userEvent.type(screen.getByLabelText('HF repo id'), 'org/missing')
    await userEvent.click(screen.getByRole('button', { name: 'Submit job' }))

    expect(await screen.findByText('HF dataset repo not found')).toBeInTheDocument()
    expect(screen.queryByText('JOBS PAGE')).not.toBeInTheDocument()
  })
})
