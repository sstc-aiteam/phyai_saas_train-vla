import { afterEach, describe, expect, it } from 'vitest'
import { executeRecaptcha } from '../../src/hooks/useRecaptcha'

afterEach(() => {
  delete window.grecaptcha
})

describe('executeRecaptcha', () => {
  it('resolves with the token grecaptcha.execute produces, once grecaptcha is ready', async () => {
    window.grecaptcha = {
      ready: (callback) => callback(),
      execute: async (siteKey, options) => `token-for-${siteKey}-${options.action}`,
    }

    const token = await executeRecaptcha('site-key-123', 'register')

    expect(token).toBe('token-for-site-key-123-register')
  })

  it('rejects if grecaptcha.execute rejects', async () => {
    window.grecaptcha = {
      ready: (callback) => callback(),
      execute: async () => {
        throw new Error('recaptcha backend unavailable')
      },
    }

    await expect(executeRecaptcha('site-key-123', 'register')).rejects.toThrow('recaptcha backend unavailable')
  })

  it('rejects (not hangs) if grecaptcha.execute throws synchronously inside ready()', async () => {
    // This is what a real invalid/missing site key actually does in a
    // browser -- confirmed by running the register page against the real
    // Google script with no site key configured: it throws synchronously
    // from inside ready()'s callback rather than returning a rejected
    // promise. Without the try/catch this guards, that throw escapes as
    // an uncaught error and this function's promise never settles at all.
    window.grecaptcha = {
      ready: (callback) => callback(),
      execute: () => {
        throw new Error('Invalid reCAPTCHA client id')
      },
    }

    await expect(executeRecaptcha('', 'register')).rejects.toThrow('Invalid reCAPTCHA client id')
  })

  it('rejects if grecaptcha.ready never calls back within the timeout', async () => {
    window.grecaptcha = {
      ready: () => {
        /* never calls the callback -- simulates a silently stalled init */
      },
      execute: async () => 'unused',
    }

    await expect(executeRecaptcha('site-key-123', 'register')).rejects.toThrow('reCAPTCHA timed out')
  }, 11_000)
})
