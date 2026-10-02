import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'

// AuthContext reads/writes real localStorage; without this, state from one
// test's login() would leak into the next test in the same file.
beforeEach(() => {
  localStorage.clear()
})
