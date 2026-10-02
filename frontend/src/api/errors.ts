// Every backend error response is { detail: string } (see main.py's
// _EXCEPTION_STATUS_CODES table) -- this wraps that into a typed error so
// callers can branch on status (e.g. 401 -> log out) without re-parsing.
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

// For calls that are inherently unauthenticated (login, register): a 401
// here means "wrong credentials," not "your session expired," so it must
// never trigger useAuthErrorHandler's logout+redirect -- just show the
// message. Authenticated pages (jobs, uploads, account) use
// useAuthErrorHandler instead, precisely because their 401s *do* mean the
// session died.
export function describeError(err: unknown): string {
  if (err instanceof ApiError) return err.message
  return 'Something went wrong. Please try again.'
}
