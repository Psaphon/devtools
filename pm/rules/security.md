---
paths:
  - "**"
---
# Security Rules

- Never store secrets in code or commit them to git
- All config via environment variables
- Docker containers: cap_drop ALL, no-new-privileges
- SSH keys live on SECRETS USB partition, copied to ~/.ssh/ at install time
- OAuth tokens persist in Docker named volumes (claude-data)
- Never read .env files or anything in secrets/ directories
- Cloudflare Worker secrets use `wrangler secret put`, never hardcoded
