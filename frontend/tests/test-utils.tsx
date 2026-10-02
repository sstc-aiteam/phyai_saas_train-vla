import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ApiClientProvider } from '../src/api/ApiClientContext'
import { AuthProvider } from '../src/auth/AuthContext'
import type { ApiClient } from '../src/api/client'
import type { ReactElement } from 'react'

interface RenderWithProvidersOptions {
  client: ApiClient
  initialPath?: string
  // Extra routes to register alongside the one at `initialPath`, so a test
  // can assert on where navigation ends up (e.g. { '/jobs': <div>JOBS</div> }).
  routes?: Record<string, ReactElement>
}

export function renderWithProviders(
  element: ReactElement,
  { client, initialPath = '/', routes = {} }: RenderWithProvidersOptions,
) {
  return render(
    <AuthProvider>
      <ApiClientProvider client={client}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path={initialPath} element={element} />
            {Object.entries(routes).map(([path, routeElement]) => (
              <Route key={path} path={path} element={routeElement} />
            ))}
          </Routes>
        </MemoryRouter>
      </ApiClientProvider>
    </AuthProvider>,
  )
}
