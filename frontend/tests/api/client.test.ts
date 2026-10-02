import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApiClient } from '../../src/api/client'
import { ApiError } from '../../src/api/errors'

describe('createApiClient', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends an Authorization header for authenticated calls when a token is present', async () => {
    fetchMock.mockResolvedValue(new Response('[]', { status: 200 }))
    const client = createApiClient('http://api.example.com', () => 'my-token')

    await client.listJobs()

    const [, options] = fetchMock.mock.calls[0]
    expect((options.headers as Headers).get('Authorization')).toBe('Bearer my-token')
  })

  it('omits the Authorization header for register/login even if a token exists', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ access_token: 't', token_type: 'bearer' })))
    const client = createApiClient('http://api.example.com', () => 'stale-token')

    await client.login('a@example.com', 'password123')

    const [, options] = fetchMock.mock.calls[0]
    expect((options.headers as Headers).has('Authorization')).toBe(false)
  })

  it('throws an ApiError with the parsed detail message on a non-2xx response', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Invalid credentials' }), { status: 401 }))
    const client = createApiClient('http://api.example.com', () => null)

    await expect(client.login('a@example.com', 'wrong')).rejects.toMatchObject({
      status: 401,
      message: 'Invalid credentials',
    })
  })

  it('falls back to a generic message when the error body has no detail field', async () => {
    fetchMock.mockResolvedValue(new Response('not json', { status: 500 }))
    const client = createApiClient('http://api.example.com', () => null)

    await expect(client.login('a@example.com', 'x')).rejects.toBeInstanceOf(ApiError)
  })

  it('treats a 204 response as void instead of trying to parse an empty body as JSON', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    const client = createApiClient('http://api.example.com', () => 'token')

    await expect(client.changePassword('old', 'new')).resolves.toBeUndefined()
  })
})
