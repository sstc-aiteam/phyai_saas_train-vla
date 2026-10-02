# LeRobot Training Service — frontend

React + Vite + TypeScript SPA covering the golden path described in the
main repo's [README.md](../README.md#frontend): register/login, submit a
training job (HF Hub dataset or zip upload), poll job status, cancel,
download. See that file for what's built, what's verified, and the two
real bugs actually running this in a browser caught.

## Setup

```bash
npm install
cp .env.example .env.local
```

Fill in `.env.local`:
- `VITE_API_BASE_URL` — defaults to `http://localhost:8000`, the backend's
  own local-dev default port.
- `VITE_RECAPTCHA_SITE_KEY` — the reCAPTCHA v3 *site* key (public, safe in
  frontend JS). Get it from the same reCAPTCHA admin console page the
  backend's secret key came from. Without it, the register page's
  reCAPTCHA call fails cleanly (shows an error, per the fix in
  `src/hooks/useRecaptcha.ts`) rather than succeeding.

## Running

```bash
npm run dev     # :5173 — matches the backend's default CORS allowlist
npm run test    # Vitest + React Testing Library
npm run build   # tsc -b && vite build -> dist/
```

The backend must be running separately (`uv run uvicorn backend.main:app
--reload` from the repo root) and reachable at `VITE_API_BASE_URL`. Its
default `Settings.cors_allowed_origins` already includes
`http://localhost:5173`, so no backend config is needed for local dev.

## Architecture

- `src/api/client.ts` — `ApiClient` interface + a `fetch`-based real
  implementation. Tests inject a hand-written `FakeApiClient`
  (`tests/api/fakeApiClient.ts`) instead of mocking `fetch`, matching the
  backend/worker's ports-and-fakes convention in the rest of this repo.
- `src/auth/` — token + email in `localStorage`; `useAuthErrorHandler`
  centralizes the one cross-cutting rule (a 401 on an *authenticated*
  call means the session died — log out, redirect to `/login`). Login
  and register's own 401s (wrong credentials) deliberately don't go
  through this — see the comments in `LoginPage.tsx`/`RegisterPage.tsx`.
- `src/pages/`, `src/components/`, `src/hooks/` — one file per page/concern.
- `tests/` mirrors `src/`'s structure.

Not built yet: HF OAuth login (no real OAuth app configured on the
backend), and deploying this anywhere (Firebase Hosting per the spec).
