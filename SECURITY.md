# Security policy

## Reporting a problem

Do not open a public issue containing a credential, internal address, log excerpt, or screenshot with private data. Contact the repository owner privately and include only the minimum detail needed to reproduce the problem.

## Deployment baseline

- Keep `.env` and other real environment files outside the repository.
- Give API tokens the smallest scope available and prefer dedicated read-only accounts.
- Bind all helper services to `127.0.0.1`.
- Never expose an unrestricted Docker API. Use a read-only socket proxy with only the required endpoints enabled.
- Use TLS, authentication, an exact host allow-list, and rate limiting when Homepage is reachable outside a trusted network.
- Leave `ALLOW_INSECURE_TLS=false`. If a private PKI is used, install its CA certificate instead of disabling verification.

## Before publishing changes

Run a secrets scanner plus a separate pattern review. Inspect the complete git diff and the exact files that would enter the commit. Pay special attention to YAML, environment examples, screenshots, archives, logs, copied terminal output, and generated JSON.

If a real secret ever enters git history, treat it as compromised: revoke or rotate it first, then clean the history before publication.
