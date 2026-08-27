import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest } from '../services/api'

describe('apiRequest', () => {
  afterEach(() => vi.restoreAllMocks())

  it('maps structured provider errors to a user-facing message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: 'provider_timeout', message: 'raw', retry_count: 2 },
    }), { status: 502, headers: { 'Content-Type': 'application/json' } })))
    await expect(apiRequest('/agent/plan')).rejects.toMatchObject({
      code: 'provider_timeout', retryCount: 2, message: '模型响应超时，请稍后重试。',
    } satisfies Partial<ApiError>)
  })

  it('returns JSON for successful requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })))
    await expect(apiRequest('/health')).resolves.toEqual({ status: 'ok' })
  })
})
