# Dev Environment Launcher (dtl)

## Status: WORKING (v1.0.0 — 2026-03-05)

Single-file project scaffolder for containerized development. All project code runs in containers.

## Usage

```bash
# List available stacks and services
dtl list-stacks

# Create a new project
dtl new \
    --name myproject \
    --stack python \
    --services postgres,redis \
    --dir ~/Desktop
```

### Available Stacks

| Stack | Base Image |
|-------|-----------|
| `python` | Python 3.12 |
| `node` | Node.js 22 LTS |
| `go` | Go 1.23 |
| `rust` | Rust (stable) |

### Optional Services

| Service | Image |
|---------|-------|
| `postgres` | postgres:16-alpine |
| `redis` | redis:7-alpine |

## What Gets Generated

```
myproject/
├── .devcontainer/
│   ├── devcontainer.json    # Security-hardened (--cap-drop=ALL, --security-opt=no-new-privileges)
│   └── Dockerfile           # Stack-specific base image
├── .github/workflows/
│   └── ci.yml               # Lint + test + security scan
├── .pre-commit-config.yaml  # gitleaks + semgrep
├── CLAUDE.md                # AI context (commit conventions, linting, workflow)
├── README.md
├── .gitignore               # Stack-specific + security exclusions
└── docker-compose.yml       # Only if --services specified (no host port mappings)
```

### Security Validation

The launcher runs 8 checks after scaffolding:

1. devcontainer: `--cap-drop=ALL`
2. devcontainer: `--security-opt=no-new-privileges`
3. .gitignore: excludes `.env` files
4. .gitignore: excludes `.pem` files
5. CLAUDE.md exists
6. .pre-commit-config.yaml exists
7. CI workflow exists
8. docker-compose.yml: no host port mappings

## Design Principles

- **Multi-stack** — not hardcoded to any single language
- **Containers are the security boundary** — host is protected by running project code in containers
- **Standard patterns** — follows devcontainers spec so VS Code picks up configs natively
- **Minimal scaffolding** — simplest working config, developer adds complexity as needed
- **Stdlib-only** — no pip dependencies, single file, works offline

## Requirements

To use devcontainers (optional — projects work without them):
- Docker installed and running
- VS Code with Dev Containers extension
- Open project in VS Code, select "Reopen in Container"

Without Docker, the project structure, CLAUDE.md, pre-commit hooks, and CI config all work directly.

## Reference Projects

| Project | Relevance |
|---------|-----------|
| [trailofbits/claude-code-devcontainer](https://github.com/trailofbits/claude-code-devcontainer) | Running Claude Code in isolated containers |
| [trailofbits/claude-code-config](https://github.com/trailofbits/claude-code-config) | CLAUDE.md template structure, security hooks |
| [dagger/container-use](https://github.com/dagger/container-use) | MCP server giving each AI agent its own container |
| [boxlite-ai/boxlite](https://github.com/boxlite-ai/boxlite) | Embeddable micro-VM sandbox (KVM), no daemon |
| [devcontainers/template-starter](https://github.com/devcontainers/template-starter) | Custom devcontainer templates for VS Code |
