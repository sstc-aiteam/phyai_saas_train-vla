// reCAPTCHA v3 is invisible: there's no checkbox, just a script that must
// be loaded once, then grecaptcha.execute(siteKey, { action }) resolves a
// token per action. Only register needs this (per the spec's registration
// anti-abuse requirement).

declare global {
  interface Window {
    grecaptcha?: {
      ready: (callback: () => void) => void
      execute: (siteKey: string, options: { action: string }) => Promise<string>
    }
  }
}

let scriptLoadPromise: Promise<void> | null = null

function loadRecaptchaScript(siteKey: string): Promise<void> {
  if (window.grecaptcha) return Promise.resolve()
  if (scriptLoadPromise) return scriptLoadPromise

  scriptLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://www.google.com/recaptcha/api.js?render=${siteKey}`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load reCAPTCHA script'))
    document.head.appendChild(script)
  })
  return scriptLoadPromise
}

const EXECUTE_TIMEOUT_MS = 10_000

// Split out from the hook so tests can exercise the execute() logic by
// stubbing window.grecaptcha directly -- skips the script tag entirely,
// so no real network/DOM script loading needs testing (thin wire-up,
// reviewed by hand instead, same as the backend's own adapter modules).
export function executeRecaptcha(siteKey: string, action: string): Promise<string> {
  const attempt = loadRecaptchaScript(siteKey).then(
    () =>
      new Promise<string>((resolve, reject) => {
        const grecaptcha = window.grecaptcha
        if (!grecaptcha) {
          reject(new Error('reCAPTCHA failed to initialize'))
          return
        }
        // grecaptcha.execute (and ready's callback invoking it) can throw
        // synchronously rather than reject -- e.g. an invalid/missing site
        // key throws "Invalid reCAPTCHA client id" as an uncaught error
        // from inside this callback, which a bare .then/.catch chain never
        // sees (it's thrown outside this Promise's call stack by the time
        // grecaptcha invokes the callback). Without this try/catch, that
        // left the register form hung forever with no error shown --
        // confirmed by actually running it in a browser, not caught by
        // any unit test's necessarily well-behaved fake grecaptcha.
        try {
          grecaptcha.ready(() => {
            try {
              grecaptcha.execute(siteKey, { action }).then(resolve).catch(reject)
            } catch (err) {
              reject(err)
            }
          })
        } catch (err) {
          reject(err)
        }
      }),
  )

  // Belt-and-suspenders: if grecaptcha.ready() itself never calls back
  // (script loaded but internal init silently stalls -- blocked by an
  // ad-blocker's network filter rather than outright failing the script
  // request, for instance), don't leave the submit button disabled forever.
  let timeoutId: ReturnType<typeof setTimeout>
  const timeout = new Promise<string>((_, reject) => {
    timeoutId = setTimeout(() => reject(new Error('reCAPTCHA timed out. Please try again.')), EXECUTE_TIMEOUT_MS)
  })

  return Promise.race([attempt, timeout]).finally(() => clearTimeout(timeoutId))
}

export function useRecaptcha(siteKey: string) {
  return {
    execute: (action: string) => executeRecaptcha(siteKey, action),
  }
}
