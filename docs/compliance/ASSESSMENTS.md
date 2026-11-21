# Compliance foundations

- **Google CASA.** MeetFlow uses OpenAI and GitHub. It requests no Google OAuth scopes. Reassess CASA if Google Workspace access is added.
- **Microsoft review.** There is no Microsoft OAuth, Graph integration or marketplace listing. Reassess publisher verification and app review before adding these.
- **OWASP-oriented independent pentest.** Before production, commission an authorized assessment of authentication, sessions, reset, CSRF, authorization, resource limits, prompt handling, integration approvals, proxy trust, storage, backup and recovery. Track severity, remediation and retest evidence. No pentest or certification has occurred.
- **SSO.** Evaluate OIDC for production. Verify tenant mapping, account linking, offboarding, access recovery and lifecycle controls.
- **Email.** Verify SPF, DKIM, DMARC, alignment, bounce handling and blocklist monitoring before using a production sender.
- **Security questionnaire.** Passwords use Argon2id. TLS depends on deployment configuration. SQLite and backup files have no app-layer encryption. Processors include OpenAI, GitHub and the chosen mail and hosting providers. Residency, certifications, uptime, infrastructure encryption and hosted continuity are unverified.
