# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.9.x   | :white_check_mark: |
| 0.8.x   | :white_check_mark: |
| 0.7.x   | :x:                |
| < 0.7   | :x:                |

## Reporting a Vulnerability

**Do not open a public issue.** Instead, email [2115464137@qq.com](mailto:2115464137@qq.com) with:

- A clear description of the vulnerability
- Steps to reproduce
- Affected versions
- Any potential impact

You will receive a response within **48 hours**. After the vulnerability is confirmed and patched, we will publish a security advisory and credit you (unless you prefer to remain anonymous).

## Response Timeline

| Phase | Timeline |
|-------|----------|
| Acknowledge receipt | Within 48 hours |
| Confirm and assess severity | Within 5 business days |
| Patch released | Depends on severity (Critical: 48h, High: 7d, Medium: 30d) |
| Public disclosure | After patch is released |

## Scope

The following are in scope:

- Multi-agent conflict detection bypasses
- Audit log tampering or hash chain breaks
- RBAC privilege escalation
- Prompt injection that bypasses the 13 detection patterns
- Unauthorized access to shared agent memory
- API key leakage through MCP tools
- Dashboard authentication bypass

## Best Practices

When deploying Ahy Governance in production:

1. **Change default credentials** — the demo data is for development only
2. **Use HTTPS** — always run behind a reverse proxy with TLS
3. **Rotate API keys** — set expiration on all API keys and rotate regularly
4. **Enable audit logging** — the SHA-256 hash chain is only as good as your logging coverage
5. **Keep dependencies updated** — run `pip list --outdated` monthly
