# Inci-dental development rules

Use Hexagonal Architecture with strict dependencies:
`api -> application -> domain <- infrastructure`.

- Domain files use only the Python standard library. They contain state and
  invariants, never HTTP clients, configuration, or framework imports.
- Application commands orchestrate the aggregate and ports. Queries are read-only.
- Infrastructure adapters use public third-party libraries and implement domain
  ports. Do not introduce private company SDKs or company-specific integrations.
- API handlers only authenticate, validate, translate errors, and return responses.
- Construct dependencies once in `app/HttpHandler/api.py`.
- Preserve auditability and incident-group references across process restarts.
- Never log API tokens, credentials, or sensitive request/response bodies.
- Keep the scope focused on incident management. Do not add traffic migration,
  load shedding, simulations, shift delivery, or membership synchronization.
- Extend existing modules and prefer the smallest readable implementation.
- Add tests for state transitions, orchestration failures, adapters, and API auth.
- Keep README.md and docs/ consistent with every endpoint, configuration, or
  architectural change.
