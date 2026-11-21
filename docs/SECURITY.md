# Security

- Argon2id password hashing, hashed 256-bit server-side session tokens, expiry, revocation, and session-bound double-submit CSRF protect private routes. Owner-scoped queries return 404 across accounts. Rate limits are per-process.
- The model receives delimited transcript data and structured-output instructions with zero tools. Schema and evidence checks constrain proposals. React renders evidence as text. Authenticated review state and a separate confirmation gate external action.
- A server-only fine-grained GitHub PAT should cover a single demo repo with Issues read/write. A production multi-tenant system would require a GitHub App or individually scoped encrypted tokens.
- Staging/production enforce HTTPS, secure cookies and HSTS with configured proxy trust. SMTP uses STARTTLS and delivery runs after the reset-request response. SQLite and backups have no application-layer encryption at rest. Verify deployment encryption and access controls before using real data.
- Reset tokens are hashed and expire after 30 minutes. Dev outbox files contain live reset links and need private local access. Account deletion uses password reauth and cascades owned records. Append-only audit records retain keyed references, omit transcript text and survive deletion. External issues and backup copies follow their own retention.
- Request logs contain safe metadata and sanitized exception indications. Keep request bodies and headers out of infrastructure logs. Sentry is disabled by omission.
- For incidents, isolate the affected component, retain logs, identify impacted users, revoke and rotate credentials where needed, assess external effects and verify recovery. Rotating the audit key changes per-user audit references.

Login and reset responses are generic. Registration still distinguishes a successful new registration from a duplicate. Production TLS, encryption, monitoring, live integrations and independent penetration testing are UNVERIFIED.
