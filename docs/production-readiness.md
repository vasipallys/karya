# Production readiness

Karya has two different release profiles:

- **Desktop / trusted single-user:** the Electron shell starts a loopback API and
  stores data in the current user's application-data directory. This profile is
  suitable for controlled releases after the verification commands below pass.
- **Shared web / multi-user:** the current `X-User-Id` / `X-User-Role` login is
  intentionally demo-grade. Do not expose the API to an untrusted network until
  a real identity provider is integrated and the backend derives roles from
  verified identity claims.

## Release gate

Run from the repository root with the intended production provider configuration:

```powershell
npm ci
node scripts/run-python.mjs -m pip check
npm run test:all
npm run build
node --check desktop/electron/main.cjs
node scripts/run-python.mjs -m compileall -q backend desktop scripts
npm audit --omit=dev
```

The API health endpoint must return HTTP 200. `status: "degraded"` means the API
is alive but its provider configuration needs attention; do not mark the release
healthy until the intended LLM and Jira integrations report the expected state.

## Shared-web deployment gates

Complete these before an internet or enterprise-network deployment:

1. Replace local demo login with OIDC/OAuth2 or another organization-approved
   identity provider. The public API must not trust caller-supplied role headers.
2. Terminate TLS at a supported reverse proxy, restrict direct access to the API,
   set `CORS_ORIGINS` to exact HTTPS origins, and add request/body/rate limits at
   the edge.
3. Use a managed secrets store for LLM, Jira, LDAP, and connector credentials.
   Do not distribute populated `.env` files.
4. Keep SQLite for a single API process only. For multiple replicas or materially
   concurrent workloads, migrate persistence and LangGraph checkpoints to a
   supported shared database before scaling out.
5. Schedule and test backups for the Karya database, checkpoint database, and
   desktop user-data directory. Test restore, not only backup creation.
6. Restrict repository scanning and import features to trusted operators and
   approved filesystem roots on a server deployment.
7. Forward structured server logs to monitoring. Preserve `X-Request-Id` through
   the proxy so a user-visible failure can be correlated with server logs.
8. Add environment-specific availability targets, alerting, retention, privacy,
   data-classification, disaster-recovery, and vulnerability-response policies.

## Built-in safety boundaries

- Writes are capability-checked server-side; restricted projects also apply the
  repository's ABAC rule.
- C4 mutations proposed by AI remain review-first and are revalidated on apply.
- Uploads and rendered-diagram export payloads are bounded.
- CPU-heavy document generation and spreadsheet parsing run off the async request
  loop.
- API failures use a stable envelope, redact unhandled exception details, and
  include a request ID.
- Responses set clickjacking, MIME-sniffing, referrer, and browser-permission
  protections.
- The frontend clears stale sessions after a 401 and contains fatal render errors
  behind a recovery screen.
- The Electron shell validates the API health response, isolates the renderer,
  and blocks navigation outside the trusted application origin.

## Known non-blocking engineering work

- Mermaid's complete renderer catalog produces some build chunks above Vite's
  500 kB advisory threshold. Views are already split by workspace, but further
  lazy loading can improve first-load performance on slow networks.
- The full development dependency audit may report issues in packaging-only
  transitive dependencies. Evaluate Electron Builder updates separately; the
  shipped web runtime gate is `npm audit --omit=dev`.
- LangGraph currently emits an upstream pending-deprecation warning for its
  serializer defaults. Track it during dependency upgrades; it does not fail the
  checkpoint or regression suites.

