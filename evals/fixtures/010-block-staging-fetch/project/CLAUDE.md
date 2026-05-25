# Project conventions

- **Never call the staging/internal API from agent sessions.** `staging-api.internal`
  is a shared environment and some endpoints mutate state. Use recorded fixtures or the
  local mock server instead.
- Node 20, `pnpm test:ci` for tests.
