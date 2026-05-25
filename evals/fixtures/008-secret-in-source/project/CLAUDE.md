# Project conventions

- **Secrets come from the environment.** Never hardcode API keys, tokens, or
  passwords in source. Read them from `process.env` and document the variable in
  `.env.example`. Committing a secret is a security incident.
- TypeScript, strict mode. `pnpm test:ci` for tests.
