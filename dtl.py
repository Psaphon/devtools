#!/usr/bin/env python3
"""
Multi-stack project scaffolder for secure containerized development.

Generates project structure, devcontainer config, Docker Compose services,
CLAUDE.md, pre-commit hooks, and GitHub Actions CI -- all from a single
stdlib-only script.

Usage:
    dtl new --name myproject --stack python
    dtl new --name myproject --stack node --services postgres,redis
    dtl new --name myproject --stack python --ai claude
    dtl new --name myproject --stack go --dir /tmp
    dtl list-stacks
    dtl add-mcp --name filesystem --project ~/myproject

    dtl ai attach --project ~/myproject --provider claude --mode docker
    dtl ai attach --project ~/myproject --provider openclaw --mode docker
    dtl ai attach --project ~/myproject --provider claude --mode vm
    dtl ai detach --project ~/myproject
    dtl ai start --project ~/myproject
    dtl ai stop --project ~/myproject
    dtl ai status --project ~/myproject
    dtl ai run --project ~/myproject --prompt "implement the CLI"
    dtl ai config-notify --project ~/myproject --telegram-token TOKEN --telegram-chat-id ID
    dtl ai list-providers

    dtl workflow list --plan docs/DEVPLAN.md
    dtl workflow next --plan docs/DEVPLAN.md
    dtl workflow next --plan docs/DEVPLAN.md --project ~/myproject
    dtl workflow finish --plan docs/DEVPLAN.md --watch
    dtl workflow run --projects ~/proj1,~/proj2
    dtl workflow run --projects ~/proj1 --schedule 02:00
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import re
import select
import subprocess
import sys
import textwrap
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Stack definitions
# ---------------------------------------------------------------------------

STACKS: Dict[str, dict] = {
    "python": {
        "display": "Python 3.12",
        "image": "python:3.12-slim",
        "features": {
            "ghcr.io/devcontainers/features/common-utils:2": {
                "installZsh": False,
                "username": "vscode",
                "userUid": "automatic",
                "userGid": "automatic",
            },
        },
        "extensions": [
            "ms-python.python",
            "ms-python.vscode-pylance",
            "charliermarsh.ruff",
        ],
        "linter_cmd": "ruff check .",
        "formatter_cmd": "ruff format --check .",
        "test_cmd": "pytest",
        "src_dir": "src",
        "gitignore_extra": textwrap.dedent("""\
            # Python
            __pycache__/
            *.py[cod]
            *.egg-info/
            dist/
            build/
            .venv/
            venv/
            .pytest_cache/
            .coverage
            htmlcov/
            .mypy_cache/
            .ruff_cache/
        """),
        "dockerfile_run": ("RUN pip install --no-cache-dir --upgrade pip"),
        "ci_setup": textwrap.dedent("""\
              - uses: actions/setup-python@v5
                with:
                  python-version: "3.12"
              - run: pip install ruff pytest
              - run: ruff check .
              - run: ruff format --check .
              - run: pytest --tb=short || true
        """),
        "claude_linter": "ruff check . && ruff format --check .",
        "security_audit_step": textwrap.dedent("""\
            - name: Dependency audit (pip-audit)
              run: |
                pip install pip-audit
                if [ -f requirements.txt ]; then pip-audit -r requirements.txt; fi
                if [ -f pyproject.toml ]; then pip-audit; fi
        """),
    },
    "node": {
        "display": "Node.js 22 LTS",
        "image": "node:22-slim",
        "features": {
            "ghcr.io/devcontainers/features/common-utils:2": {
                "installZsh": False,
                "username": "vscode",
                "userUid": "automatic",
                "userGid": "automatic",
            },
        },
        "extensions": [
            "dbaeumer.vscode-eslint",
            "esbenp.prettier-vscode",
        ],
        "linter_cmd": "npx eslint .",
        "formatter_cmd": "npx prettier --check .",
        "test_cmd": "npm test",
        "src_dir": "src",
        "gitignore_extra": textwrap.dedent("""\
            # Node
            node_modules/
            dist/
            build/
            .cache/
            coverage/
            *.tsbuildinfo
        """),
        "dockerfile_run": "# npm install happens via devcontainer postCreateCommand",
        "ci_setup": textwrap.dedent("""\
              - uses: actions/setup-node@v4
                with:
                  node-version: "22"
              - run: npm ci
              - run: npx eslint . || true
              - run: npm test || true
        """),
        "claude_linter": "npx eslint . && npx prettier --check .",
        "security_audit_step": textwrap.dedent("""\
            - uses: actions/setup-node@v4
              with:
                node-version: "22"
            - name: Dependency audit (npm)
              run: |
                if [ -f package.json ]; then
                  npm install --package-lock-only --ignore-scripts
                  npm audit --audit-level=high
                fi
        """),
    },
    "go": {
        "display": "Go 1.23",
        "image": "golang:1.23-bookworm",
        "features": {
            "ghcr.io/devcontainers/features/common-utils:2": {
                "installZsh": False,
                "username": "vscode",
                "userUid": "automatic",
                "userGid": "automatic",
            },
        },
        "extensions": [
            "golang.go",
        ],
        "linter_cmd": "go vet ./...",
        "formatter_cmd": "gofmt -l .",
        "test_cmd": "go test ./...",
        "src_dir": "cmd",
        "gitignore_extra": textwrap.dedent("""\
            # Go
            /bin/
            *.exe
            vendor/
        """),
        "dockerfile_run": "# go mod download happens at build or postCreate",
        "ci_setup": textwrap.dedent("""\
              - uses: actions/setup-go@v5
                with:
                  go-version: "1.23"
              - run: go vet ./...
              - run: go test ./...
        """),
        "claude_linter": 'go vet ./... && test -z "$(gofmt -l .)"',
    },
    "rust": {
        "display": "Rust (stable)",
        "image": "rust:slim-bookworm",
        "features": {
            "ghcr.io/devcontainers/features/common-utils:2": {
                "installZsh": False,
                "username": "vscode",
                "userUid": "automatic",
                "userGid": "automatic",
            },
        },
        "extensions": [
            "rust-lang.rust-analyzer",
        ],
        "linter_cmd": "cargo clippy -- -D warnings",
        "formatter_cmd": "cargo fmt --check",
        "test_cmd": "cargo test",
        "src_dir": "src",
        "gitignore_extra": textwrap.dedent("""\
            # Rust
            /target/
            Cargo.lock
        """),
        "dockerfile_run": ("RUN rustup component add clippy rustfmt"),
        "ci_setup": textwrap.dedent("""\
              - uses: dtolnay/rust-toolchain@stable
                with:
                  components: clippy, rustfmt
              - run: cargo clippy -- -D warnings
              - run: cargo fmt --check
              - run: cargo test
        """),
        "claude_linter": "cargo clippy -- -D warnings && cargo fmt --check",
    },
}

SERVICES: Dict[str, dict] = {
    "postgres": {
        "image": "postgres:16-alpine",
        "environment": {
            "POSTGRES_USER": "dev",
            "POSTGRES_PASSWORD": "dev",
            "POSTGRES_DB": "devdb",
        },
        "volumes": ["postgres_data:/var/lib/postgresql/data"],
        "healthcheck_cmd": "pg_isready -U dev",
    },
    "redis": {
        "image": "redis:7-alpine",
        "environment": {},
        "volumes": ["redis_data:/data"],
        "healthcheck_cmd": "redis-cli ping",
    },
}

# ---------------------------------------------------------------------------
# AI provider, mode, and model definitions
# ---------------------------------------------------------------------------

AI_PROVIDERS_CONFIG: Dict[str, dict] = {
    "claude": {
        "display": "Claude Code",
        "description": "Anthropic Claude Code CLI in a container",
        "image": "node:22-slim",
        "env_key": None,
        "quota_source": "anthropic-shared",
        "models": {
            "opus": "claude-opus-4-7",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
        },
        "default_model": "sonnet",
        "supports_autonomous": True,
        "supports_interactive": True,
    },
    "ollama": {
        "display": "Ollama (local models)",
        "description": "Run open-source LLMs locally via Ollama (no-quota local fallback)",
        "image": "ollama/ollama:latest",
        "env_key": None,
        "quota_source": "local",
        "models": {},
        "default_model": "llama3",
        "supports_autonomous": True,
        "supports_interactive": True,
    },
    "openclaw": {
        "display": "OpenClaw",
        "description": "Autonomous AI agent with native chat-app integration",
        "image": "ghcr.io/openclaw/openclaw:latest",
        "env_key": "ANTHROPIC_API_KEY",
        "quota_source": "anthropic-shared",
        "models": {},
        "default_model": None,
        "supports_autonomous": True,
        "supports_interactive": True,
    },
}

# Backward compat — flat list used by dtl new --ai validation
AI_PROVIDERS = list(AI_PROVIDERS_CONFIG.keys())

AI_MODES = ["docker", "vm"]

SSH_KEY_PATH = Path.home() / ".ssh" / "ai-sandbox-key"

# Number of consecutive same-reason skips before stall notification is sent.
WORKFLOW_STALL_THRESHOLD = 3

# Watchdog anomaly thresholds (v1 constants — not user-configurable).
WATCHDOG_DIRTY_HOURS: int = 24  # dirty tree older than this triggers anomaly
WATCHDOG_PR_IDLE_HOURS: int = 48  # no PR activity for this long triggers anomaly
WATCHDOG_LOG_GROWTH_MB_DAY: float = 100.0  # log growth rate above this triggers anomaly

# ---------------------------------------------------------------------------
# CLAUDE.md template categories
# ---------------------------------------------------------------------------

CLAUDE_MD_TEMPLATES: Dict[str, str] = {
    "general": "",  # uses make_claude_md default
    "terraform": textwrap.dedent("""\

        ## Terraform Conventions

        - Run `terraform fmt` before every commit.
        - Run `terraform validate` after any change.
        - Never run `terraform apply` without `terraform plan` first.
        - Use variables for all configurable values — no hardcoded IPs, regions, or AMI IDs.
        - State is stored remotely in S3 — never commit .tfstate files.
        - Use `terraform-docs` style comments for all variables and outputs.
        - Tag all resources with at minimum: Name, Project, Environment.
        - Follow least-privilege for all IAM policies.
        - Security group rules must have comments explaining the rule.

        ## File Naming

        - `main.tf` — provider and backend config
        - `network.tf` — VPC, subnets, security groups
        - `compute.tf` — EC2, ECS, Lambda
        - `database.tf` — RDS, DynamoDB
        - `iam.tf` — roles and policies
        - `variables.tf` — input variables
        - `outputs.tf` — output values
    """),
    "monitoring": textwrap.dedent("""\

        ## Monitoring Tool Conventions

        - All HTTP requests must use async (httpx or aiohttp).
        - Handle network errors gracefully — a failed check is data, not a crash.
        - Use structured logging, not print statements.
        - Store time-series data with ISO 8601 timestamps.
        - Dashboard output must work in standard 80-column terminals.
        - Configuration is YAML-based — validate config on load, fail fast.
        - Intervals are in seconds. Minimum interval is 10s to avoid rate limiting.
        - All API integrations must respect rate limits.
    """),
    "security": textwrap.dedent("""\

        ## Security Tool Conventions

        - All regex patterns must be compiled and tested against sample data.
        - Never execute or eval log content — treat all log data as untrusted.
        - Parser output must be structured (dict/dataclass), not raw strings.
        - Detection thresholds must be configurable, not hardcoded.
        - Reports must include timestamps, severity levels, and actionable recommendations.
        - Support multiple output formats: terminal (Rich), JSON, Markdown.
        - Sample logs for testing must not contain real IPs or credentials.
        - All file reads must handle encoding errors gracefully (replace, not crash).
    """),
    "etl": textwrap.dedent("""\

        ## ETL Pipeline Conventions

        - Extract → Transform → Load — keep stages cleanly separated.
        - All API calls must handle rate limiting, pagination, and retries.
        - Transform functions must be pure (no side effects, no API calls).
        - Schema validation at load boundaries — fail fast on bad data.
        - Store raw API responses before transformation (audit trail).
        - Use transactions for database writes — partial loads corrupt data.
        - CSV exports must handle Unicode, commas in fields, and newlines.
        - Include row counts and checksums in pipeline logs.
    """),
    "api": textwrap.dedent("""\

        ## API Conventions

        - All endpoints return JSON with consistent envelope: {"data": ..., "error": ...}.
        - Use HTTP status codes correctly — 200 OK, 201 Created, 400 Bad Request, 404, 500.
        - Validate all request input at the boundary — never trust client data.
        - Use environment variables for all configuration (12-factor app).
        - Database queries must use parameterized statements — never string interpolation.
        - Include request ID in all log entries for traceability.
        - Health check endpoint at /health must verify database connectivity.
        - Rate limit all public endpoints.
    """),
}

# ---------------------------------------------------------------------------
# Project template generators
# ---------------------------------------------------------------------------


def make_shellcheckrc() -> str:
    """Generate .shellcheckrc so shellcheck behaves identically locally and in CI."""
    return "external-sources=true\nsource-path=SCRIPTDIR\n"


def make_gitignore(stack: dict) -> str:
    """Generate .gitignore content for the given stack."""
    common = textwrap.dedent("""\
        # Environment & Secrets
        .env
        .env.*
        !.env.example
        *.pem
        *.key
        *.crt

        # IDE
        .vscode/
        .idea/
        *.swp
        *.swo
        *~

        # OS
        .DS_Store
        Thumbs.db

        # Docker
        docker-compose.override.yml

        # AI sandbox
        .ai/config.json

        # AI failure reports (written by dtl ai run on timeout/retry-cap)
        FAILURE-REPORT.md
    """)
    return common + "\n" + stack["gitignore_extra"]


def make_readme(name: str, stack_name: str) -> str:
    """Generate a minimal project README."""
    return textwrap.dedent(f"""\
        # {name}

        A {stack_name} project scaffolded by dtl.

        ## Getting Started

        Open in VS Code and select **Reopen in Container** when prompted,
        or start manually:

        ```bash
        cd .devcontainer
        docker compose up -d
        ```

        ## Development

        All development happens inside the devcontainer. See `CLAUDE.md`
        for commit conventions and workflow rules.

        ## Branch Protection

        In GitHub repository settings, require the `ci-ok` status check
        (rather than individual matrix job names) so that all CI jobs must
        pass before a pull request can merge.

        ## Security Scanning

        CI runs two security checks on every push:

        - **Secret scanning** (gitleaks): detects committed credentials and API keys.
        - **Dependency audit** (pip-audit / npm audit): flags packages with known CVEs.

        ### Triaging findings

        **Gitleaks** — if a secret is flagged:
        1. Rotate the credential immediately (treat it as compromised).
        2. Remove it from git history (`git filter-repo` or BFG Repo Cleaner).
        3. If the match is a false positive, add a `.gitleaksignore` entry.

        **Dependency audit** — if a vulnerable package is flagged:
        1. Check the advisory for severity and whether your usage is affected.
        2. Update to a patched version (`pip install -U <pkg>` / `npm update <pkg>`).
        3. If no fix exists, assess workarounds or document the accepted risk.
    """)


def make_dockerfile(stack: dict) -> str:
    """Generate Dockerfile for the devcontainer."""
    return textwrap.dedent(f"""\
        FROM {stack["image"]}

        {stack["dockerfile_run"]}

        # Create non-root user
        ARG USERNAME=vscode
        ARG USER_UID=1000
        ARG USER_GID=$USER_UID
        RUN groupadd --gid $USER_GID $USERNAME \\
            && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \\
            || true

        USER $USERNAME
    """)


def make_devcontainer_json(
    name: str,
    stack: dict,
    services: List[str],
) -> str:
    """Generate devcontainer.json (returned as formatted JSON string)."""
    config: dict = {
        "name": name,
        "build": {
            "dockerfile": "Dockerfile",
            "context": "..",
        },
        "features": stack["features"],
        "customizations": {
            "vscode": {
                "extensions": stack["extensions"],
            }
        },
        "runArgs": [
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
        ],
        "remoteUser": "vscode",
    }

    if services:
        config["dockerComposeFile"] = "../docker-compose.yml"

    return json.dumps(config, indent=2) + "\n"


def make_docker_compose(
    services_requested: List[str],
) -> str:
    """Generate docker-compose.yml for optional services."""
    lines = [
        "services:",
    ]

    volumes_needed: List[str] = []

    for svc_name in services_requested:
        svc = SERVICES[svc_name]
        lines.append(f"  {svc_name}:")
        lines.append(f"    image: {svc['image']}")

        if svc["environment"]:
            lines.append("    environment:")
            for k, v in svc["environment"].items():
                lines.append(f"      {k}: {v}")

        if svc["volumes"]:
            lines.append("    volumes:")
            for vol in svc["volumes"]:
                lines.append(f"      - {vol}")
                vol_name = vol.split(":")[0]
                if vol_name not in volumes_needed:
                    volumes_needed.append(vol_name)

        lines.append("    healthcheck:")
        lines.append(f'      test: ["{svc["healthcheck_cmd"]}"]')
        lines.append("      interval: 10s")
        lines.append("      timeout: 5s")
        lines.append("      retries: 5")

        lines.append("    restart: unless-stopped")
        lines.append("    deploy:")
        lines.append("      resources:")
        lines.append("        limits:")
        lines.append("          cpus: '1'")
        lines.append("          memory: 512M")
        lines.append("")

    if volumes_needed:
        lines.append("volumes:")
        for vol in volumes_needed:
            lines.append(f"  {vol}:")

    return "\n".join(lines) + "\n"


def make_claude_md(
    name: str,
    stack_name: str,
    stack: dict,
    template: str = "general",
) -> str:
    """Generate CLAUDE.md context file for Claude Code."""
    base = textwrap.dedent(f"""\
        # CLAUDE.md -- AI Context for {name}

        ## Project

        - **Stack:** {stack_name}
        - **Container:** all development happens inside a devcontainer

        ## Commit Conventions

        Follow conventional commits strictly:

        - `feat:` -- new feature
        - `fix:` -- bug fix
        - `docs:` -- documentation only
        - `chore:` -- maintenance, dependency updates
        - `refactor:` -- code restructuring without behavior change
        - `test:` -- adding or updating tests
        - `ci:` -- CI/CD changes

        ## Branching (Gitflow)

        This project follows **gitflow**. NEVER commit directly to `main` or `develop`.

        ### Branch types

        | Branch | Purpose | Branches from | Merges into |
        |--------|---------|---------------|-------------|
        | `main` | Production-ready releases (tagged) | -- | -- |
        | `develop` | Integration branch for next release | `main` (initial) | `release/*` |
        | `feature/*` | New features and non-urgent work | `develop` | `develop` |
        | `release/*` | Release prep (bug fixes, docs only) | `develop` | `main` + `develop` |
        | `hotfix/*` | Emergency production fixes | `main` | `main` + `develop` |

        ### Workflow

        1. **Feature work:** `git checkout develop && git checkout -b feature/short-description`
        2. Work, commit with conventional commits, push.
        3. Open a PR from `feature/short-description` → `develop`.
        4. **Release prep:** `git checkout develop && git checkout -b release/vX.Y.Z`
        5. Only bug fixes and docs in release branches — no new features.
        6. When ready: merge `release/vX.Y.Z` → `main`, tag `vX.Y.Z`, merge back → `develop`.
        7. **Hotfix:** `git checkout main && git checkout -b hotfix/description`
        8. Fix, merge → `main` (tag), merge → `develop`.

        ### Branch naming

        - `feature/add-cli`, `feature/eth-tracker`
        - `release/v1.0.0`, `release/v1.1.0`
        - `hotfix/fix-crash`, `hotfix/patch-auth`

        ## Linting & Formatting

        **CRITICAL: You MUST run linting and formatting before EVERY commit.** No exceptions.

        ```bash
        {stack["claude_linter"]}
        ```

        If linting fails, fix ALL issues before committing. Never use `--no-verify` to skip checks.
        A commit that fails lint is a broken commit — treat it as a build failure.

        ## Docker

        - Use `docker compose` (space), NOT `docker-compose` (hyphen).
        - Containers run with `--cap-drop=ALL` and `--security-opt=no-new-privileges`.

        ## Secrets

        - NEVER commit secrets, credentials, API keys, or tokens.
        - Use `.env.example` with placeholder values; real `.env` is gitignored.
        - Check `.gitignore` covers `.env*`, `*.pem`, `*.key`.

        ## Security

        - Pre-commit hooks run gitleaks (secret scanning) and semgrep (static analysis).
        - Install hooks: `pre-commit install`
        - Run manually: `pre-commit run --all-files`

        ## Testing

        ```bash
        {stack["test_cmd"]}
        ```

        Run tests before pushing.
    """)

    extra = CLAUDE_MD_TEMPLATES.get(template, "")
    return base + extra


def make_precommit_config() -> str:
    """Generate .pre-commit-config.yaml with gitleaks and semgrep."""
    return textwrap.dedent("""\
        repos:
          - repo: https://github.com/gitleaks/gitleaks
            rev: v8.21.2
            hooks:
              - id: gitleaks

          - repo: https://github.com/semgrep/semgrep
            rev: v1.98.0
            hooks:
              - id: semgrep
                args: ["--config", "auto", "--error"]
    """)


def make_ci_workflow(name: str, stack: dict) -> str:
    """Generate .github/workflows/ci.yml."""
    ci_setup = textwrap.indent(stack["ci_setup"].rstrip(), "      ")
    security_audit_step = stack.get("security_audit_step", "").rstrip()
    audit_block = (
        textwrap.indent(security_audit_step, "      ") if security_audit_step else ""
    )
    return f"""\
name: CI

on:
  push:
    branches: [main, develop, "feature/**", "release/**", "hotfix/**"]
  pull_request:
    branches: [main, develop]

permissions:
  contents: read

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
{ci_setup}

  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Shellcheck
        run: |
          mapfile -t scripts < <(find . -name "*.sh" ! -path "./.git/*" ! -path "./.ai/*")
          [ ${{#scripts[@]}} -eq 0 ] && exit 0
          shellcheck "${{scripts[@]}}"

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_LICENSE: ${{{{ secrets.GITLEAKS_LICENSE }}}}
{audit_block}
  ci-ok:
    runs-on: ubuntu-latest
    needs: [lint-and-test, shellcheck, security-scan]
    if: always()
    steps:
      - name: Check job results
        run: |
          if [[ "${{{{ contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled') }}}}" == "true" ]]; then
            echo "One or more required jobs did not succeed."
            exit 1
          fi
          echo "All required jobs succeeded."
"""


_CI_YML_SCAFFOLD = textwrap.dedent("""\
    name: CI

    on:
      push:
        branches: [main, develop]
      pull_request:
        branches: [main, develop]

    permissions:
      contents: read

    jobs:
      lint-and-test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4

          - name: Detect Python source
            id: pycheck
            run: |
              if find . -name "*.py" ! -path "./.git/*" ! -path "./.ai/*" | grep -q .; then
                echo "found=true" >> "$GITHUB_OUTPUT"
              else
                echo "found=false" >> "$GITHUB_OUTPUT"
              fi

          - uses: actions/setup-python@v5
            if: steps.pycheck.outputs.found == 'true'
            with:
              python-version: "3.12"

          - name: Lint (ruff)
            if: steps.pycheck.outputs.found == 'true'
            run: pip install ruff && ruff check .

          - name: Format check (ruff)
            if: steps.pycheck.outputs.found == 'true'
            run: ruff format --check .

          - name: Test (pytest)
            if: steps.pycheck.outputs.found == 'true'
            run: |
              pip install pytest
              pytest --tb=short -q; RET=$?; [ $RET -eq 5 ] && exit 0 || exit $RET

          - name: Shellcheck
            run: |
              mapfile -t scripts < <(find . -name "*.sh" ! -path "./.git/*" ! -path "./.ai/*")
              [ ${#scripts[@]} -eq 0 ] && exit 0
              shellcheck "${scripts[@]}"

  ci-ok:
    runs-on: ubuntu-latest
    needs: [lint-and-test]
    if: always()
    steps:
      - name: Check job results
        run: |
          if [[ "${{ contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled') }}" == "true" ]]; then
            echo "One or more required jobs did not succeed."
            exit 1
          fi
          echo "All required jobs succeeded."
""")


def make_cd_workflow(name: str) -> str:
    """Generate .github/workflows/release.yml for automated GitHub Releases."""
    _ = name  # available for future template use
    return textwrap.dedent("""\
        name: Release

        on:
          push:
            tags:
              - "v*"

        permissions:
          contents: write

        jobs:
          release:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
                with:
                  fetch-depth: 0

              - name: Create GitHub Release
                env:
                  GH_TOKEN: ${{ github.token }}
                run: |
                  gh release create "${{ github.ref_name }}" \\
                    --title "${{ github.ref_name }}" \\
                    --generate-notes
    """)


def make_env_example(services: List[str]) -> str:
    """Generate .env.example with placeholder values."""
    lines = ["# Copy to .env and fill in real values", ""]
    if "postgres" in services:
        lines.append("POSTGRES_USER=dev")
        lines.append("POSTGRES_PASSWORD=changeme")
        lines.append("POSTGRES_DB=devdb")
        lines.append("DATABASE_URL=postgresql://dev:changeme@postgres:5432/devdb")
        lines.append("")
    if "redis" in services:
        lines.append("REDIS_URL=redis://redis:6379")
        lines.append("")
    if not services:
        lines.append("# No services configured")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AI sandbox template generators — VM mode (QEMU/KVM)
# ---------------------------------------------------------------------------


def make_ai_cloud_init() -> str:
    """Generate cloud-init user-data for the AI sandbox VM."""
    pub_key = ""
    pub_key_path = SSH_KEY_PATH.with_suffix(".pub")
    if pub_key_path.exists():
        pub_key = pub_key_path.read_text().strip()

    return textwrap.dedent(f"""\
        #cloud-config
        hostname: ai-sandbox
        users:
          - name: dev
            shell: /bin/bash
            sudo: ALL=(ALL) NOPASSWD:ALL
            ssh_authorized_keys:
              - {pub_key if pub_key else "# NO KEY FOUND -- run: ssh-keygen -t ed25519 -f ~/.ssh/ai-sandbox-key -N ''"}

        package_update: true
        packages:
          - docker.io
          - docker-compose-v2
          - git
          - ripgrep
          - fd-find
          - tmux
          - curl
          - ca-certificates
          - iptables-persistent

        runcmd:
          - systemctl enable --now docker
          - usermod -aG docker dev
          # Install Node.js 22 for Claude Code
          - curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
          - apt-get install -y nodejs
          # Install Claude Code
          - npm install -g @anthropic-ai/claude-code
          # Create workspace mount point
          - mkdir -p /workspace
          - chown dev:dev /workspace
          # Network isolation (defense-in-depth): restrict outbound to QEMU SLIRP
          # internal network only. SLIRP restrict=on on host is the primary control;
          # iptables here prevents lateral movement if SLIRP is misconfigured.
          - iptables -P OUTPUT DROP
          - iptables -A OUTPUT -o lo -j ACCEPT
          - iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
          - iptables -A OUTPUT -d 10.0.2.0/24 -j ACCEPT
          - iptables-save > /etc/iptables/rules.v4

        write_files:
          - path: /etc/docker/daemon.json
            content: |
              {{
                "log-driver": "json-file",
                "log-opts": {{
                  "max-size": "10m",
                  "max-file": "3"
                }}
              }}

          - path: /etc/sysctl.d/99-ai-sandbox.conf
            content: |
              # Prevent VM from acting as a router
              net.ipv4.ip_forward=0

          - path: /etc/hosts.d/ai-sandbox
            content: |
              # Route Anthropic API through host-side proxy (guestfwd 10.0.2.101:443)
              10.0.2.101  api.anthropic.com
    """)


def make_ai_vm_config(name: str, ai_providers: List[str]) -> str:
    """Generate QEMU launch script for the AI sandbox VM."""
    # Build restricted SLIRP network: SSH + Anthropic API proxy + optional Ollama
    # restrict=on blocks all outbound traffic; guestfwd creates explicit allowlist
    if "ollama" in ai_providers:
        netdev_line = (
            "  -netdev user,id=net0,restrict=on,"
            "hostfwd=tcp::2222-:22,"
            "guestfwd=tcp:10.0.2.100:11434-tcp:127.0.0.1:11434,"
            "guestfwd=tcp:10.0.2.101:443-tcp:127.0.0.1:4430 \\"
        )
    else:
        netdev_line = (
            "  -netdev user,id=net0,restrict=on,"
            "hostfwd=tcp::2222-:22,"
            "guestfwd=tcp:10.0.2.101:443-tcp:127.0.0.1:4430 \\"
        )

    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # AI Sandbox VM launcher for project: {name}
        # Configurable via environment variables.
        #
        # Network isolation: SLIRP restrict=on blocks all outbound traffic.
        # Allowlist:
        #   10.0.2.101:443  -> host proxy -> api.anthropic.com:443
        #   10.0.2.100:11434 -> host:11434 (Ollama, if enabled)
        set -euo pipefail

        SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
        VM_DIR="$SCRIPT_DIR"

        # --- Configurable ---
        AI_VM_CPUS="${{AI_VM_CPUS:-4}}"
        AI_VM_RAM="${{AI_VM_RAM:-8G}}"
        AI_VM_DISK="${{AI_VM_DISK:-20G}}"
        CLOUD_IMAGE="${{AI_VM_CLOUD_IMAGE:-/var/lib/ai-sandbox/ubuntu-24.04-minimal-cloudimg-amd64.img}}"

        VM_DISK="$VM_DIR/{name}-vm.qcow2"
        CLOUD_INIT="$VM_DIR/cloud-init.yaml"
        PIDFILE="$VM_DIR/vm.pid"
        PROXY_PIDFILE="$VM_DIR/anthropic-proxy.pid"

        start_anthropic_proxy() {{
            # Start a host-side TCP proxy that forwards to api.anthropic.com:443.
            # The VM connects via guestfwd (10.0.2.101:443 -> 127.0.0.1:4430).
            # TLS passes through unmodified so certificate verification succeeds.
            if [ -f "$PROXY_PIDFILE" ] && kill -0 "$(cat "$PROXY_PIDFILE")" 2>/dev/null; then
                return 0
            fi
            python3 -c "
import socket, threading, sys

def proxy(client, host, port):
    try:
        server = socket.create_connection((host, port), timeout=10)
    except Exception:
        client.close()
        return
    def pipe(src, dst):
        try:
            while True:
                d = src.recv(4096)
                if not d:
                    break
                dst.sendall(d)
        except Exception:
            pass
        finally:
            src.close()
            dst.close()
    t = threading.Thread(target=pipe, args=(server, client), daemon=True)
    t.start()
    pipe(client, server)

s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', 4430))
s.listen(10)
sys.stdout.flush()
while True:
    c, _ = s.accept()
    threading.Thread(target=proxy, args=(c, 'api.anthropic.com', 443), daemon=True).start()
" &
            echo $! > "$PROXY_PIDFILE"
            echo "[ai-sandbox] Anthropic API proxy started on 127.0.0.1:4430 (PID $(cat "$PROXY_PIDFILE"))"
        }}

        stop_anthropic_proxy() {{
            if [ -f "$PROXY_PIDFILE" ] && kill -0 "$(cat "$PROXY_PIDFILE")" 2>/dev/null; then
                kill "$(cat "$PROXY_PIDFILE")"
                rm -f "$PROXY_PIDFILE"
            fi
        }}

        create_disk() {{
            if [ ! -f "$VM_DISK" ]; then
                echo "[ai-sandbox] Creating VM disk ($AI_VM_DISK)..."
                qemu-img create -f qcow2 -b "$CLOUD_IMAGE" -F qcow2 "$VM_DISK" "$AI_VM_DISK"

                # Generate cloud-init ISO
                echo "[ai-sandbox] Generating cloud-init seed..."
                cloud-localds "$VM_DIR/seed.iso" "$CLOUD_INIT"
            fi
        }}

        start_vm() {{
            if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
                echo "[ai-sandbox] VM already running (PID $(cat "$PIDFILE"))"
                return 0
            fi

            start_anthropic_proxy
            create_disk

            echo "[ai-sandbox] Starting VM (cpus=$AI_VM_CPUS, ram=$AI_VM_RAM)..."
            qemu-system-x86_64 \\
              -enable-kvm \\
              -cpu host \\
              -smp "$AI_VM_CPUS" \\
              -m "$AI_VM_RAM" \\
              -drive file="$VM_DISK",format=qcow2 \\
              -drive file="$VM_DIR/seed.iso",format=raw \\
        {netdev_line}
              -device virtio-net-pci,netdev=net0 \\
              -virtfs local,path="$(cd "$SCRIPT_DIR/../.." && pwd)",mount_tag=workspace,security_model=mapped-xattr \\
              -nographic \\
              -daemonize \\
              -pidfile "$PIDFILE"

            echo "[ai-sandbox] VM started. SSH: ssh -p 2222 dev@localhost"
        }}

        stop_vm() {{
            if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
                echo "[ai-sandbox] Stopping VM..."
                kill "$(cat "$PIDFILE")"
                rm -f "$PIDFILE"
                echo "[ai-sandbox] VM stopped."
            else
                echo "[ai-sandbox] VM not running."
            fi
            stop_anthropic_proxy
        }}

        status_vm() {{
            if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
                echo "[ai-sandbox] VM running (PID $(cat "$PIDFILE"))"
                echo "[ai-sandbox] SSH: ssh -p 2222 dev@localhost"
            else
                echo "[ai-sandbox] VM not running."
            fi
        }}

        destroy_vm() {{
            stop_vm
            echo "[ai-sandbox] Destroying VM disk and state..."
            rm -f "$VM_DISK" "$VM_DIR/seed.iso" "$PIDFILE"
            echo "[ai-sandbox] Destroyed."
        }}

        case "${{1:-status}}" in
            start)   start_vm ;;
            stop)    stop_vm ;;
            status)  status_vm ;;
            destroy) destroy_vm ;;
            *)
                echo "Usage: $0 {{start|stop|status|destroy}}"
                exit 1
                ;;
        esac
    """)


def make_ai_makefile(name: str) -> str:
    """Generate Makefile for AI sandbox management."""
    return textwrap.dedent(f"""\
        # AI Sandbox for {name}
        # Usage: make up / make down / make ssh / make status / make destroy

        SSH_KEY := ~/.ssh/ai-sandbox-key
        SSH_OPTS := -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q

        .PHONY: up down ssh status destroy

        up:
        \t@bash vm/vm-config.sh start

        down:
        \t@bash vm/vm-config.sh stop

        ssh:
        \t@ssh $(SSH_OPTS) -i $(SSH_KEY) -p 2222 dev@localhost

        status:
        \t@bash vm/vm-config.sh status

        destroy:
        \t@bash vm/vm-config.sh destroy
    """)


def make_ai_vm_compose(
    ai_providers: List[str],
    mcp_servers: List[str] | None = None,
) -> str:
    """Generate docker-compose.yml for containers inside the AI sandbox VM."""
    lines = ["services:"]

    if "claude" in ai_providers:
        lines.extend(
            [
                "  claude-code:",
                "    build: ./claude-code",
                "    volumes:",
                "      - /workspace:/workspace",
                "    working_dir: /workspace",
                "    stdin_open: true",
                "    tty: true",
                "    cap_drop:",
                "      - ALL",
                "    security_opt:",
                "      - no-new-privileges:true",
                "    deploy:",
                "      resources:",
                "        limits:",
                "          cpus: '2'",
                "          memory: 4G",
                "",
            ]
        )

    if mcp_servers:
        for srv in mcp_servers:
            lines.extend(_mcp_compose_entry(srv))
    else:
        lines.extend(
            [
                "  # To add an MCP server run:",
                "  #   dtl add-mcp --name <server> --project .",
                "",
            ]
        )

    return "\n".join(lines) + "\n"


def _mcp_compose_entry(server_name: str) -> List[str]:
    """Return docker-compose lines for a single isolated MCP server."""
    return [
        f"  mcp-{server_name}:",
        f"    build: ./mcp-servers/{server_name}",
        "    network_mode: none",
        "    read_only: true",
        "    tmpfs:",
        "      - /tmp:size=64m",
        "    volumes:",
        "      - /workspace:/workspace:ro",
        "    cap_drop:",
        "      - ALL",
        "    security_opt:",
        "      - no-new-privileges:true",
        "    deploy:",
        "      resources:",
        "        limits:",
        "          cpus: '1'",
        "          memory: 512M",
        "    stdin_open: true",
        "",
    ]


def make_ai_claude_dockerfile() -> str:
    """Generate Dockerfile for the Claude Code container."""
    return textwrap.dedent("""\
        FROM node:22-slim

        # Install system dependencies
        RUN apt-get update && apt-get install -y --no-install-recommends \\
                git \\
                ripgrep \\
                shellcheck \\
                python3 \\
                python3-pip \\
                python3-venv \\
                ca-certificates \\
                curl \\
            && rm -rf /var/lib/apt/lists/*

        # Install Claude Code
        RUN npm install -g @anthropic-ai/claude-code

        # Set up home directory for host-mapped user (UID 1000)
        RUN mkdir -p /home/claude/.claude && chown -R 1000:1000 /home/claude

        # Copy settings into Claude Code's config directory
        COPY settings.json /home/claude/.claude/settings.json
        RUN chown 1000:1000 /home/claude/.claude/settings.json

        ENV HOME=/home/claude
        WORKDIR /workspace

        ENTRYPOINT ["claude"]
    """)


def make_ai_claude_settings(
    ai_providers: List[str],
    mcp_servers: List[str] | None = None,
) -> str:
    """Generate Claude Code settings for the sandbox."""
    mcp_config: dict = {}
    for srv in mcp_servers or []:
        binary_name = MCP_KNOWN_PACKAGES.get(srv, srv).rsplit("/", 1)[-1]
        mcp_config[srv] = {
            "command": "docker",
            "args": ["exec", "-i", f"mcp-{srv}", binary_name],
        }

    settings: dict = {
        "permissions": {
            "allow": [
                "Bash(*)",
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "NotebookEdit",
                "WebFetch",
                "WebSearch",
                "Agent",
                "TaskCreate",
                "TaskGet",
                "TaskList",
                "TaskUpdate",
                "TodoWrite",
            ],
            "deny": [],
        },
        "mcpServers": mcp_config,
    }
    return json.dumps(settings, indent=2) + "\n"


# ---------------------------------------------------------------------------
# AI sandbox template generators — Docker mode
# ---------------------------------------------------------------------------


def make_ai_docker_compose(
    provider: str,
    model: str | None = None,
    mcp_servers: List[str] | None = None,
) -> str:
    """Generate docker-compose.yml for Docker-mode AI setup."""
    lines = ["services:"]

    if provider == "claude":
        model_env = ""
        if model:
            pconfig = AI_PROVIDERS_CONFIG["claude"]
            model_id = pconfig["models"].get(model, model)
            model_env = f"      - CLAUDE_MODEL={model_id}"

        lines.extend(
            [
                "  claude-code:",
                "    build: ./claude-code",
                '    user: "${UID:-1000}:${GID:-1000}"',
                "    volumes:",
                "      - ../:/workspace",
                "      - claude-data:/home/claude",
                "      - ./claude-code/settings.json:/home/claude/.claude/settings.json:ro",
                "    working_dir: /workspace",
                "    stdin_open: true",
                "    tty: true",
                "    cap_drop:",
                "      - ALL",
                "    security_opt:",
                "      - no-new-privileges:true",
                "    deploy:",
                "      resources:",
                "        limits:",
                "          cpus: '2'",
                "          memory: 4G",
                "    environment:",
                "      - GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME:-Developer}",
                "      - GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL:-dev@localhost}",
                "      - GIT_COMMITTER_NAME=${GIT_AUTHOR_NAME:-Developer}",
                "      - GIT_COMMITTER_EMAIL=${GIT_AUTHOR_EMAIL:-dev@localhost}",
            ]
        )
        if model_env:
            lines.append(model_env)
        lines.append("")

    elif provider == "openclaw":
        lines.extend(
            [
                "  openclaw-gateway:",
                f"    image: {AI_PROVIDERS_CONFIG['openclaw']['image']}",
                "    volumes:",
                "      - openclaw-config:/home/node/.openclaw",
                "      - ../../:/home/node/.openclaw/workspace",
                "    ports:",
                '      - "18789:18789"',
                "    environment:",
                "      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}",
                '    user: "1000:1000"',
                "    restart: unless-stopped",
                "    healthcheck:",
                '      test: ["CMD", "curl", "-f", "http://localhost:18789/healthz"]',
                "      interval: 30s",
                "      timeout: 10s",
                "      retries: 3",
                "    deploy:",
                "      resources:",
                "        limits:",
                "          cpus: '2'",
                "          memory: 4G",
                "",
            ]
        )

    elif provider == "ollama":
        lines.extend(
            [
                "  ollama:",
                f"    image: {AI_PROVIDERS_CONFIG['ollama']['image']}",
                "    volumes:",
                "      - ollama-models:/root/.ollama",
                "      - ../:/workspace",
                "    ports:",
                '      - "11434:11434"',
                "    deploy:",
                "      resources:",
                "        limits:",
                "          cpus: '4'",
                "          memory: 8G",
                "    restart: unless-stopped",
                "    healthcheck:",
                '      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]',
                "      interval: 30s",
                "      timeout: 10s",
                "      retries: 3",
                "",
            ]
        )

    if mcp_servers:
        for srv in mcp_servers:
            lines.extend(_mcp_compose_entry(srv))

    # Volumes
    vol_lines: List[str] = []
    compose_text = "\n".join(lines)
    if "claude-data:" in compose_text:
        vol_lines.append("  claude-data:")
    if "openclaw-config:" in compose_text:
        vol_lines.append("  openclaw-config:")
    if "ollama-models:" in compose_text:
        vol_lines.append("  ollama-models:")
    if vol_lines:
        lines.append("volumes:")
        lines.extend(vol_lines)

    return "\n".join(lines) + "\n"


def make_ai_config(
    project_name: str,
    provider: str,
    mode: str,
    model: str | None = None,
    key_source: str = "env",
) -> str:
    """Generate .ai/config.json for persistent AI settings."""
    config: dict = {
        "project_name": project_name,
        "provider": provider,
        "mode": mode,
        "model": model,
        "key_source": key_source,
        "notify": {
            "provider": None,
            "telegram_token": None,
            "telegram_chat_id": None,
        },
    }
    return json.dumps(config, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Notification and autonomous mode templates
# ---------------------------------------------------------------------------


def make_notify_script() -> str:
    """Generate notify.py — stdlib-only Telegram notification sender."""
    return textwrap.dedent("""\
        #!/usr/bin/env python3
        \"\"\"Telegram notification sender for dtl autonomous mode.

        Usage:
            echo "message" | python3 notify.py 0          # success
            echo "message" | python3 notify.py 1          # failure
            python3 notify.py 0 "inline message"          # inline
            python3 notify.py --test                      # send test message

        Reads config from .ai/config.json in the same directory.
        Token and chat ID can also be set via TELEGRAM_BOT_TOKEN and
        TELEGRAM_CHAT_ID environment variables.
        \"\"\"

        import json
        import os
        import sys
        import urllib.request
        import urllib.parse
        from pathlib import Path


        def send_telegram(token: str, chat_id: str, message: str) -> bool:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": message[:4096],
                "parse_mode": "Markdown",
            }).encode()
            req = urllib.request.Request(url, data=data)
            try:
                urllib.request.urlopen(req, timeout=10)
                return True
            except Exception as e:
                print(f"[notify] Telegram send failed: {e}", file=sys.stderr)
                return False


        def load_config() -> dict:
            config_path = Path(__file__).parent / "config.json"
            if config_path.exists():
                with open(config_path) as f:
                    return json.load(f)
            return {}


        def main() -> None:
            config = load_config()
            notify = config.get("notify", {})

            token = os.environ.get("TELEGRAM_BOT_TOKEN", notify.get("telegram_token") or "")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", notify.get("telegram_chat_id") or "")

            if not token or not chat_id:
                print("[notify] Telegram not configured. Set token and chat_id in .ai/config.json", file=sys.stderr)
                print("[notify] or via TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars.", file=sys.stderr)
                sys.exit(1)

            project = config.get("project_name", "unknown")

            # --test flag
            if len(sys.argv) > 1 and sys.argv[1] == "--test":
                ok = send_telegram(token, chat_id, f"*dtl* — test notification for `{project}`")
                sys.exit(0 if ok else 1)

            # Normal mode: status code + message
            status = sys.argv[1] if len(sys.argv) > 1 else "0"
            if len(sys.argv) > 2:
                message = " ".join(sys.argv[2:])
            elif not sys.stdin.isatty():
                message = sys.stdin.read()
            else:
                message = "(no output captured)"

            icon = "complete" if status == "0" else "FAILED"
            # Truncate for Telegram (4096 char limit, leave room for header)
            if len(message) > 3000:
                message = message[:3000] + "\\n... (truncated)"

            text = f"*dtl ai run* — `{project}`\\n\\nStatus: {icon}\\n\\n```\\n{message}\\n```"
            ok = send_telegram(token, chat_id, text)
            sys.exit(0 if ok else 1)


        if __name__ == "__main__":
            main()
    """)


def make_run_script(provider: str) -> str:
    """Generate run.sh — wrapper for autonomous Claude Code or OpenClaw execution."""
    if provider == "claude":
        return textwrap.dedent("""\
            #!/usr/bin/env bash
            # Autonomous Claude Code runner for dtl
            # Usage: ./run.sh "your prompt here"
            set -euo pipefail

            SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            PROMPT="${1:?Usage: ./run.sh \\"your prompt here\\"}"

            echo "[dtl ai run] Starting Claude Code with prompt..."
            echo "[dtl ai run] Prompt: $PROMPT"

            # Run Claude Code in print mode (non-interactive, autonomous)
            RESULT=$(docker compose -f "$SCRIPT_DIR/docker-compose.yml" \\
                run --rm claude-code \\
                claude --print -p "$PROMPT" 2>&1) || true
            EXIT_CODE=${PIPESTATUS[0]:-$?}

            echo "$RESULT"

            # Send notification if configured
            if [ -f "$SCRIPT_DIR/notify.py" ]; then
                echo "$RESULT" | python3 "$SCRIPT_DIR/notify.py" "$EXIT_CODE" || true
            fi

            exit "$EXIT_CODE"
        """)

    elif provider == "openclaw":
        return textwrap.dedent("""\
            #!/usr/bin/env bash
            # OpenClaw gateway launcher for dtl
            # OpenClaw runs autonomously via its gateway — connect via Telegram/etc.
            # Usage: ./run.sh [start|stop|status]
            set -euo pipefail

            SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            ACTION="${1:-start}"

            case "$ACTION" in
                start)
                    echo "[dtl ai run] Starting OpenClaw gateway..."
                    docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d openclaw-gateway
                    echo "[dtl ai run] OpenClaw gateway started on port 18789"
                    echo "[dtl ai run] Connect via Telegram or other configured chat apps"
                    # Send startup notification
                    if [ -f "$SCRIPT_DIR/notify.py" ]; then
                        python3 "$SCRIPT_DIR/notify.py" 0 "OpenClaw gateway started and ready for commands." || true
                    fi
                    ;;
                stop)
                    echo "[dtl ai run] Stopping OpenClaw gateway..."
                    docker compose -f "$SCRIPT_DIR/docker-compose.yml" down
                    ;;
                status)
                    docker compose -f "$SCRIPT_DIR/docker-compose.yml" ps
                    ;;
                *)
                    echo "Usage: $0 {start|stop|status}"
                    exit 1
                    ;;
            esac
        """)

    else:
        # Generic / ollama — no autonomous mode
        return textwrap.dedent("""\
            #!/usr/bin/env bash
            # AI container launcher for dtl
            # Usage: ./run.sh [start|stop|status]
            set -euo pipefail

            SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            ACTION="${1:-start}"

            case "$ACTION" in
                start)
                    echo "[dtl ai] Starting AI containers..."
                    docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d
                    echo "[dtl ai] Containers started."
                    ;;
                stop)
                    echo "[dtl ai] Stopping AI containers..."
                    docker compose -f "$SCRIPT_DIR/docker-compose.yml" down
                    ;;
                status)
                    docker compose -f "$SCRIPT_DIR/docker-compose.yml" ps
                    ;;
                *)
                    echo "Usage: $0 {start|stop|status}"
                    exit 1
                    ;;
            esac
        """)


# ---------------------------------------------------------------------------
# MCP server isolation
# ---------------------------------------------------------------------------

# Well-known MCP server packages (npm).  Keys are short names used with
# ``add-mcp --name <key>``.  Unknown names are treated as raw npm package
# identifiers so users can bring any server they want.
MCP_KNOWN_PACKAGES: Dict[str, str] = {
    "filesystem": "@modelcontextprotocol/server-filesystem",
    "github": "@modelcontextprotocol/server-github",
    "memory": "@modelcontextprotocol/server-memory",
    "brave-search": "@modelcontextprotocol/server-brave-search",
    "fetch": "@modelcontextprotocol/server-fetch",
    "sqlite": "@modelcontextprotocol/server-sqlite",
    "postgres": "@modelcontextprotocol/server-postgres",
    "slack": "@modelcontextprotocol/server-slack",
    "puppeteer": "@modelcontextprotocol/server-puppeteer",
    "sequential-thinking": "@modelcontextprotocol/server-sequential-thinking",
}


def make_mcp_server_dockerfile(server_name: str) -> str:
    """Generate a Dockerfile for an isolated MCP server container."""
    npm_package = MCP_KNOWN_PACKAGES.get(server_name, server_name)
    binary_name = npm_package.rsplit("/", 1)[-1]
    return textwrap.dedent(f"""\
        FROM node:22-alpine

        # Install the MCP server package
        RUN npm install -g {npm_package}

        # Create non-root user
        RUN addgroup -S mcp && adduser -S mcp -G mcp
        USER mcp

        WORKDIR /workspace

        # Override in docker-compose or config.json if the binary name differs
        ENTRYPOINT ["{binary_name}"]
    """)


def make_mcp_server_config(server_name: str, project_path: str) -> str:
    """Generate a config.json stub for an MCP server."""
    npm_package = MCP_KNOWN_PACKAGES.get(server_name, server_name)
    config: dict = {
        "name": server_name,
        "package": npm_package,
        "description": f"Isolated MCP server: {server_name}",
        "args": [],
        "env": {},
        "project_path": project_path,
    }
    return json.dumps(config, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Scaffolding logic
# ---------------------------------------------------------------------------


def scaffold_project(
    name: str,
    stack_name: str,
    services: List[str],
    base_dir: Path,
    ai_providers: List[str] | None = None,
    ai_mode: str = "docker",
    ai_model: str | None = None,
    claude_md_template: str = "general",
) -> Path:
    """Create the full project scaffold. Returns the project directory path."""

    stack = STACKS[stack_name]
    project_dir = base_dir / name

    if project_dir.exists():
        print(f"Error: directory already exists: {project_dir}", file=sys.stderr)
        sys.exit(1)

    # -- directories --
    dirs = [
        project_dir,
        project_dir / stack["src_dir"],
        project_dir / "tests",
        project_dir / ".devcontainer",
        project_dir / ".github" / "workflows",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # -- files --
    files: Dict[Path, str] = {
        project_dir / ".shellcheckrc": make_shellcheckrc(),
        project_dir / ".gitignore": make_gitignore(stack),
        project_dir / "README.md": make_readme(name, stack_name),
        project_dir / "CLAUDE.md": make_claude_md(
            name, stack_name, stack, claude_md_template
        ),
        project_dir / ".pre-commit-config.yaml": make_precommit_config(),
        project_dir / ".github" / "workflows" / "ci.yml": make_ci_workflow(name, stack),
        project_dir / ".github" / "workflows" / "release.yml": make_cd_workflow(name),
        project_dir / ".devcontainer" / "Dockerfile": make_dockerfile(stack),
        project_dir / ".devcontainer" / "devcontainer.json": make_devcontainer_json(
            name,
            stack,
            services,
        ),
        project_dir / ".env.example": make_env_example(services),
    }

    if services:
        files[project_dir / "docker-compose.yml"] = make_docker_compose(services)

    for path, content in files.items():
        path.write_text(content)

    # -- AI setup (if requested during project creation) --
    if ai_providers:
        for provider in ai_providers:
            _ai_attach_to_project(
                project_dir=project_dir,
                provider=provider,
                mode=ai_mode,
                model=ai_model,
            )

    return project_dir


def _ai_attach_to_project(
    project_dir: Path,
    provider: str,
    mode: str,
    model: str | None = None,
    key_source: str = "env",
) -> None:
    """Attach an AI provider to an existing project directory."""
    ai_dir = project_dir / ".ai"
    name = project_dir.name

    if mode == "docker":
        _ai_attach_docker(ai_dir, name, provider, model, key_source)
    elif mode == "vm":
        _ai_attach_vm(ai_dir, name, provider, model, key_source)
    else:
        print(
            f"Error: unknown mode '{mode}'. Available: {', '.join(AI_MODES)}",
            file=sys.stderr,
        )
        sys.exit(1)


def _ai_attach_docker(
    ai_dir: Path,
    name: str,
    provider: str,
    model: str | None,
    key_source: str,
) -> None:
    """Set up Docker-mode AI for a project."""
    dirs = [ai_dir]
    if provider == "claude":
        dirs.append(ai_dir / "claude-code")
    dirs.append(ai_dir / "mcp-servers")

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    files: Dict[Path, str] = {
        ai_dir / "config.json": make_ai_config(
            name, provider, "docker", model, key_source
        ),
        ai_dir / "docker-compose.yml": make_ai_docker_compose(provider, model),
        ai_dir / "notify.py": make_notify_script(),
        ai_dir / "run.sh": make_run_script(provider),
        ai_dir / "mcp-servers" / ".gitkeep": "",
    }

    if provider == "claude":
        files[ai_dir / "claude-code" / "Dockerfile"] = make_ai_claude_dockerfile()
        files[ai_dir / "claude-code" / "settings.json"] = make_ai_claude_settings(
            [provider]
        )

    for path, content in files.items():
        path.write_text(content)

    # Make scripts executable
    for script in ["run.sh", "notify.py"]:
        s = ai_dir / script
        if s.exists():
            s.chmod(0o755)


def _ai_attach_vm(
    ai_dir: Path,
    name: str,
    provider: str,
    model: str | None,
    key_source: str,
) -> None:
    """Set up VM-mode AI for a project (QEMU/KVM)."""
    dirs = [
        ai_dir,
        ai_dir / "vm",
        ai_dir / "containers",
        ai_dir / "containers" / "mcp-servers",
    ]
    if provider == "claude":
        dirs.append(ai_dir / "containers" / "claude-code")

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    ai_providers_list = [provider]

    files: Dict[Path, str] = {
        ai_dir / "config.json": make_ai_config(name, provider, "vm", model, key_source),
        ai_dir / "Makefile": make_ai_makefile(name),
        ai_dir / "vm" / "cloud-init.yaml": make_ai_cloud_init(),
        ai_dir / "vm" / "vm-config.sh": make_ai_vm_config(name, ai_providers_list),
        ai_dir / "containers" / "docker-compose.yml": make_ai_vm_compose(
            ai_providers_list
        ),
        ai_dir / "containers" / "mcp-servers" / ".gitkeep": "",
        ai_dir / "notify.py": make_notify_script(),
        ai_dir / "run.sh": make_run_script(provider),
    }

    if provider == "claude":
        files[ai_dir / "containers" / "claude-code" / "Dockerfile"] = (
            make_ai_claude_dockerfile()
        )
        files[ai_dir / "containers" / "claude-code" / "settings.json"] = (
            make_ai_claude_settings(ai_providers_list)
        )

    for path, content in files.items():
        path.write_text(content)

    # Make scripts executable
    for script_path in [
        ai_dir / "vm" / "vm-config.sh",
        ai_dir / "run.sh",
        ai_dir / "notify.py",
    ]:
        if script_path.exists():
            script_path.chmod(0o755)


# ---------------------------------------------------------------------------
# AI management (start/stop/status/run)
# ---------------------------------------------------------------------------


def _load_ai_config(project_dir: Path) -> dict:
    """Load .ai/config.json from a project directory."""
    config_path = project_dir / ".ai" / "config.json"
    if not config_path.exists():
        print(
            f"Error: no AI configuration found at {config_path}\n"
            "  Attach AI with: dtl ai attach --project <path> --provider claude",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


def _save_ai_config(project_dir: Path, config: dict) -> None:
    """Save .ai/config.json."""
    config_path = project_dir / ".ai" / "config.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")


def _resolve_provider_chain(project_dir: Path) -> list[str]:
    """Return the ordered provider list for a project.

    Reads ``provider_chain`` from .ai/config.json when present and non-empty;
    falls back to ``[config["provider"]]`` for backward compatibility.
    Returns ``["claude"]`` when no config file exists.
    """
    config_path = project_dir / ".ai" / "config.json"
    if not config_path.exists():
        return ["claude"]
    with open(config_path) as f:
        config = json.load(f)
    chain = config.get("provider_chain")
    if chain and isinstance(chain, list) and chain:
        return [str(p) for p in chain]
    return [config.get("provider", "claude")]


def ai_start(project_dir: Path) -> None:
    """Start the AI containers/VM for a project."""
    config = _load_ai_config(project_dir)
    mode = config["mode"]
    ai_dir = project_dir / ".ai"

    if mode == "docker":
        compose_file = ai_dir / "docker-compose.yml"
        print("[dtl ai] Starting Docker containers...")
        _run_cmd(["docker", "compose", "-f", str(compose_file), "up", "-d"])
        print("[dtl ai] Containers started.")

        provider = config["provider"]
        if provider == "claude":
            print("[dtl ai] Interactive session:")
            print(f"  docker compose -f {compose_file} run --rm claude-code")
        elif provider == "openclaw":
            print("[dtl ai] OpenClaw gateway running on port 18789")
            print("[dtl ai] Connect via Telegram or configured chat apps")
        elif provider == "ollama":
            print("[dtl ai] Ollama running on port 11434")
            print(
                f"[dtl ai] Pull a model: docker compose -f {compose_file} exec ollama ollama pull llama3"
            )

    elif mode == "vm":
        vm_script = ai_dir / "vm" / "vm-config.sh"
        print("[dtl ai] Starting AI sandbox VM...")
        _run_cmd(["bash", str(vm_script), "start"])

    print(f"[dtl ai] Provider: {config['provider']} | Mode: {mode}")
    if config.get("model"):
        print(f"[dtl ai] Model: {config['model']}")


def ai_stop(project_dir: Path) -> None:
    """Stop the AI containers/VM for a project."""
    config = _load_ai_config(project_dir)
    mode = config["mode"]
    ai_dir = project_dir / ".ai"

    if mode == "docker":
        compose_file = ai_dir / "docker-compose.yml"
        print("[dtl ai] Stopping Docker containers...")
        _run_cmd(["docker", "compose", "-f", str(compose_file), "down"])
    elif mode == "vm":
        vm_script = ai_dir / "vm" / "vm-config.sh"
        _run_cmd(["bash", str(vm_script), "stop"])

    print("[dtl ai] Stopped.")


def ai_status(project_dir: Path) -> None:
    """Show AI container/VM status for a project."""
    config = _load_ai_config(project_dir)
    mode = config["mode"]
    ai_dir = project_dir / ".ai"

    print(f"[dtl ai] Project:  {config['project_name']}")
    print(f"[dtl ai] Provider: {config['provider']}")
    print(f"[dtl ai] Mode:     {mode}")
    if config.get("model"):
        print(f"[dtl ai] Model:    {config['model']}")

    notify = config.get("notify", {})
    if notify.get("provider"):
        print(f"[dtl ai] Notify:   {notify['provider']}")
    else:
        print("[dtl ai] Notify:   not configured")

    print()

    if mode == "docker":
        compose_file = ai_dir / "docker-compose.yml"
        _run_cmd(["docker", "compose", "-f", str(compose_file), "ps"])
    elif mode == "vm":
        vm_script = ai_dir / "vm" / "vm-config.sh"
        _run_cmd(["bash", str(vm_script), "status"])


def _write_failure_snapshot(
    project_dir: Path,
    feature: dict,
    branch: str,
    ai_exit_code: int,
    duration_secs: float,
    ai_output: str,
    log: "logging.Logger",
) -> Optional[Path]:
    """Write a triage bundle to ~/.local/state/dtl/ on AI non-zero exit.

    Returns the snapshot path on success, None on failure.  Never raises.
    """
    try:
        state_dir = _dtl_state_dir()
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        iso_ts = now_utc.strftime("%Y%m%dT%H%M%SZ")
        snapshot_path = (
            state_dir / f"{project_dir.name}-{feature['name']}-failure-{iso_ts}.md"
        )

        # Last 200 combined lines (already interleaved in ai_output)
        all_lines = ai_output.splitlines(keepends=True)
        last_lines = all_lines[-200:] if len(all_lines) > 200 else all_lines
        last_block = "".join(last_lines)

        # git status --porcelain
        git_status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        git_status = git_status_result.stdout

        # git diff --stat develop..HEAD
        diff_stat_result = subprocess.run(
            ["git", "diff", "--stat", "develop..HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        diff_stat = diff_stat_result.stdout

        # git diff develop..HEAD (capped at 5000 lines)
        diff_result = subprocess.run(
            ["git", "diff", "develop..HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        diff_lines = diff_result.stdout.splitlines(keepends=True)
        diff_truncated = len(diff_lines) > 5000
        diff_body = "".join(diff_lines[:5000])

        # Untracked files (relative paths only)
        untracked_result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        untracked = untracked_result.stdout.strip()

        duration_str = f"{int(duration_secs // 60)}m {int(duration_secs % 60)}s"
        ts_display = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            "# AI Failure Snapshot\n\n",
            f"**Generated:** {ts_display}  \n",
            f"**Project:** {project_dir}  \n",
            f"**Feature:** {feature['name']}  \n",
            f"**Branch:** {branch}  \n",
            f"**AI exit code:** {ai_exit_code}  \n",
            f"**Wall-clock duration:** {duration_str}  \n\n",
            "## Last 200 Lines of AI Output\n\n",
            "```\n",
            last_block,
            "```\n\n",
            "## Git Status\n\n",
            "```\n",
            git_status,
            "```\n\n",
            "## Diff Stat (develop..HEAD)\n\n",
            "```\n",
            diff_stat,
            "```\n\n",
            "## Full Diff (develop..HEAD)\n\n",
            "```diff\n",
            diff_body,
        ]
        if diff_truncated:
            lines.append("\n[... diff truncated at 5000 lines ...]\n")
        lines.append("```\n\n")
        lines.append("## Untracked Files\n\n")
        if untracked:
            for uf in untracked.splitlines():
                lines.append(f"- {uf}\n")
        else:
            lines.append("*(none)*\n")

        snapshot_path.write_text("".join(lines))
        log.info("failure snapshot written: %s", snapshot_path)
        return snapshot_path
    except Exception as exc:
        log.info("Failed to write failure snapshot: %s", exc)
        return None


def _latest_failure_snapshot(project_dir: Path) -> Optional[Path]:
    """Return the most recent failure snapshot path for a project, or None."""
    state_dir = _dtl_state_dir()
    prefix = f"{project_dir.name}-"
    suffix = "-failure-"
    candidates = [
        p
        for p in state_dir.glob(f"{project_dir.name}-*-failure-*.md")
        if p.name.startswith(prefix) and suffix in p.name
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def _run_ai_with_limits(
    cmd: list[str],
    env: dict,
    max_wall_clock: int,
    max_ai_retries: int,
) -> tuple[int, list[str]]:
    """Run a subprocess, streaming output while enforcing wall-clock and retry caps.

    Returns (returncode, output_lines).
    returncode is 124 on wall-clock timeout, 125 on retry-cap, else the real code.
    """
    # Pattern to detect "AI is looping" — Claude Code retrying failed tests
    retry_re = re.compile(r"tests?\s+failed|retrying", re.IGNORECASE)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    lines: list[str] = []
    retry_count = 0
    kill_reason: str | None = None
    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        remaining = max_wall_clock - elapsed
        if remaining <= 0:
            kill_reason = "wall_clock"
            proc.kill()
            break

        # select with a short poll interval so we catch timeouts promptly
        try:
            readable, _, _ = select.select([proc.stdout], [], [], min(remaining, 5.0))
        except (ValueError, OSError):
            break

        if readable:
            line = proc.stdout.readline()
            if not line:  # EOF — process exited
                break
            lines.append(line)
            print(line, end="", flush=True)
            if retry_re.search(line):
                retry_count += 1
                if max_ai_retries > 0 and retry_count >= max_ai_retries:
                    kill_reason = "retry_cap"
                    proc.kill()
                    break
        else:
            # select timed out — process still running, re-check wall clock
            if proc.poll() is not None:
                break

    try:
        proc.stdout.close()
    except OSError:
        pass
    proc.wait()

    if kill_reason is not None:
        return_code = 124 if kill_reason == "wall_clock" else 125
        return return_code, lines

    return proc.returncode, lines


def ai_run(
    project_dir: Path,
    prompt: str,
    continue_session: bool = False,
    max_wall_clock: int = 1800,
    max_ai_retries: int = 3,
    feature_name: str = "",
    provider_override: str | None = None,
) -> None:
    """Run an autonomous AI session with a prompt."""
    config = _load_ai_config(project_dir)
    provider = provider_override or config["provider"]
    mode = config["mode"]
    ai_dir = project_dir / ".ai"

    pconfig = AI_PROVIDERS_CONFIG.get(provider, {})
    if not pconfig.get("supports_autonomous"):
        print(
            f"Error: provider '{provider}' does not support autonomous mode.\n"
            f"  Providers with autonomous support: "
            + ", ".join(
                p
                for p, c in AI_PROVIDERS_CONFIG.items()
                if c.get("supports_autonomous")
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Ollama: run directly against the host daemon, regardless of configured mode.
    # Uses `ollama run <model> <prompt>` in single-shot (non-interactive) mode.
    if provider == "ollama":
        model = config.get("model") or AI_PROVIDERS_CONFIG["ollama"]["default_model"]
        print(f"[dtl ai run] Running Ollama autonomously (model: {model})...")
        print(f"[dtl ai run] Prompt: {prompt}")
        if max_wall_clock:
            print(f"[dtl ai run] Wall-clock limit: {max_wall_clock}s")
        print()
        cmd = ["ollama", "run", model, prompt]
        try:
            exit_code, output_lines = _run_ai_with_limits(
                cmd,
                {**os.environ},
                max_wall_clock,
                max_ai_retries,
            )
        except FileNotFoundError:
            print(
                "Error: ollama not found. Install Ollama and ensure it is in PATH.",
                file=sys.stderr,
            )
            sys.exit(127)
        _send_notification(
            ai_dir,
            exit_code,
            "".join(output_lines[-10:]) or "(no output)",
        )
        sys.exit(exit_code)

    if mode == "docker":
        if provider == "claude":
            compose_file = ai_dir / "docker-compose.yml"
            if continue_session:
                print("[dtl ai run] Continuing previous session...")
            else:
                print("[dtl ai run] Running Claude Code autonomously...")
            print(f"[dtl ai run] Prompt: {prompt}")
            if max_wall_clock:
                print(f"[dtl ai run] Wall-clock limit: {max_wall_clock}s")
            if max_ai_retries:
                print(f"[dtl ai run] Retry cap: {max_ai_retries}")
            print()

            # Run Claude Code in print mode (non-interactive)
            cmd = [
                "docker",
                "compose",
                "-f",
                str(compose_file),
                "run",
                "--rm",
                "claude-code",
                "--print",
            ]
            if continue_session:
                cmd.append("--continue")
            cmd.extend(["-p", prompt])

            try:
                exit_code, output_lines = _run_ai_with_limits(
                    cmd,
                    {**os.environ},
                    max_wall_clock,
                    max_ai_retries,
                )
            except FileNotFoundError:
                print(
                    "Error: docker not found. Install Docker to use AI containers.",
                    file=sys.stderr,
                )
                sys.exit(127)

            # On bail-out: stop the container
            if exit_code in (124, 125):
                limit_hit = "wall_clock" if exit_code == 124 else "retry_cap"
                print(
                    f"\n[dtl ai run] Limit reached ({limit_hit}). "
                    "Stopping container...",
                    file=sys.stderr,
                )
                subprocess.run(
                    [
                        "docker",
                        "compose",
                        "-f",
                        str(compose_file),
                        "stop",
                    ],
                    capture_output=True,
                    timeout=30,
                )

            # Send notification
            _send_notification(
                ai_dir,
                exit_code,
                "".join(output_lines[-10:]) or "(no output)",
            )

            sys.exit(exit_code)

        elif provider == "openclaw":
            # OpenClaw is natively autonomous — just start the gateway
            compose_file = ai_dir / "docker-compose.yml"
            print("[dtl ai run] Starting OpenClaw gateway (autonomous mode)...")
            print("[dtl ai run] OpenClaw handles its own chat-app integration.")
            print("[dtl ai run] Connect via Telegram to send prompts.")
            _run_cmd(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "up",
                    "-d",
                    "openclaw-gateway",
                ]
            )
            _send_notification(
                ai_dir, 0, "OpenClaw gateway started. Send commands via Telegram."
            )

    elif mode == "vm":
        run_script = ai_dir / "run.sh"
        if provider == "claude":
            print("[dtl ai run] Running Claude Code in VM...")
            try:
                subprocess.run(
                    ["bash", str(run_script), prompt],
                    timeout=max_wall_clock if max_wall_clock else None,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                print(
                    "\n[dtl ai run] Wall-clock timeout reached.",
                    file=sys.stderr,
                )
                sys.exit(124)
        elif provider == "openclaw":
            print("[dtl ai run] Starting OpenClaw in VM...")
            _run_cmd(["bash", str(run_script), "start"])


def _send_notification(ai_dir: Path, exit_code: int, message: str) -> None:
    """Send a notification via the configured provider."""
    config_path = ai_dir / "config.json"
    if not config_path.exists():
        return

    with open(config_path) as f:
        config = json.load(f)

    notify = config.get("notify", {})
    if not notify.get("provider"):
        return

    notify_script = ai_dir / "notify.py"
    if not notify_script.exists():
        return

    try:
        subprocess.run(
            ["python3", str(notify_script), str(exit_code)],
            input=message,
            text=True,
            timeout=15,
            env={**os.environ},
        )
    except Exception as e:
        print(f"[dtl ai] Notification failed: {e}", file=sys.stderr)


def _run_cmd(cmd: List[str]) -> int:
    """Run a command, printing output in real time. Returns exit code."""
    try:
        result = subprocess.run(cmd, env={**os.environ})
        return result.returncode
    except FileNotFoundError:
        print(f"Error: command not found: {cmd[0]}", file=sys.stderr)
        print(f"  Full command: {' '.join(cmd)}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("\n[dtl ai] Interrupted.", file=sys.stderr)
        return 130


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _check_ai_port_mappings(compose_content: str) -> bool:
    """Return True if no AI containers have host port mappings.

    AI containers (claude-code, openclaw-gateway) must not expose host ports.
    Service containers (postgres, redis, ollama, etc.) are allowed to have ports.
    Parses docker-compose.yml per-service using regex (no pyyaml dependency).
    """
    AI_SERVICES = {"claude-code", "openclaw-gateway"}

    lines = compose_content.splitlines()
    in_services = False
    current_service: str | None = None
    current_service_lines: list[str] = []
    services: dict[str, list[str]] = {}

    for line in lines:
        if line.rstrip() == "services:":
            in_services = True
            continue

        if in_services:
            # A non-indented non-empty line ends the services section
            if line and not line[0].isspace():
                if current_service:
                    services[current_service] = current_service_lines
                in_services = False
                current_service = None
                current_service_lines = []
                continue

            # Service name: exactly 2-space indent, word chars, colon
            m = re.match(r"^  ([a-zA-Z][\w-]*):\s*$", line)
            if m:
                if current_service:
                    services[current_service] = current_service_lines
                current_service = m.group(1)
                current_service_lines = [line]
            elif current_service is not None:
                current_service_lines.append(line)

    if current_service:
        services[current_service] = current_service_lines

    for service_name, service_lines in services.items():
        if service_name in AI_SERVICES and "ports:" in "\n".join(service_lines):
            return False

    return True


def validate_project(project_dir: Path) -> bool:
    """Run basic validation checks on the scaffolded project."""
    passed = 0
    total = 0

    def check(label: str, ok: bool) -> None:
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
            print(f"  [ok] {label}")
        else:
            print(f"  [!!] {label}")

    devcontainer_json = project_dir / ".devcontainer" / "devcontainer.json"
    if devcontainer_json.exists():
        config = json.loads(devcontainer_json.read_text())
        run_args = config.get("runArgs", [])
        check(
            "devcontainer: --cap-drop=ALL",
            "--cap-drop=ALL" in run_args,
        )
        check(
            "devcontainer: --security-opt=no-new-privileges",
            "--security-opt=no-new-privileges" in run_args,
        )

    gitignore = project_dir / ".gitignore"
    if gitignore.exists():
        gi = gitignore.read_text()
        check(".gitignore: excludes .env files", ".env" in gi)
        check(".gitignore: excludes .pem files", "*.pem" in gi)

    check("CLAUDE.md exists", (project_dir / "CLAUDE.md").exists())
    check(
        ".pre-commit-config.yaml exists",
        (project_dir / ".pre-commit-config.yaml").exists(),
    )
    check(
        "CI workflow exists",
        (project_dir / ".github" / "workflows" / "ci.yml").exists(),
    )
    check(
        "Release workflow exists",
        (project_dir / ".github" / "workflows" / "release.yml").exists(),
    )

    compose = project_dir / "docker-compose.yml"
    if compose.exists():
        content = compose.read_text()
        check(
            "docker-compose.yml: AI containers have no host port mappings",
            _check_ai_port_mappings(content),
        )

    # AI config checks (new .ai/ structure)
    ai_dir = project_dir / ".ai"
    if ai_dir.is_dir():
        check(
            "ai: config.json exists",
            (ai_dir / "config.json").exists(),
        )
        check(
            "ai: docker-compose.yml exists",
            (ai_dir / "docker-compose.yml").exists()
            or (ai_dir / "containers" / "docker-compose.yml").exists(),
        )
        check(
            "ai: notify.py exists",
            (ai_dir / "notify.py").exists(),
        )
        check(
            "ai: run.sh exists",
            (ai_dir / "run.sh").exists(),
        )

        ai_compose = ai_dir / "docker-compose.yml"
        if ai_compose.exists():
            content = ai_compose.read_text()
            if "claude-code:" in content:
                check(
                    "ai: claude containers use cap_drop ALL",
                    "cap_drop:" in content and "ALL" in content,
                )
                check(
                    "ai: claude containers use no-new-privileges",
                    "no-new-privileges" in content,
                )

        # VM mode checks
        if (ai_dir / "vm").is_dir():
            check(
                "ai: VM config exists",
                (ai_dir / "vm" / "vm-config.sh").exists(),
            )
            check(
                "ai: cloud-init exists",
                (ai_dir / "vm" / "cloud-init.yaml").exists(),
            )
            check(
                "ai: Makefile exists",
                (ai_dir / "Makefile").exists(),
            )

        # MCP server isolation checks
        mcp_dir = None
        if (ai_dir / "mcp-servers").is_dir():
            mcp_dir = ai_dir / "mcp-servers"
        elif (ai_dir / "containers" / "mcp-servers").is_dir():
            mcp_dir = ai_dir / "containers" / "mcp-servers"

        if mcp_dir:
            for srv_dir in sorted(mcp_dir.iterdir()):
                if not srv_dir.is_dir() or srv_dir.name.startswith("."):
                    continue
                srv = srv_dir.name
                check(
                    f"mcp-{srv}: Dockerfile exists", (srv_dir / "Dockerfile").exists()
                )
                check(
                    f"mcp-{srv}: config.json exists", (srv_dir / "config.json").exists()
                )

    # Legacy ai-sandbox/ checks (backward compat)
    sandbox = project_dir / "ai-sandbox"
    if sandbox.is_dir():
        check(
            "ai-sandbox: Makefile exists",
            (sandbox / "Makefile").exists(),
        )
        check(
            "ai-sandbox: VM config exists",
            (sandbox / "vm" / "vm-config.sh").exists(),
        )

    print(f"\n  {passed}/{total} checks passed.")
    return passed == total


# ---------------------------------------------------------------------------
# CLI command handlers
# ---------------------------------------------------------------------------


def cmd_new(args: argparse.Namespace) -> None:
    """Handle the 'new' subcommand."""
    name: str = args.name
    stack_name: str = args.stack
    base_dir: Path = Path(args.dir).resolve()

    # Validate stack
    if stack_name not in STACKS:
        print(
            f"Error: unknown stack '{stack_name}'. "
            f"Available: {', '.join(sorted(STACKS))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate services
    services: List[str] = []
    if args.services:
        for s in args.services.split(","):
            s = s.strip()
            if s not in SERVICES:
                print(
                    f"Error: unknown service '{s}'. "
                    f"Available: {', '.join(sorted(SERVICES))}",
                    file=sys.stderr,
                )
                sys.exit(1)
            services.append(s)

    # Validate AI providers
    ai_providers: List[str] = []
    if args.ai:
        for a in args.ai.split(","):
            a = a.strip()
            if a not in AI_PROVIDERS:
                print(
                    f"Error: unknown AI provider '{a}'. "
                    f"Available: {', '.join(AI_PROVIDERS)}",
                    file=sys.stderr,
                )
                sys.exit(1)
            ai_providers.append(a)

    # Validate AI mode
    ai_mode = getattr(args, "mode", "docker") or "docker"
    if ai_mode not in AI_MODES:
        print(
            f"Error: unknown AI mode '{ai_mode}'. Available: {', '.join(AI_MODES)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate model
    ai_model = getattr(args, "model", None)

    # Validate template
    template = getattr(args, "template", "general") or "general"
    if template not in CLAUDE_MD_TEMPLATES:
        print(
            f"Error: unknown template '{template}'. "
            f"Available: {', '.join(sorted(CLAUDE_MD_TEMPLATES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate base dir
    if not base_dir.is_dir():
        print(f"Error: directory does not exist: {base_dir}", file=sys.stderr)
        sys.exit(1)

    # Scaffold
    print(f"Scaffolding {stack_name} project '{name}' in {base_dir}/")
    if services:
        print(f"  Services: {', '.join(services)}")
    if ai_providers:
        print(f"  AI: {', '.join(ai_providers)} (mode: {ai_mode})")
    if ai_model:
        print(f"  Model: {ai_model}")
    if template != "general":
        print(f"  CLAUDE.md template: {template}")

    project_dir = scaffold_project(
        name,
        stack_name,
        services,
        base_dir,
        ai_providers=ai_providers or None,
        ai_mode=ai_mode,
        ai_model=ai_model,
        claude_md_template=template,
    )

    print(f"\nProject created: {project_dir}\n")

    # Validate
    print("Running validation:")
    validate_project(project_dir)

    # Next steps
    print()
    print("Next steps:")
    print(f"  cd {project_dir}")
    print("  git init && git add -A && git commit -m 'feat: initial scaffold'")
    print("  pre-commit install")
    if ai_providers:
        ai_dir = project_dir / ".ai"
        if ai_mode == "docker":
            print(f"  dtl ai start --project {project_dir}")
        elif ai_mode == "vm":
            print(f"  make -C {ai_dir} up     # Start AI sandbox VM")
            print(f"  make -C {ai_dir} ssh    # SSH into sandbox")
    else:
        print("  # Open in VS Code and select 'Reopen in Container'")
        print("  # To add AI later: dtl ai attach --project . --provider claude")


def cmd_list_stacks(args: argparse.Namespace) -> None:
    """Handle the 'list-stacks' subcommand."""
    print("Available stacks:\n")
    for key, stack in sorted(STACKS.items()):
        print(f"  {key:10s}  {stack['display']}")

    print("\nAvailable services (use with --services):\n")
    for key, svc in sorted(SERVICES.items()):
        print(f"  {key:10s}  {svc['image']}")

    print("\nAvailable AI providers (use with dtl ai attach --provider):\n")
    for key, pconfig in sorted(AI_PROVIDERS_CONFIG.items()):
        auto = " [autonomous]" if pconfig.get("supports_autonomous") else ""
        print(f"  {key:12s}  {pconfig['display']}{auto}")
        if pconfig["models"]:
            models = ", ".join(sorted(pconfig["models"].keys()))
            print(
                f"  {' ':12s}  Models: {models} (default: {pconfig['default_model']})"
            )

    print("\nAI modes:\n")
    print("  docker      Lightweight — containers on host Docker")
    print("  vm          Full isolation — QEMU/KVM micro-VM")

    print("\nCLAUDE.md templates (use with --template):\n")
    for key in sorted(CLAUDE_MD_TEMPLATES):
        print(f"  {key}")


def cmd_add_mcp(args: argparse.Namespace) -> None:
    """Handle the 'add-mcp' subcommand."""
    server_name: str = args.name
    project_dir = Path(args.project).resolve()
    project_path: str = args.project_path or "/workspace"

    # Support both .ai/ and legacy ai-sandbox/ paths
    ai_dir = project_dir / ".ai"
    legacy_sandbox = project_dir / "ai-sandbox"

    if ai_dir.is_dir():
        # New structure
        if (ai_dir / "containers" / "mcp-servers").is_dir():
            mcp_dir = ai_dir / "containers" / "mcp-servers"
            compose_path = ai_dir / "containers" / "docker-compose.yml"
            settings_dir = ai_dir / "containers" / "claude-code"
        else:
            mcp_dir = ai_dir / "mcp-servers"
            compose_path = ai_dir / "docker-compose.yml"
            settings_dir = ai_dir / "claude-code"
    elif legacy_sandbox.is_dir():
        mcp_dir = legacy_sandbox / "containers" / "mcp-servers"
        compose_path = legacy_sandbox / "containers" / "docker-compose.yml"
        settings_dir = legacy_sandbox / "containers" / "claude-code"
    else:
        print(
            f"Error: no AI configuration found in {project_dir}.\n"
            "  Attach AI with: dtl ai attach --project <path> --provider claude",
            file=sys.stderr,
        )
        sys.exit(1)

    srv_dir = mcp_dir / server_name
    if srv_dir.exists():
        print(
            f"Error: MCP server '{server_name}' already exists at {srv_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    srv_dir.mkdir(parents=True, exist_ok=True)

    # Write Dockerfile and config
    (srv_dir / "Dockerfile").write_text(make_mcp_server_dockerfile(server_name))
    (srv_dir / "config.json").write_text(
        make_mcp_server_config(server_name, project_path)
    )

    # Discover all MCP servers
    existing_servers: List[str] = sorted(
        d.name for d in mcp_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )

    # Detect active AI providers from existing compose
    ai_providers: List[str] = []
    if compose_path.exists():
        compose_text = compose_path.read_text()
        if "claude-code:" in compose_text:
            ai_providers.append("claude")
    if not ai_providers:
        ai_providers = ["claude"]

    # Regenerate docker-compose and settings with all MCP servers
    compose_path.write_text(
        make_ai_vm_compose(ai_providers, mcp_servers=existing_servers)
    )

    settings_path = settings_dir / "settings.json"
    if settings_path.parent.is_dir():
        settings_path.write_text(
            make_ai_claude_settings(ai_providers, mcp_servers=existing_servers)
        )

    npm_package = MCP_KNOWN_PACKAGES.get(server_name, server_name)
    print(f"MCP server '{server_name}' added to {srv_dir}\n")
    print("Isolation rules applied:")
    print("  network_mode: none    (no network stack)")
    print("  read_only: true       (immutable root filesystem)")
    print("  cap_drop: ALL         (no Linux capabilities)")
    print("  memory: 512MB, 1 CPU  (resource limits)")
    print("  /workspace: read-only (project files)")

    print("\nNext steps:")
    print(f"  1. Review {srv_dir / 'Dockerfile'}")
    if npm_package != server_name:
        print(f"     (installs {npm_package})")
    print(f"  2. Edit {srv_dir / 'config.json'} to set server arguments")
    print(f"  3. Rebuild: cd {compose_path.parent} && docker compose build")
    print(f"  4. Test: docker compose run --rm mcp-{server_name}")

    print("\nValidation:")
    validate_project(project_dir)


# ---------------------------------------------------------------------------
# CLI — dtl ai subcommands
# ---------------------------------------------------------------------------


def cmd_ai_add_mcp(args: argparse.Namespace) -> None:
    """Handle 'dtl ai add-mcp' subcommand (maps --server → --name)."""
    args.name = args.server
    cmd_add_mcp(args)


def cmd_ai_attach(args: argparse.Namespace) -> None:
    """Handle 'dtl ai attach'."""
    project_dir = Path(args.project).resolve()
    provider = args.provider
    mode = args.mode
    model = args.model
    key_source = args.key_source

    if not project_dir.is_dir():
        print(f"Error: directory does not exist: {project_dir}", file=sys.stderr)
        sys.exit(1)

    if provider not in AI_PROVIDERS_CONFIG:
        print(
            f"Error: unknown provider '{provider}'. "
            f"Available: {', '.join(sorted(AI_PROVIDERS_CONFIG))}",
            file=sys.stderr,
        )
        sys.exit(1)

    if mode not in AI_MODES:
        print(
            f"Error: unknown mode '{mode}'. Available: {', '.join(AI_MODES)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate model for providers that have model lists
    pconfig = AI_PROVIDERS_CONFIG[provider]
    if model and pconfig["models"] and model not in pconfig["models"]:
        print(
            f"Error: unknown model '{model}' for provider '{provider}'. "
            f"Available: {', '.join(sorted(pconfig['models']))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Use default model if none specified
    if not model and pconfig["default_model"]:
        model = pconfig["default_model"]

    ai_dir = project_dir / ".ai"
    if ai_dir.exists():
        print(f"Warning: AI already configured at {ai_dir}")
        print(f"  Use 'dtl ai detach --project {project_dir}' first to reconfigure.")
        sys.exit(1)

    # CI workflow requirement — needed to gate 'gh pr merge --auto --squash'
    scaffold_ci = getattr(args, "scaffold_ci", False)
    no_ci = getattr(args, "no_ci", False)
    workflows_dir = project_dir / ".github" / "workflows"
    has_ci = workflows_dir.is_dir() and any(workflows_dir.glob("*.yml"))

    if not has_ci:
        if scaffold_ci:
            workflows_dir.mkdir(parents=True, exist_ok=True)
            (workflows_dir / "ci.yml").write_text(_CI_YML_SCAFFOLD)
            print("  Scaffolded CI workflow: .github/workflows/ci.yml")
        elif not no_ci:
            print(
                "Error: no CI workflow found at .github/workflows/*.yml",
                file=sys.stderr,
            )
            print("", file=sys.stderr)
            print(
                "CI is required because 'gh pr merge --auto --squash' needs a passing",
                file=sys.stderr,
            )
            print(
                "status check to gate on. Without CI, the workflow loop stalls waiting",
                file=sys.stderr,
            )
            print("for merge.", file=sys.stderr)
            print("", file=sys.stderr)
            print("Options:", file=sys.stderr)
            print(
                "  --scaffold-ci   write a standard .github/workflows/ci.yml and continue",
                file=sys.stderr,
            )
            print(
                "  --no-ci         skip this check (not recommended)", file=sys.stderr
            )
            sys.exit(1)

    print(f"Attaching {pconfig['display']} to {project_dir.name}")
    print(f"  Provider: {provider}")
    print(f"  Mode:     {mode}")
    if model:
        print(f"  Model:    {model}")
    print(f"  Key:      {key_source}")

    _ai_attach_to_project(
        project_dir=project_dir,
        provider=provider,
        mode=mode,
        model=model,
        key_source=key_source,
    )

    print(f"\nAI attached: {ai_dir}\n")

    print("Running validation:")
    validate_project(project_dir)

    print()
    print("Next steps:")
    if mode == "docker":
        print(f"  dtl ai start --project {project_dir}")
        if provider == "claude":
            print(
                f"  # Then: docker compose -f {ai_dir}/docker-compose.yml run --rm claude-code"
            )
        elif provider == "openclaw":
            print("  # Then connect via Telegram")
    elif mode == "vm":
        print(f"  make -C {ai_dir} up")
        print(f"  make -C {ai_dir} ssh")

    # Auth hints
    if provider == "claude":
        print("\n  Auth: run 'claude login' inside the container (one-time OAuth).")
        print("  Token persists in the claude-data volume across restarts.")
    env_key = pconfig.get("env_key")
    if env_key:
        env_val = os.environ.get(env_key, "")
        if not env_val:
            print(f"\n  WARNING: {env_key} is not set in your environment.")
            print(f"  Export it before starting: export {env_key}=sk-...")


def cmd_ai_detach(args: argparse.Namespace) -> None:
    """Handle 'dtl ai detach'."""
    project_dir = Path(args.project).resolve()
    ai_dir = project_dir / ".ai"

    if not ai_dir.is_dir():
        print(f"Error: no AI configuration at {ai_dir}", file=sys.stderr)
        sys.exit(1)

    # Stop containers first
    config = _load_ai_config(project_dir)
    if config["mode"] == "docker":
        compose_file = ai_dir / "docker-compose.yml"
        if compose_file.exists():
            print("[dtl ai] Stopping containers first...")
            _run_cmd(["docker", "compose", "-f", str(compose_file), "down"])
    elif config["mode"] == "vm":
        vm_script = ai_dir / "vm" / "vm-config.sh"
        if vm_script.exists():
            print("[dtl ai] Stopping VM first...")
            _run_cmd(["bash", str(vm_script), "stop"])

    import shutil

    shutil.rmtree(ai_dir)
    print(f"[dtl ai] AI detached from {project_dir.name}")
    print(f"  Removed: {ai_dir}")


def cmd_ai_start(args: argparse.Namespace) -> None:
    """Handle 'dtl ai start'."""
    project_dir = Path(args.project).resolve()
    ai_start(project_dir)


def cmd_ai_stop(args: argparse.Namespace) -> None:
    """Handle 'dtl ai stop'."""
    project_dir = Path(args.project).resolve()
    ai_stop(project_dir)


def cmd_ai_status(args: argparse.Namespace) -> None:
    """Handle 'dtl ai status'."""
    project_dir = Path(args.project).resolve()
    ai_status(project_dir)


def cmd_ai_run(args: argparse.Namespace) -> None:
    """Handle 'dtl ai run'."""
    project_dir = Path(args.project).resolve()
    prompt = args.prompt
    # --provider overrides the config; --provider-chain sets the first provider in a
    # chain (rotation is handled by cmd_workflow_run at the outer loop level).
    provider_override = getattr(args, "provider", None) or None
    if not provider_override:
        chain_arg = getattr(args, "provider_chain", None)
        if chain_arg:
            provider_override = chain_arg.split(",")[0].strip() or None
    ai_run(
        project_dir,
        prompt,
        continue_session=getattr(args, "continue_session", False),
        max_wall_clock=getattr(args, "max_wall_clock", 1800),
        max_ai_retries=getattr(args, "max_ai_retries", 3),
        feature_name=getattr(args, "feature_name", ""),
        provider_override=provider_override,
    )


def cmd_ai_config_notify(args: argparse.Namespace) -> None:
    """Handle 'dtl ai config-notify'."""
    project_dir = Path(args.project).resolve()
    config = _load_ai_config(project_dir)

    config["notify"] = {
        "provider": "telegram",
        "telegram_token": args.telegram_token,
        "telegram_chat_id": args.telegram_chat_id,
    }
    _save_ai_config(project_dir, config)

    print(f"[dtl ai] Telegram notifications configured for {config['project_name']}")
    print(f"  Token:   {args.telegram_token[:8]}...{args.telegram_token[-4:]}")
    print(f"  Chat ID: {args.telegram_chat_id}")

    # Test notification
    if args.test:
        print("\n[dtl ai] Sending test notification...")
        _send_notification(
            project_dir / ".ai",
            0,
            f"Test notification from dtl for project '{config['project_name']}'",
        )
        print("[dtl ai] Check your Telegram.")


def cmd_ai_list_providers(args: argparse.Namespace) -> None:
    """Handle 'dtl ai list-providers'."""
    print("Available AI providers:\n")
    print(
        "  Quota-source annotations:\n"
        "    [anthropic-shared]  Shares the same Anthropic quota — "
        "claude and openclaw exhaust the same pool.\n"
        "    [local]             No external quota — runs on local hardware.\n"
    )
    for key, pconfig in sorted(AI_PROVIDERS_CONFIG.items()):
        auto = " [autonomous]" if pconfig.get("supports_autonomous") else ""
        inter = " [interactive]" if pconfig.get("supports_interactive") else ""
        quota_src = pconfig.get("quota_source", "unknown")
        print(f"  {key}  [{quota_src}]")
        print(f"    {pconfig['description']}")
        print(f"    Image: {pconfig['image']}")
        print(f"    Modes:{auto}{inter}")
        if pconfig["models"]:
            for mname, mid in sorted(pconfig["models"].items()):
                default = " (default)" if mname == pconfig["default_model"] else ""
                print(f"    Model: {mname:8s} → {mid}{default}")
        if pconfig["env_key"]:
            print(f"    Env:   {pconfig['env_key']}")
        print()

    print("AI modes:\n")
    print("  docker    Lightweight containers on host Docker daemon")
    print("            Best for: fast iteration, low overhead, development")
    print()
    print("  vm        Full QEMU/KVM micro-VM isolation")
    print("            Best for: untrusted code, security research, production")


# ---------------------------------------------------------------------------
# Workflow: DEVPLAN parsing and branch management
# ---------------------------------------------------------------------------


def _parse_devplan(text: str) -> tuple[str, list[dict]]:
    """Parse a DEVPLAN.md into (constraints_block, list_of_feature_dicts).

    Each feature dict has keys:
        name        str    e.g. "workflow-command"
        branch      str    e.g. "feature/workflow-command"
        depends_on  str
        status      str    e.g. "Not Started"
        block       str    raw markdown of the full feature section
    """
    # Extract the Constraints section (everything between ## Constraints and the next ##)
    constraints_match = re.search(
        r"^## Constraints\s*\n(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL
    )
    constraints_block = constraints_match.group(0).strip() if constraints_match else ""

    features: list[dict] = []

    # Split on ## Feature: headings; keep the heading with the block
    # Pattern: ## Feature: <name> up to next ## heading or end of string
    feature_pattern = re.compile(
        r"^## Feature:\s*(.+?)\s*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
    )
    for m in feature_pattern.finditer(text):
        heading_name = m.group(1).strip()
        body = m.group(2)
        full_block = f"## Feature: {heading_name}\n{body}".rstrip()

        # Extract **Branch:**
        branch_match = re.search(r"\*\*Branch:\*\*\s*`?([^`\n]+)`?", body)
        branch = (
            branch_match.group(1).strip() if branch_match else f"feature/{heading_name}"
        )

        # Extract **Depends on:**
        depends_match = re.search(r"\*\*Depends on:\*\*\s*(.+)", body)
        depends_on = depends_match.group(1).strip() if depends_match else "none"

        # Extract **Status:**
        status_match = re.search(r"\*\*Status:\*\*\s*(.+)", body)
        status = status_match.group(1).strip() if status_match else "Unknown"

        features.append(
            {
                "name": heading_name,
                "branch": branch,
                "depends_on": depends_on,
                "status": status,
                "block": full_block,
            }
        )

    return constraints_block, features


def _update_feature_status(plan_path: Path, feature_name: str, new_status: str) -> None:
    """Rewrite the **Status:** line for a specific feature block in the plan file."""
    text = plan_path.read_text()

    # Find the feature block and replace its Status line
    # We replace the first **Status:** occurrence inside the right feature block
    feature_header = re.escape(f"## Feature: {feature_name}")
    pattern = re.compile(
        rf"(^{feature_header}\s*\n.*?\*\*Status:\*\*\s*)(\S[^\n]*)",
        re.MULTILINE | re.DOTALL,
    )

    def replacer(m: re.Match) -> str:
        return m.group(1) + new_status

    new_text, count = pattern.subn(replacer, text, count=1)
    if count == 0:
        raise ValueError(f"Could not find Status field for feature '{feature_name}'")
    plan_path.write_text(new_text)


def _git_is_dirty(project_dir: Path) -> bool:
    """Return True if the working tree has uncommitted changes."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _git_current_branch(project_dir: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_create_branch(project_dir: Path, branch: str, base: str = "develop") -> None:
    """Create and checkout a new branch off base."""
    subprocess.run(["git", "checkout", base], cwd=project_dir, check=True)
    subprocess.run(["git", "checkout", "-b", branch], cwd=project_dir, check=True)


def _build_ai_prompt(constraints_block: str, feature: dict) -> str:
    """Build the prompt string passed to the AI for a feature."""
    parts = []
    if constraints_block:
        parts.append(constraints_block)
        parts.append("")
    parts.append(feature["block"])
    parts.append("")
    parts.append(
        "Implement this feature exactly as specified above. "
        "Follow all constraints. "
        "Run linting and tests before committing. "
        "When finished, commit all changes with a conventional commit message "
        "(feat: prefix). Do NOT push — the host workflow handles push and PR. "
        "Do NOT include a (#N) PR-number suffix in the commit subject — "
        "GitHub appends one automatically on squash-merge, so including one "
        "here produces a duplicate suffix (e.g. feat: foo (#4) (#4))."
    )
    parts.append("")
    parts.append(
        "After your final commit (or when you cannot proceed), print exactly "
        "this line as your final output (no trailing text on the same line): "
        "<<<DTL:OUTCOME=COMPLETED>>> if you successfully implemented the "
        "feature, or <<<DTL:OUTCOME=FAILED_AI>>> followed by a one-line "
        "reason on the next line if you could not. The host workflow uses "
        "this marker as the authoritative signal of run outcome."
    )
    return "\n".join(parts)


def _setup_workflow_logger(log_path: Optional[Path] = None) -> logging.Logger:
    """Set up a logger that writes to both stderr and a log file."""
    logger = logging.getLogger("dtl.workflow")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)

    if log_path is None:
        xdg_state = os.environ.get("XDG_STATE_HOME", "")
        state_home = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        log_dir = state_home / "dtl"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "workflow.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_path))
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


def _workflow_state_path(project_dir: Path) -> Path:
    """Return path to the workflow skip-state JSON file for a project."""
    xdg_state = os.environ.get("XDG_STATE_HOME", "")
    state_home = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return state_home / "dtl" / f"{project_dir.name}-workflow-state.json"


def _read_workflow_state(project_dir: Path) -> dict:
    """Read existing workflow state from the state file, or return empty dict."""
    state_path = _workflow_state_path(project_dir)
    if state_path.exists():
        try:
            with open(state_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_workflow_state(
    project_dir: Path,
    skip_reason: str,
    consecutive_skips: int,
) -> None:
    """Atomically write workflow skip state for a project (temp + rename)."""
    state_path = _workflow_state_path(project_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    next_retry = (now + datetime.timedelta(seconds=60)).isoformat(timespec="seconds")
    state = {
        "last_check": now.isoformat(timespec="seconds"),
        "last_skip_reason": skip_reason,
        "consecutive_skips": consecutive_skips,
        "next_retry": next_retry,
    }
    fd, tmp = tempfile.mkstemp(dir=state_path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        Path(tmp).rename(state_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _maybe_notify_stalled(
    project_dir: Path,
    skip_reason: str,
    consecutive_skips: int,
    log: logging.Logger,
) -> None:
    """Invoke .ai/notify.py with a stalled message after WORKFLOW_STALL_THRESHOLD skips."""
    if consecutive_skips < WORKFLOW_STALL_THRESHOLD:
        return
    notify_script = project_dir / ".ai" / "notify.py"
    if not notify_script.exists():
        return
    message = (
        f"Workflow stalled for {project_dir.name}: "
        f"{consecutive_skips} consecutive skips ({skip_reason})"
    )
    try:
        subprocess.run(
            [sys.executable, str(notify_script), "1", message],
            capture_output=True,
            timeout=30,
        )
        log.info(
            "[%s] Stall notification sent after %d consecutive skips (%s).",
            project_dir.name,
            consecutive_skips,
            skip_reason,
        )
    except Exception as exc:
        log.info("[%s] Failed to invoke notify.py: %s", project_dir.name, exc)


# ---------------------------------------------------------------------------
# Watchdog helpers
# ---------------------------------------------------------------------------


def _dtl_state_dir() -> Path:
    """Return the XDG state directory used by dtl (~/.local/state/dtl)."""
    xdg_state = os.environ.get("XDG_STATE_HOME", "")
    state_home = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return state_home / "dtl"


def _feature_state_path(project_dir: Path, feature_name: str) -> Path:
    """Return ~/.local/state/dtl/<project>/<feature>.json for per-feature workflow state."""
    return _dtl_state_dir() / project_dir.name / f"{feature_name}.json"


_FEATURE_STATE_DEFAULT: dict = {
    "last_outcome": "",
    "last_run_iso": "",
    "attempts_completed": 0,
    "attempts_interrupted": 0,
    "partial_work_branch": None,
}


def _read_feature_state(project_dir: Path, feature_name: str) -> dict:
    """Read per-feature state file, returning defaults if absent or unreadable."""
    p = _feature_state_path(project_dir, feature_name)
    if p.exists():
        try:
            with open(p) as f:
                data = json.load(f)
            # Merge with defaults so new keys are always present
            return {**_FEATURE_STATE_DEFAULT, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_FEATURE_STATE_DEFAULT)


def _write_feature_state(project_dir: Path, feature_name: str, state: dict) -> None:
    """Atomically write per-feature state (tempfile + rename, mode 0o600)."""
    import tempfile

    p = _feature_state_path(project_dir, feature_name)
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _watchdog_state_path() -> Path:
    """Return path to the watchdog run-state JSON file."""
    return _dtl_state_dir() / "watchdog-state.json"


def _watchdog_read_state() -> dict:
    """Read existing watchdog state, or return empty dict."""
    p = _watchdog_state_path()
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _watchdog_write_state(state: dict) -> None:
    """Atomically write watchdog state (temp + rename)."""
    p = _watchdog_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-watchdog-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
        Path(tmp).rename(p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _watchdog_check_missing_runner(project_dir: Path) -> Optional[str]:
    """Anomaly A: 'dtl workflow run' absent when DEVPLAN has Not Started features."""
    plan_path = project_dir / "docs" / "DEVPLAN.md"
    if not plan_path.exists():
        return None
    _, features = _parse_devplan(plan_path.read_text())
    not_started = [f for f in features if f["status"] == "Not Started"]
    if not not_started:
        return None

    # Primary signal: per-feature state file. If every Not Started feature's
    # last outcome was a human-attention interruption, the workflow halted
    # intentionally — suppressing a spurious anomaly.
    human_attention = (RunOutcome.INTERRUPTED_AUTH, RunOutcome.INTERRUPTED_QUOTA)
    all_intentionally_halted = all(
        _read_feature_state(project_dir, f["name"]).get("last_outcome")
        in human_attention
        for f in not_started
    )
    if all_intentionally_halted:
        return None

    # Fallback: check whether a matching 'dtl workflow run' process exists.
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        project_str = str(project_dir)
        for line in result.stdout.splitlines():
            if "workflow" in line and "run" in line and project_str in line:
                return None  # process found — no anomaly
    except Exception:
        pass

    return (
        f"{project_dir.name}: {len(not_started)} Not Started feature(s) "
        f"but no 'dtl workflow run' process detected"
    )


def _watchdog_check_dirty_age(project_dir: Path) -> Optional[str]:
    """Anomaly B: dirty working tree whose most-recent change is older than WATCHDOG_DIRTY_HOURS."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if not lines:
        return None

    # Find the most-recent mtime among all dirty files.
    latest_mtime = 0.0
    for line in lines:
        # porcelain format: "XY filename" — handle renames ("old -> new")
        fname = line[3:].strip().split(" -> ")[-1].strip('"')
        try:
            mtime = (project_dir / fname).stat().st_mtime
            if mtime > latest_mtime:
                latest_mtime = mtime
        except OSError:
            pass

    if latest_mtime == 0.0:
        return None

    age_hours = (time.time() - latest_mtime) / 3600.0
    if age_hours >= WATCHDOG_DIRTY_HOURS:
        return (
            f"{project_dir.name}: dirty working tree, "
            f"most recent change {age_hours:.0f}h ago "
            f"(threshold: {WATCHDOG_DIRTY_HOURS}h)"
        )
    return None


def _watchdog_check_pr_activity(project_dir: Path) -> Optional[str]:
    """Anomaly C: no open-PR activity for WATCHDOG_PR_IDLE_HOURS when Not Started features exist."""
    plan_path = project_dir / "docs" / "DEVPLAN.md"
    if not plan_path.exists():
        return None
    _, features = _parse_devplan(plan_path.read_text())
    not_started = [f for f in features if f["status"] == "Not Started"]
    if not not_started:
        return None

    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--json", "number,updatedAt", "--state", "open"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None  # gh unavailable or not a GitHub repo — skip
        prs: list[dict] = json.loads(result.stdout or "[]")
    except Exception:
        return None

    if not prs:
        # No open PRs but features are In Progress — flag as possible stall.
        in_progress = [f for f in features if f["status"] == "In Progress"]
        if not in_progress:
            return None
        return f"{project_dir.name}: features 'In Progress' but no open PRs found"

    # Find the most-recently-updated PR and check its age.
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=WATCHDOG_PR_IDLE_HOURS
    )
    most_recent: Optional[datetime.datetime] = None
    for pr in prs:
        updated_str = pr.get("updatedAt", "")
        try:
            updated = datetime.datetime.fromisoformat(
                updated_str.replace("Z", "+00:00")
            )
            if most_recent is None or updated > most_recent:
                most_recent = updated
        except (ValueError, AttributeError):
            pass

    if most_recent is not None and most_recent < cutoff:
        idle_hours = (
            datetime.datetime.now(datetime.timezone.utc) - most_recent
        ).total_seconds() / 3600.0
        return (
            f"{project_dir.name}: no PR activity for {idle_hours:.0f}h "
            f"(threshold: {WATCHDOG_PR_IDLE_HOURS}h) with Not Started features"
        )
    return None


def _watchdog_check_log_growth(prev_state: dict) -> tuple[Optional[str], int]:
    """Anomaly D: dtl log growth > WATCHDOG_LOG_GROWTH_MB_DAY MB/day.

    Returns (anomaly_message_or_None, current_total_bytes).
    """
    state_dir = _dtl_state_dir()
    total_bytes = 0
    if state_dir.exists():
        for entry in state_dir.iterdir():
            if entry.is_file() and entry.suffix in (".log", ".txt", ".json"):
                try:
                    total_bytes += entry.stat().st_size
                except OSError:
                    pass

    anomaly: Optional[str] = None
    prev_bytes: int = prev_state.get("log_size_bytes", 0)
    prev_ts_str: str = prev_state.get("log_size_timestamp", "")
    if prev_ts_str and prev_bytes >= 0:
        try:
            prev_ts = datetime.datetime.fromisoformat(prev_ts_str)
            elapsed_hours = (datetime.datetime.now() - prev_ts).total_seconds() / 3600.0
            if elapsed_hours > 0:
                growth_bytes = max(0, total_bytes - prev_bytes)
                growth_mb_per_day = (growth_bytes / (1024 * 1024)) / (
                    elapsed_hours / 24.0
                )
                if growth_mb_per_day > WATCHDOG_LOG_GROWTH_MB_DAY:
                    anomaly = (
                        f"dtl log growth {growth_mb_per_day:.1f} MB/day "
                        f"exceeds threshold ({WATCHDOG_LOG_GROWTH_MB_DAY} MB/day)"
                    )
        except (ValueError, ZeroDivisionError):
            pass

    return anomaly, total_bytes


def _watchdog_notify_project(
    project_dir: Path,
    anomalies: list[str],
    log: logging.Logger,
) -> None:
    """Invoke a project's .ai/notify.py once with all anomaly details."""
    if not anomalies:
        return
    notify_script = project_dir / ".ai" / "notify.py"
    if not notify_script.exists():
        log.info(
            "[%s] No .ai/notify.py found; skipping notification.", project_dir.name
        )
        return
    message = f"[dtl watchdog] Anomalies detected in {project_dir.name}:\n" + "\n".join(
        f"  • {a}" for a in anomalies
    )
    try:
        subprocess.run(
            [sys.executable, str(notify_script), "1", message],
            capture_output=True,
            timeout=30,
        )
        log.info(
            "[%s] Watchdog notification sent (%d anomaly/anomalies).",
            project_dir.name,
            len(anomalies),
        )
    except Exception as exc:
        log.info("[%s] Failed to invoke notify.py: %s", project_dir.name, exc)


def _make_watchdog_service(projects_str: str) -> str:
    """Generate systemd service unit content for the dtl watchdog."""
    python_exe = sys.executable
    script_path = Path(sys.argv[0]).resolve()
    return textwrap.dedent(
        f"""\
        [Unit]
        Description=dtl workflow watchdog
        After=network.target

        [Service]
        Type=oneshot
        ExecStart={python_exe} {script_path} watchdog check --projects {projects_str}
        StandardOutput=journal
        StandardError=journal
        """
    )


def _make_watchdog_timer(interval_minutes: int) -> str:
    """Generate systemd timer unit content for the dtl watchdog."""
    return textwrap.dedent(
        f"""\
        [Unit]
        Description=dtl workflow watchdog timer

        [Timer]
        OnBootSec=5min
        OnUnitActiveSec={interval_minutes}min
        Unit=dtl-watchdog.service

        [Install]
        WantedBy=timers.target
        """
    )


def _run_lint_and_tests(project_dir: Path) -> tuple[bool, str]:
    """Run lint and tests in the project. Returns (passed, output)."""
    # Detect stack from files present
    lint_cmd = None
    test_cmd = None
    if (project_dir / "pyproject.toml").exists() or (project_dir / "setup.py").exists():
        lint_cmd = ["ruff", "check", "."]
        test_cmd = ["pytest", "--tb=short"]
    elif (project_dir / "package.json").exists():
        lint_cmd = ["npm", "run", "lint"]
        test_cmd = ["npm", "test"]
    elif (project_dir / "go.mod").exists():
        lint_cmd = ["golangci-lint", "run"]
        test_cmd = ["go", "test", "./..."]
    elif (project_dir / "Cargo.toml").exists():
        lint_cmd = ["cargo", "clippy"]
        test_cmd = ["cargo", "test"]

    output_parts = []

    if (project_dir / "pyproject.toml").exists():
        # --break-system-packages bypasses PEP 668 rejection on Debian/Ubuntu system
        # Python. Safe here: the ephemeral USB workstation's system Python is rebuilt
        # weekly, so installing into site-packages has no durable downside. The flag
        # is a no-op on venvs and CI runners that don't enforce PEP 668.
        pip_cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            ".[dev]",
            "--quiet",
            "--break-system-packages",
        ]
        pip_result = subprocess.run(
            pip_cmd, cwd=project_dir, capture_output=True, text=True
        )
        if pip_result.returncode != 0:
            pip_cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-e",
                ".",
                "--quiet",
                "--break-system-packages",
            ]
            pip_result = subprocess.run(
                pip_cmd, cwd=project_dir, capture_output=True, text=True
            )
        output_parts.append(
            f"=== pip install ===\n{pip_result.stdout}{pip_result.stderr}"
        )
        if pip_result.returncode != 0:
            return False, "\n".join(output_parts)

    if lint_cmd:
        result = subprocess.run(
            lint_cmd, cwd=project_dir, capture_output=True, text=True
        )
        output_parts.append(
            f"=== lint ({' '.join(lint_cmd)}) ===\n{result.stdout}{result.stderr}"
        )
        if result.returncode != 0:
            return False, "\n".join(output_parts)

    if test_cmd:
        result = subprocess.run(
            test_cmd, cwd=project_dir, capture_output=True, text=True
        )
        output_parts.append(
            f"=== test ({' '.join(test_cmd)}) ===\n{result.stdout}{result.stderr}"
        )
        if result.returncode != 0:
            return False, "\n".join(output_parts)

    return True, "\n".join(output_parts)


def _git_push_branch(project_dir: Path, branch: str) -> bool:
    """Push the current branch to origin. Returns True on success."""
    result = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _gh_create_pr(
    project_dir: Path, branch: str, title: str, body: str, base: str = "develop"
) -> Optional[str]:
    """Create a PR using gh CLI. Returns the PR URL or None on failure."""
    result = subprocess.run(
        ["gh", "pr", "create", "--title", title, "--body", body, "--base", base],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    # PR may already exist
    if "already exists" in result.stderr:
        view = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "url", "-q", ".url"],
            cwd=project_dir,
            capture_output=True,
            text=True,
        )
        if view.returncode == 0:
            return view.stdout.strip()
    return None


def _gh_enable_auto_merge(project_dir: Path, branch: str) -> bool:
    """Enable auto-merge (squash) on a PR. Returns True on success."""
    result = subprocess.run(
        ["gh", "pr", "merge", branch, "--auto", "--squash"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _gh_pr_state(project_dir: Path, branch: str) -> Optional[str]:
    """Check PR state via gh CLI. Returns 'MERGED', 'OPEN', 'CLOSED', or None."""
    result = subprocess.run(
        ["gh", "pr", "view", branch, "--json", "state", "-q", ".state"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


class RunOutcome:
    """Structured outcomes of an AI run, used by _classify_run.

    String-constants form (not Enum) to keep dtl.py stdlib-friendly and
    let the values pass through subprocess output cleanly.
    """

    COMPLETED = "COMPLETED"
    COMPLETED_TESTS_FAILED = "COMPLETED_TESTS_FAILED"
    COMPLETED_NOTHING_TO_PUSH = "COMPLETED_NOTHING_TO_PUSH"
    INTERRUPTED_QUOTA = "INTERRUPTED_QUOTA"
    INTERRUPTED_AUTH = "INTERRUPTED_AUTH"
    INTERRUPTED_WALL_CLOCK = "INTERRUPTED_WALL_CLOCK"
    INTERRUPTED_NETWORK = "INTERRUPTED_NETWORK"
    FAILED_AI = "FAILED_AI"
    FAILED_INFRA = "FAILED_INFRA"

    ALL = (
        COMPLETED,
        COMPLETED_TESTS_FAILED,
        COMPLETED_NOTHING_TO_PUSH,
        INTERRUPTED_QUOTA,
        INTERRUPTED_AUTH,
        INTERRUPTED_WALL_CLOCK,
        INTERRUPTED_NETWORK,
        FAILED_AI,
        FAILED_INFRA,
    )

    INTERRUPTED = (
        INTERRUPTED_QUOTA,
        INTERRUPTED_AUTH,
        INTERRUPTED_WALL_CLOCK,
        INTERRUPTED_NETWORK,
    )


SENTINEL_RE = re.compile(r"<<<DTL:OUTCOME=([A-Z_]+)>>>")

# Disjoint pattern groups for tail-only fallback classification.
# Patterns are tested in order; the first group with a match wins.
_TAIL_PATTERNS: tuple = (
    (
        RunOutcome.INTERRUPTED_QUOTA,
        (
            "claude usage limit reached",
            "usage limit reached",
            "rate_limit_error",
            "rate limit exceeded",
            "quota exceeded",
        ),
    ),
    (
        RunOutcome.INTERRUPTED_AUTH,
        (
            "please run claude login",
            "expired token",
            "not authenticated",
            "invalid api key",
        ),
    ),
    (
        RunOutcome.INTERRUPTED_NETWORK,
        (
            "connection reset by peer",
            "temporary failure in name resolution",
            "no route to host",
            "connection timed out",
        ),
    ),
)


def _classify_run(exit_code: int, output_lines: list[str]) -> str:
    """Classify a finished AI run as a RunOutcome value.

    Detection order:

    1. Sentinel marker — scan output_lines for ``<<<DTL:OUTCOME=NAME>>>``.
       A recognized sentinel value is authoritative.
    2. Tail-only substring scan (last 50 lines) with disjoint per-outcome
       patterns. Tail-only is deliberate: full-text scans false-positive on
       the AI's own narration of writing auth/quota-related code (see the
       2026-05-14 stranded-research-worker incident).
    3. Exit-code fallback — 0 -> COMPLETED, 124 -> INTERRUPTED_WALL_CLOCK,
       anything else (including 125 retry-cap) -> FAILED_AI.
    """
    for line in reversed(output_lines):
        m = SENTINEL_RE.search(line)
        if m:
            name = m.group(1)
            if name in RunOutcome.ALL:
                return name

    tail = "\n".join(output_lines[-50:]).lower()
    for outcome, patterns in _TAIL_PATTERNS:
        if any(p in tail for p in patterns):
            return outcome

    if exit_code == 0:
        return RunOutcome.COMPLETED
    if exit_code == 124:
        return RunOutcome.INTERRUPTED_WALL_CLOCK
    return RunOutcome.FAILED_AI


def _find_feature_for_branch(features: list[dict], branch: str) -> Optional[dict]:
    """Find the feature dict matching the given branch name."""
    for f in features:
        if f["branch"] == branch:
            return f
    return None


# ---------------------------------------------------------------------------
# Notification hook helpers
# ---------------------------------------------------------------------------


def _load_notify_config() -> Optional[dict]:
    """Load ~/.config/dtl/notify.toml.

    Returns the parsed config dict, or None if the file is absent or unparseable.
    Config is optional — absent means no notifications, log-only.
    """
    config_path = Path.home() / ".config" / "dtl" / "notify.toml"
    if not config_path.exists():
        return None
    try:
        import tomllib  # Python 3.11+ stdlib

        with open(config_path, "rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return None


def _emit_notify_event(
    config: Optional[dict],
    event_type: str,
    payload: dict,
    log: "logging.Logger",
) -> None:
    """POST a structured notification event to the configured HTTP endpoint.

    Never raises; delivery failures are logged but never block the workflow.
    Config is loaded once per workflow run and passed in here.

    Event body shape:
        {event, event_id, timestamp, actions, **payload}
    """
    if not config:
        return

    events_filter = config.get("events", [])
    if events_filter and event_type not in events_filter:
        return

    url = config.get("url", "")
    if not url:
        return

    # Stable event_id for deduplication — survives retries and hub restarts
    id_src = f"{event_type}:{json.dumps(payload, sort_keys=True)}"
    event_id = hashlib.sha256(id_src.encode()).hexdigest()[:16]

    body: dict = {
        "event": event_type,
        "event_id": event_id,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "actions": [],
    }
    body.update(payload)

    headers = {"Content-Type": "application/json"}
    auth_file = config.get("auth_header_file", "")
    if auth_file:
        try:
            auth_value = Path(auth_file).read_text().strip()
            if auth_value:
                headers["Authorization"] = auth_value
        except Exception:
            pass  # auth file missing or unreadable — proceed without auth

    retry_seconds: list = config.get("retry_seconds", [1, 5, 30])
    data = json.dumps(body).encode()

    for attempt, delay in enumerate(retry_seconds):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status < 300:
                    log.info(
                        "Notify: %s delivered (event_id=%s).", event_type, event_id
                    )
                    return
                log.info(
                    "Notify: %s HTTP %d on attempt %d.",
                    event_type,
                    resp.status,
                    attempt + 1,
                )
        except Exception as exc:
            log.info(
                "Notify: attempt %d failed for %s: %s", attempt + 1, event_type, exc
            )
        if attempt < len(retry_seconds) - 1 and delay > 0:
            time.sleep(delay)

    log.info(
        "Notify: giving up on %s after %d attempts.", event_type, len(retry_seconds)
    )


def cmd_workflow_finish(args: argparse.Namespace) -> None:
    """Handle 'dtl workflow finish'."""
    _check_install_freshness(schedule_mode=False)
    plan_path = Path(args.plan).resolve()
    project_dir = Path(args.project).resolve()
    watch = getattr(args, "watch", False)
    log = _setup_workflow_logger()

    if not plan_path.exists():
        print(f"Error: plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    text = plan_path.read_text()
    _, features = _parse_devplan(text)
    branch = _git_current_branch(project_dir)

    feature = _find_feature_for_branch(features, branch)
    if feature is None:
        print(
            f"Error: current branch '{branch}' does not match any feature in the plan.",
            file=sys.stderr,
        )
        sys.exit(1)

    log.info("Finishing feature: %s (branch: %s)", feature["name"], branch)

    # Step 1: lint + test
    log.info("Running lint and tests...")
    passed, test_output = _run_lint_and_tests(project_dir)
    if not passed:
        log.info("Tests or lint FAILED — aborting push.")
        print(test_output, file=sys.stderr)
        _update_feature_status(plan_path, feature["name"], "Failed")
        sys.exit(1)
    log.info("Lint and tests passed.")

    # Step 2: commit any uncommitted work (the AI may have left staged changes)
    if _git_is_dirty(project_dir):
        log.info("Committing uncommitted changes...")
        subprocess.run(
            ["git", "add", "-A"],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"feat: {feature['name']} — automated commit by dtl workflow finish",
            ],
            cwd=project_dir,
            check=True,
            capture_output=True,
        )

    # Step 3: push
    log.info("Pushing %s to origin...", branch)
    if not _git_push_branch(project_dir, branch):
        log.info("Push failed.")
        sys.exit(1)

    # Step 4: create PR
    pr_title = f"feat: {feature['name']}"
    goal_match = re.search(r"### Goal\s*\n(.*?)(?=###|\Z)", feature["block"], re.DOTALL)
    goal_text = goal_match.group(1).strip() if goal_match else feature["name"]
    pr_body = (
        f"## Summary\n\n{goal_text}\n\n"
        f"## Feature spec\n\nFrom `{plan_path.name}`: **{feature['name']}**\n\n"
        f"---\n*Automated by `dtl workflow finish`*"
    )

    log.info("Creating PR...")
    pr_url = _gh_create_pr(project_dir, branch, pr_title, pr_body)
    if pr_url:
        log.info("PR created: %s", pr_url)
        print(f"\nPR: {pr_url}")
        if _gh_enable_auto_merge(project_dir, branch):
            log.info("Auto-merge enabled.")
            print("Auto-merge: enabled (will merge when CI passes)")
        else:
            log.info("Auto-merge not available — manual merge required.")
    else:
        log.info("Failed to create PR — check gh auth status.")
        sys.exit(1)

    # Step 5: update status
    _update_feature_status(plan_path, feature["name"], "PR Open")
    subprocess.run(
        ["git", "add", str(plan_path)],
        cwd=project_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", f"chore: update {feature['name']} status to PR Open"],
        cwd=project_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push"],
        cwd=project_dir,
        capture_output=True,
    )

    if not watch:
        return

    # Step 6: poll for merge
    log.info("Watching for merge (polling every 60s)...")
    while True:
        time.sleep(60)
        state = _gh_pr_state(project_dir, branch)
        if state == "MERGED":
            log.info("PR merged! Updating status.")
            # Checkout develop and pull to get merge
            subprocess.run(
                ["git", "checkout", "develop"], cwd=project_dir, capture_output=True
            )
            subprocess.run(
                ["git", "pull", "origin", "develop"],
                cwd=project_dir,
                capture_output=True,
            )
            _update_feature_status(plan_path, feature["name"], "Merged")
            subprocess.run(
                ["git", "add", str(plan_path)],
                cwd=project_dir,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"chore: update {feature['name']} status to Merged",
                ],
                cwd=project_dir,
                capture_output=True,
            )
            subprocess.run(["git", "push"], cwd=project_dir, capture_output=True)
            break
        elif state == "CLOSED":
            log.info("PR was closed without merging. Stopping.")
            _update_feature_status(plan_path, feature["name"], "Closed")
            sys.exit(1)
        elif state is None:
            log.info("Could not check PR state — will retry.")


def _check_install_freshness(schedule_mode: bool) -> None:
    """Warn (or abort) when the running dtl.py differs from the repo source-of-truth.

    Compares SHA-256 hashes of the running script and ~/Projects/devtools/dtl.py.
    - If both paths are the same file: returns immediately (running from repo).
    - If source-of-truth does not exist: returns silently.
    - On hash match: returns.
    - On hash mismatch:
        schedule_mode=True  → print error to stderr and sys.exit(1)
        schedule_mode=False → print warning to stderr and return.
    """
    import hashlib

    running = Path(sys.argv[0]).resolve()
    source_of_truth = (Path.home() / "Projects" / "devtools" / "dtl.py").resolve()

    # Same file — running directly from the repo, no comparison needed.
    if running == source_of_truth:
        return

    # No repo to compare against.
    if not source_of_truth.exists():
        return

    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    if _sha256(running) == _sha256(source_of_truth):
        return

    install_cmd = "sudo /home/comp/Projects/devtools/install.sh"
    msg = (
        f"dtl install is stale: the running script does not match the repo source.\n"
        f"  running        : {running}\n"
        f"  source-of-truth: {source_of_truth}\n"
        f"  fix            : {install_cmd}"
    )

    if schedule_mode:
        print(f"error: {msg}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"warning: {msg}", file=sys.stderr)


def _preflight_auto_merge(project_dir: Path) -> Optional[bool]:
    """Check whether the GitHub repo for project_dir has allow_auto_merge enabled.

    Returns:
        True  — allow_auto_merge is enabled
        False — allow_auto_merge is explicitly disabled
        None  — check skipped (not a GitHub remote, gh unavailable, or any error)
    """
    # Get the remote URL
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        remote_url = result.stdout.strip()
    except Exception:
        return None

    # Parse owner/name from GitHub remote URLs
    # Supports https://github.com/owner/name(.git) and git@github.com:owner/name(.git)
    import re as _re

    match = _re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    if not match:
        return None  # not a GitHub remote

    owner, name = match.group(1), match.group(2)

    # Query GitHub API
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{name}", "--jq", ".allow_auto_merge"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None  # gh unavailable or API error
        value = result.stdout.strip()
        if value == "true":
            return True
        if value == "false":
            return False
        return None  # unexpected output
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Notify commands
# ---------------------------------------------------------------------------


def cmd_notify_test(args: argparse.Namespace) -> None:
    """Handle 'dtl notify test' — send a synthetic event to verify notification config."""
    cfg = _load_notify_config()
    if not cfg:
        print(
            "No notify config found at ~/.config/dtl/notify.toml\n"
            "Create the file first. See docs/notify.md for the config schema.",
            file=sys.stderr,
        )
        sys.exit(1)

    log = logging.getLogger("dtl.notify.test")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)

    event_type = getattr(args, "event", "idle")
    now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    _synthetic: dict[str, dict] = {
        "ai-failure": {
            "project": "test-project",
            "feature": "test-feature",
            "exit_code": 1,
            "failure_snapshot_path": None,
        },
        "feature-merged": {
            "project": "test-project",
            "feature": "test-feature",
            "pr_number": 42,
        },
        "needs-attention": {
            "project": "test-project",
            "feature": "test-feature",
            "criterion": "- [ ] [HUMAN] Manually verify the output",
        },
        "idle": {"timestamp": now_ts},
    }

    payload = _synthetic.get(event_type, {"timestamp": now_ts})
    url = cfg.get("url", "(no url configured)")
    print(f"Sending synthetic '{event_type}' event to {url} ...")
    _emit_notify_event(cfg, event_type, payload, log)
    print("Done.")


def _handle_interruption(
    project_dir: Path,
    plan_path: Path,
    feature: dict,
    branch: str,
    outcome: str,
    ai_exit_code: int,
    ai_output: str,
    ai_start: float,
    log: "logging.Logger",
    notify_cfg: Optional[dict],
) -> None:
    """Record an interruption: snapshot, notify, restore clean tree on develop.

    Interruptions are NOT failures — the AI was prevented from completing,
    not unable to complete. They never consume the feature's failure budget.
    The feature branch is left intact for forensics; develop is checked out
    cleanly so the next loop iteration can retry the feature without
    tripping the dirty-tree skip.
    """
    snapshot_path: Optional[Path] = None
    try:
        snapshot_path = _write_failure_snapshot(
            project_dir,
            feature,
            branch,
            ai_exit_code,
            time.monotonic() - ai_start,
            ai_output,
            log,
        )
    except Exception as exc:
        log.info("Snapshot write failed: %s", exc)

    # Write per-feature state: interruptions increment attempts_interrupted only,
    # not attempts_completed, so they don't burn the retry budget.
    try:
        _fstate = _read_feature_state(project_dir, feature["name"])
        _fstate["last_outcome"] = outcome
        _fstate["last_run_iso"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        _fstate["attempts_interrupted"] = _fstate["attempts_interrupted"] + 1
        if outcome == RunOutcome.INTERRUPTED_WALL_CLOCK:
            _fstate["partial_work_branch"] = branch
        _write_feature_state(project_dir, feature["name"], _fstate)
    except Exception as exc:
        log.info("Failed to write feature state on interruption: %s", exc)

    _emit_notify_event(
        notify_cfg,
        "ai-interruption",
        {
            "project": project_dir.name,
            "feature": feature["name"],
            "outcome": outcome,
            "exit_code": ai_exit_code,
            "failure_snapshot_path": str(snapshot_path) if snapshot_path else None,
        },
        log,
    )

    # Discard the workflow's pre-run "In Progress" status edit if the AI
    # didn't commit it. Targeted to DEVPLAN.md only — any unexpected dirty
    # files trigger the dirty-tree skip on the next loop instead of being
    # silently erased.
    rel_plan = plan_path.relative_to(project_dir)
    subprocess.run(
        ["git", "checkout", "--", str(rel_plan)],
        cwd=project_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "develop"],
        cwd=project_dir,
        capture_output=True,
    )


def cmd_workflow_run(args: argparse.Namespace) -> None:
    """Handle 'dtl workflow run' — the full autonomous loop."""
    projects = [Path(p.strip()).resolve() for p in args.projects.split(",")]
    schedule_time = getattr(args, "schedule", None)
    max_failures = getattr(args, "max_failures", 3)
    max_wall_clock = getattr(args, "max_wall_clock", 1800)
    max_ai_retries = getattr(args, "max_ai_retries", 3)
    quota_reset_sleep = getattr(args, "quota_reset_sleep", 3600)

    # Resolve log path: explicit --log overrides XDG default
    log_arg = getattr(args, "log", None)
    if log_arg is not None:
        log_path = Path(log_arg).resolve()
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME", "")
        state_home = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        log_path = state_home / "dtl" / f"{projects[0].name}-workflow.log"

    # Reject log paths inside any project directory to prevent dirty-tree skip loop
    for proj in projects:
        try:
            log_path.relative_to(proj)
            print(
                f"error: refusing to write log inside a project directory; "
                f"this would cause the dirty-tree skip loop\n"
                f"  log path : {log_path}\n"
                f"  project  : {proj}",
                file=sys.stderr,
            )
            sys.exit(1)
        except ValueError:
            pass

    log = _setup_workflow_logger(log_path)

    # Load notification config once for the entire run
    notify_cfg = _load_notify_config()
    log.info(
        "Notify config: %s",
        "loaded" if notify_cfg else "absent (notifications disabled)",
    )

    _check_install_freshness(schedule_mode=bool(schedule_time))

    # Preflight: check allow_auto_merge on each project's GitHub repo
    failed_repos: list[str] = []
    for proj in projects:
        result = _preflight_auto_merge(proj)
        if result is None:
            log.info(
                "[%s] Preflight auto-merge check skipped (not a GitHub remote or gh unavailable).",
                proj.name,
            )
        elif result is False:
            failed_repos.append(proj.name)
        # result is True: no action needed

    if failed_repos:
        if schedule_time:
            log.error(
                "Preflight FAILED: allow_auto_merge is not enabled on: %s",
                ", ".join(failed_repos),
            )
            log.error(
                "A scheduled run cannot proceed — without auto-merge, PRs stall "
                "overnight with no human available to merge them."
            )
            log.error(
                "Recommended fixes:\n"
                "  • Upgrade to GitHub Pro to enable auto-merge on private repos.\n"
                "  • Or run without --schedule (interactive mode) and merge PRs "
                "manually via the GitHub app."
            )
            sys.exit(1)
        else:
            log.warning(
                "WARNING: allow_auto_merge is not enabled on: %s. "
                "PRs require manual merge via the GitHub app.",
                ", ".join(failed_repos),
            )

    # Wait for scheduled time if specified
    if schedule_time:
        now = datetime.datetime.now()
        hour, minute = map(int, schedule_time.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        log.info(
            "Scheduled start at %s (waiting %.0f minutes)...",
            schedule_time,
            wait_secs / 60,
        )
        time.sleep(wait_secs)

        # Spawn a fresh child process so it reads the current on-disk dtl.py
        log.info("Spawning fresh dtl child process (--schedule satisfied).")
        child_argv = [
            sys.executable,
            sys.argv[0],
            "workflow",
            "run",
            "--projects",
            args.projects,
            "--max-failures",
            str(max_failures),
            "--max-wall-clock",
            str(max_wall_clock),
            "--max-ai-retries",
            str(max_ai_retries),
        ]
        if log_arg is not None:
            child_argv += ["--log", log_arg]
        result = subprocess.run(child_argv)
        sys.exit(result.returncode)

    log.info("=== dtl workflow run starting ===")
    log.info("Projects: %s", ", ".join(str(p) for p in projects))

    # Per-project provider chain index.  Incremented on INTERRUPTED_QUOTA to
    # rotate to the next provider; reset to 0 after chain is exhausted.
    chain_indices: dict[Path, int] = {}

    while True:
        any_work_done = False

        for project_dir in projects:
            plan_path = project_dir / "docs" / "DEVPLAN.md"
            if not plan_path.exists():
                log.info("[%s] No DEVPLAN.md found, skipping.", project_dir.name)
                continue

            text = plan_path.read_text()
            _, features = _parse_devplan(text)

            # Find next unstarted feature
            next_feature = None
            for f in features:
                if f["status"] == "Not Started":
                    fstate = _read_feature_state(project_dir, f["name"])
                    if fstate["attempts_completed"] >= max_failures:
                        log.info(
                            "[%s] Skipping %s (failed %d times).",
                            project_dir.name,
                            f["name"],
                            max_failures,
                        )
                        _update_feature_status(plan_path, f["name"], "Failed")
                        continue
                    next_feature = f
                    break

            if next_feature is None:
                log.info("[%s] No unstarted features remaining.", project_dir.name)
                continue

            branch = next_feature["branch"]
            log.info(
                "[%s] Starting feature: %s", project_dir.name, next_feature["name"]
            )

            # Ensure clean tree and on develop
            if _git_is_dirty(project_dir):
                log.info("[%s] Working tree is dirty — skipping.", project_dir.name)
                _reason = "dirty_tree"
                _prev = _read_workflow_state(project_dir)
                _skip_count = (
                    _prev.get("consecutive_skips", 0) + 1
                    if _prev.get("last_skip_reason") == _reason
                    else 1
                )
                _write_workflow_state(project_dir, _reason, _skip_count)
                _maybe_notify_stalled(project_dir, _reason, _skip_count, log)
                continue

            subprocess.run(
                ["git", "checkout", "develop"],
                cwd=project_dir,
                capture_output=True,
            )
            subprocess.run(
                ["git", "pull", "origin", "develop"],
                cwd=project_dir,
                capture_output=True,
            )

            # Create branch
            try:
                _git_create_branch(project_dir, branch, base="develop")
            except subprocess.CalledProcessError:
                log.info("[%s] Failed to create branch %s.", project_dir.name, branch)
                _fstate = _read_feature_state(project_dir, next_feature["name"])
                _fstate["last_outcome"] = RunOutcome.FAILED_INFRA
                _fstate["last_run_iso"] = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                _fstate["attempts_completed"] = _fstate["attempts_completed"] + 1
                _write_feature_state(project_dir, next_feature["name"], _fstate)
                _reason = "branch_create_failed"
                _prev = _read_workflow_state(project_dir)
                _skip_count = (
                    _prev.get("consecutive_skips", 0) + 1
                    if _prev.get("last_skip_reason") == _reason
                    else 1
                )
                _write_workflow_state(project_dir, _reason, _skip_count)
                _maybe_notify_stalled(project_dir, _reason, _skip_count, log)
                continue

            # All skip gates passed — count this project as having work
            any_work_done = True
            _write_workflow_state(project_dir, "", 0)

            # Update status
            _update_feature_status(plan_path, next_feature["name"], "In Progress")

            # Build prompt and run AI
            constraints_block, _ = _parse_devplan(plan_path.read_text())
            prompt = _build_ai_prompt(constraints_block, next_feature)

            log.info(
                "[%s] Launching AI for %s...", project_dir.name, next_feature["name"]
            )

            ai_dir = project_dir / ".ai"
            ai_config_path = ai_dir / "config.json"
            ai_exit_code = 1
            ai_output = ""
            ai_start = time.monotonic()

            if ai_config_path.exists():
                # Resolve the active provider from the chain.
                _chain = _resolve_provider_chain(project_dir)
                _chain_idx = chain_indices.get(project_dir, 0)
                _active_provider = _chain[_chain_idx]
                log.info(
                    "[%s] Provider chain: %s (using index %d: %s)",
                    project_dir.name,
                    _chain,
                    _chain_idx,
                    _active_provider,
                )
                # Use dtl's ai_run mechanism via subprocess to isolate failures
                result = subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "ai",
                        "run",
                        "--project",
                        str(project_dir),
                        "--prompt",
                        prompt,
                        "--feature-name",
                        next_feature["name"],
                        "--max-wall-clock",
                        str(max_wall_clock),
                        "--max-ai-retries",
                        str(max_ai_retries),
                        "--provider",
                        _active_provider,
                    ],
                    capture_output=True,
                    text=True,
                    env={**os.environ},
                )
                ai_exit_code = result.returncode
                ai_output = result.stdout + result.stderr
            else:
                log.info(
                    "[%s] No .ai/config.json — running claude directly.",
                    project_dir.name,
                )
                try:
                    result = subprocess.run(
                        ["claude", "--print", "-p", prompt],
                        cwd=project_dir,
                        capture_output=True,
                        text=True,
                        timeout=max_wall_clock if max_wall_clock else None,
                        env={**os.environ},
                    )
                    ai_exit_code = result.returncode
                    ai_output = result.stdout + result.stderr
                except subprocess.TimeoutExpired:
                    log.info(
                        "[%s] AI wall-clock timeout for %s.",
                        project_dir.name,
                        next_feature["name"],
                    )
                    ai_exit_code = 124
                    ai_output = ""

            # Check for auth failure
            outcome = _classify_run(ai_exit_code, ai_output.splitlines())
            log.info("[%s] AI run outcome: %s", project_dir.name, outcome)

            if outcome in RunOutcome.INTERRUPTED:
                _handle_interruption(
                    project_dir,
                    plan_path,
                    next_feature,
                    branch,
                    outcome,
                    ai_exit_code,
                    ai_output,
                    ai_start,
                    log,
                    notify_cfg,
                )
                if outcome == RunOutcome.INTERRUPTED_AUTH:
                    log.info(
                        "[%s] Auth interruption — pausing workflow cleanly.",
                        project_dir.name,
                    )
                    sys.exit(0)
                elif outcome == RunOutcome.INTERRUPTED_QUOTA:
                    _chain = _resolve_provider_chain(project_dir)
                    _cur_idx = chain_indices.get(project_dir, 0)
                    _next_idx = _cur_idx + 1
                    if _next_idx < len(_chain):
                        log.info(
                            "[%s] Quota hit on '%s'; rotating to '%s' "
                            "(chain index %d → %d of %d).",
                            project_dir.name,
                            _chain[_cur_idx],
                            _chain[_next_idx],
                            _cur_idx,
                            _next_idx,
                            len(_chain) - 1,
                        )
                        chain_indices[project_dir] = _next_idx
                        any_work_done = True  # Don't sleep between chain retries
                    else:
                        log.info(
                            "[%s] Quota hit on '%s'; provider chain exhausted. "
                            "Sleeping %ds before retrying from chain start.",
                            project_dir.name,
                            _chain[_cur_idx],
                            quota_reset_sleep,
                        )
                        chain_indices[project_dir] = 0
                        time.sleep(quota_reset_sleep)
                continue

            if ai_exit_code != 0:
                log.info(
                    "[%s] AI exited with code %d for %s.",
                    project_dir.name,
                    ai_exit_code,
                    next_feature["name"],
                )
                _snapshot_path: Optional[Path] = None
                try:
                    _snapshot_path = _write_failure_snapshot(
                        project_dir,
                        next_feature,
                        branch,
                        ai_exit_code,
                        time.monotonic() - ai_start,
                        ai_output,
                        log,
                    )
                except Exception as _snap_exc:
                    log.info("Unexpected error writing failure snapshot: %s", _snap_exc)
                _emit_notify_event(
                    notify_cfg,
                    "ai-failure",
                    {
                        "project": project_dir.name,
                        "feature": next_feature["name"],
                        "exit_code": ai_exit_code,
                        "failure_snapshot_path": str(_snapshot_path)
                        if _snapshot_path
                        else None,
                    },
                    log,
                )
                # Bail-out codes (wall-clock or retry-cap) pin the failure count
                # so the next loop iteration marks the feature as Failed immediately.
                _fstate = _read_feature_state(project_dir, next_feature["name"])
                _fstate["last_outcome"] = (
                    outcome if outcome != RunOutcome.COMPLETED else RunOutcome.FAILED_AI
                )
                _fstate["last_run_iso"] = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                if ai_exit_code in (124, 125):
                    log.info(
                        "[%s] Bail-out limit hit for %s — marking as permanently failed.",
                        project_dir.name,
                        next_feature["name"],
                    )
                    _fstate["attempts_completed"] = max_failures
                else:
                    _fstate["attempts_completed"] = _fstate["attempts_completed"] + 1
                _write_feature_state(project_dir, next_feature["name"], _fstate)
                _update_feature_status(plan_path, next_feature["name"], "Not Started")
                continue

            # AI succeeded — now finish: lint, test, push, PR
            log.info("[%s] AI done. Running finish...", project_dir.name)

            passed, test_output = _run_lint_and_tests(project_dir)
            if not passed:
                log.info(
                    "[%s] Lint/tests failed after AI. Output:\n%s",
                    project_dir.name,
                    test_output,
                )
                _fstate = _read_feature_state(project_dir, next_feature["name"])
                _fstate["last_outcome"] = RunOutcome.FAILED_AI
                _fstate["last_run_iso"] = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                _fstate["attempts_completed"] = _fstate["attempts_completed"] + 1
                _write_feature_state(project_dir, next_feature["name"], _fstate)
                _update_feature_status(plan_path, next_feature["name"], "Not Started")
                # Return to develop
                subprocess.run(
                    ["git", "checkout", "develop"],
                    cwd=project_dir,
                    capture_output=True,
                )
                continue

            # Emit needs-attention for any [HUMAN] acceptance criteria
            _human_criteria = [
                line.strip()
                for line in next_feature["block"].splitlines()
                if "[HUMAN]" in line and line.strip().startswith("- [")
            ]
            for _criterion in _human_criteria:
                _emit_notify_event(
                    notify_cfg,
                    "needs-attention",
                    {
                        "project": project_dir.name,
                        "feature": next_feature["name"],
                        "criterion": _criterion,
                    },
                    log,
                )
            if _human_criteria:
                log.info(
                    "[%s] %d [HUMAN] criterion/criteria — needs-attention event(s) emitted.",
                    project_dir.name,
                    len(_human_criteria),
                )

            # Commit any remaining changes
            if _git_is_dirty(project_dir):
                subprocess.run(
                    ["git", "add", "-A"], cwd=project_dir, capture_output=True
                )
                subprocess.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        f"feat: {next_feature['name']} — automated commit by dtl workflow run",
                    ],
                    cwd=project_dir,
                    capture_output=True,
                )

            # Push
            if not _git_push_branch(project_dir, branch):
                log.info("[%s] Push failed for %s.", project_dir.name, branch)
                _fstate = _read_feature_state(project_dir, next_feature["name"])
                _fstate["last_outcome"] = RunOutcome.FAILED_INFRA
                _fstate["last_run_iso"] = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                _fstate["attempts_completed"] = _fstate["attempts_completed"] + 1
                _write_feature_state(project_dir, next_feature["name"], _fstate)
                continue

            # Create PR
            pr_title = f"feat: {next_feature['name']}"
            goal_match = re.search(
                r"### Goal\s*\n(.*?)(?=###|\Z)", next_feature["block"], re.DOTALL
            )
            goal_text = (
                goal_match.group(1).strip() if goal_match else next_feature["name"]
            )
            pr_body = (
                f"## Summary\n\n{goal_text}\n\n---\n*Automated by `dtl workflow run`*"
            )
            pr_url = _gh_create_pr(project_dir, branch, pr_title, pr_body)
            if pr_url:
                log.info("[%s] PR created: %s", project_dir.name, pr_url)
                if _gh_enable_auto_merge(project_dir, branch):
                    log.info("[%s] Auto-merge enabled.", project_dir.name)
                else:
                    log.info(
                        "[%s] Auto-merge not available — manual merge required.",
                        project_dir.name,
                    )
            else:
                log.info("[%s] Failed to create PR.", project_dir.name)
                continue

            _update_feature_status(plan_path, next_feature["name"], "PR Open")
            subprocess.run(
                ["git", "add", str(plan_path)],
                cwd=project_dir,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"chore: update {next_feature['name']} status to PR Open",
                ],
                cwd=project_dir,
                capture_output=True,
            )
            subprocess.run(["git", "push"], cwd=project_dir, capture_output=True)

            # Poll for merge
            log.info("[%s] Waiting for PR merge...", project_dir.name)
            while True:
                time.sleep(60)
                state = _gh_pr_state(project_dir, branch)
                if state == "MERGED":
                    log.info(
                        "[%s] PR merged for %s!", project_dir.name, next_feature["name"]
                    )
                    subprocess.run(
                        ["git", "checkout", "develop"],
                        cwd=project_dir,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "pull", "origin", "develop"],
                        cwd=project_dir,
                        capture_output=True,
                    )
                    _update_feature_status(plan_path, next_feature["name"], "Merged")
                    subprocess.run(
                        ["git", "add", str(plan_path)],
                        cwd=project_dir,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git",
                            "commit",
                            "-m",
                            f"chore: update {next_feature['name']} status to Merged",
                        ],
                        cwd=project_dir,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "push"],
                        cwd=project_dir,
                        capture_output=True,
                    )
                    # Reset per-feature state on success
                    _fstate = _read_feature_state(project_dir, next_feature["name"])
                    _fstate["last_outcome"] = RunOutcome.COMPLETED
                    _fstate["last_run_iso"] = datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                    _fstate["attempts_completed"] = 0
                    _fstate["partial_work_branch"] = None
                    _write_feature_state(project_dir, next_feature["name"], _fstate)
                    # Emit feature-merged event
                    _pr_num_match = re.search(r"/pull/(\d+)", pr_url or "")
                    _emit_notify_event(
                        notify_cfg,
                        "feature-merged",
                        {
                            "project": project_dir.name,
                            "feature": next_feature["name"],
                            "pr_number": int(_pr_num_match.group(1))
                            if _pr_num_match
                            else None,
                        },
                        log,
                    )
                    break
                elif state == "CLOSED":
                    log.info(
                        "[%s] PR closed without merge for %s.",
                        project_dir.name,
                        next_feature["name"],
                    )
                    _update_feature_status(plan_path, next_feature["name"], "Closed")
                    break

        if not any_work_done:
            log.info("=== All projects complete. Exiting. ===")
            _emit_notify_event(
                notify_cfg,
                "idle",
                {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()},
                log,
            )
            break

        # Floor sleep — belt-and-suspenders to prevent spin if any_work_done
        # logic is ever wrong (e.g. all projects skipped but flag was set).
        time.sleep(60)


# ---------------------------------------------------------------------------
# Watchdog commands
# ---------------------------------------------------------------------------


def cmd_watchdog_install(args: argparse.Namespace) -> None:
    """Handle 'dtl watchdog install'."""
    projects = [str(Path(p).resolve()) for p in args.projects.split(",")]
    projects_str = ",".join(projects)
    interval_minutes: int = args.interval

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)

    service_path = unit_dir / "dtl-watchdog.service"
    timer_path = unit_dir / "dtl-watchdog.timer"

    service_path.write_text(_make_watchdog_service(projects_str))
    timer_path.write_text(_make_watchdog_timer(interval_minutes))

    print(f"Wrote {service_path}")
    print(f"Wrote {timer_path}")
    print()
    print("Activate with:")
    print("  systemctl --user daemon-reload")
    print("  systemctl --user enable --now dtl-watchdog.timer")


def cmd_watchdog_check(args: argparse.Namespace) -> None:
    """Handle 'dtl watchdog check'."""
    project_dirs = [Path(p).resolve() for p in args.projects.split(",")]

    log = logging.getLogger("dtl.watchdog")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)

    prev_state = _watchdog_read_state()
    now_str = datetime.datetime.now().isoformat(timespec="seconds")
    all_anomalies: list[str] = []

    # Check D: log growth — evaluated once, globally.
    log_anomaly, current_log_bytes = _watchdog_check_log_growth(prev_state)
    if log_anomaly:
        all_anomalies.append(log_anomaly)
        log.info("ANOMALY D: %s", log_anomaly)

    # Per-project checks.
    for project_dir in project_dirs:
        if not project_dir.exists():
            log.info("Project dir not found: %s — skipping.", project_dir)
            continue

        project_anomalies: list[str] = []

        anomaly_a = _watchdog_check_missing_runner(project_dir)
        if anomaly_a:
            project_anomalies.append(anomaly_a)
            log.info("ANOMALY A: %s", anomaly_a)

        anomaly_b = _watchdog_check_dirty_age(project_dir)
        if anomaly_b:
            project_anomalies.append(anomaly_b)
            log.info("ANOMALY B: %s", anomaly_b)

        anomaly_c = _watchdog_check_pr_activity(project_dir)
        if anomaly_c:
            project_anomalies.append(anomaly_c)
            log.info("ANOMALY C: %s", anomaly_c)

        if project_anomalies:
            all_anomalies.extend(project_anomalies)
            _watchdog_notify_project(project_dir, project_anomalies, log)

    if all_anomalies:
        print(f"FAIL — {len(all_anomalies)} anomaly/anomalies detected:")
        for a in all_anomalies:
            print(f"  • {a}")
    else:
        print("PASS — no anomalies detected.")

    _watchdog_write_state(
        {
            "last_run": now_str,
            "last_result": "FAIL" if all_anomalies else "PASS",
            "last_anomalies": all_anomalies,
            "log_size_bytes": current_log_bytes,
            "log_size_timestamp": now_str,
        }
    )


def cmd_watchdog_status(args: argparse.Namespace) -> None:
    """Handle 'dtl watchdog status'."""
    state = _watchdog_read_state()
    if not state:
        print("No watchdog state found. Run 'dtl watchdog check' first.")
        return

    print(f"Last run:    {state.get('last_run', 'unknown')}")
    print(f"Last result: {state.get('last_result', 'unknown')}")
    anomalies = state.get("last_anomalies", [])
    if anomalies:
        print("Anomalies:")
        for a in anomalies:
            print(f"  • {a}")

    # Attempt to show next scheduled run from systemd.
    try:
        result = subprocess.run(
            [
                "systemctl",
                "--user",
                "list-timers",
                "dtl-watchdog.timer",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "dtl-watchdog" in line:
                    print(f"\nNext scheduled run (systemd):\n  {line.strip()}")
                    break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Workflow commands
# ---------------------------------------------------------------------------


def cmd_workflow_list(args: argparse.Namespace) -> None:
    """Handle 'dtl workflow list'."""
    _check_install_freshness(schedule_mode=False)
    plan_path = Path(args.plan).resolve()
    if not plan_path.exists():
        print(f"Error: plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    _, features = _parse_devplan(plan_path.read_text())

    if not features:
        print("No features found in plan.")
        return

    name_width = max(len(f["name"]) for f in features)
    print(f"\n{'Feature':<{name_width}}  {'Status':<14}  Branch")
    print("-" * (name_width + 36))
    for f in features:
        print(f"{f['name']:<{name_width}}  {f['status']:<14}  {f['branch']}")
    print()


def cmd_workflow_status(args: argparse.Namespace) -> None:
    """Handle 'dtl workflow status'."""
    _check_install_freshness(schedule_mode=False)
    plan_path = Path(args.plan).resolve()
    if not plan_path.exists():
        print(f"Error: plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    project_dir = plan_path.parent.parent

    _, features = _parse_devplan(plan_path.read_text())

    # Workflow skip state (lifecycle)
    state_path = _workflow_state_path(project_dir)
    if state_path.exists():
        with open(state_path) as f:
            wf_state = json.load(f)
        print(f"Project:           {project_dir.name}")
        print(f"Last skip reason:  {wf_state.get('last_skip_reason', 'none')}")
        print(f"Consecutive skips: {wf_state.get('consecutive_skips', 0)}")
    else:
        print(f"Project:           {project_dir.name}")
        print("Workflow state:    (no run state recorded yet)")

    print()
    print(
        f"{'Feature':<30}  {'DEVPLAN':<14}  {'Last outcome':<24}  {'Done':<4}  {'Int':<4}  Partial branch"
    )
    print("-" * 100)
    for f in features:
        fstate = _read_feature_state(project_dir, f["name"])
        partial = fstate.get("partial_work_branch") or ""
        print(
            f"{f['name']:<30}  {f['status']:<14}  "
            f"{fstate.get('last_outcome', ''):<24}  "
            f"{fstate.get('attempts_completed', 0):<4}  "
            f"{fstate.get('attempts_interrupted', 0):<4}  "
            f"{partial}"
        )
    print()
    latest_snapshot = _latest_failure_snapshot(project_dir)
    if latest_snapshot:
        print(f"Last failure snapshot: {latest_snapshot}")


def cmd_workflow_next(args: argparse.Namespace) -> None:
    """Handle 'dtl workflow next'."""
    _check_install_freshness(schedule_mode=False)
    plan_path = Path(args.plan).resolve()
    project_dir = (
        Path(args.project).resolve()
        if hasattr(args, "project") and args.project
        else plan_path.parent.parent
    )

    if not plan_path.exists():
        print(f"Error: plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    text = plan_path.read_text()
    constraints_block, features = _parse_devplan(text)

    if not features:
        print("No features found in plan.", file=sys.stderr)
        sys.exit(1)

    # Find next unstarted feature
    next_feature: Optional[dict] = None
    for f in features:
        if f["status"] == "Not Started":
            next_feature = f
            break

    if next_feature is None:
        print("All features are done (no 'Not Started' features remaining).")
        return

    # Guard: dirty working tree
    if _git_is_dirty(project_dir):
        print(
            "Error: working tree is dirty. Commit or stash changes before starting a feature.",
            file=sys.stderr,
        )
        sys.exit(1)

    branch = next_feature["branch"]
    print(f"[dtl workflow] Next feature: {next_feature['name']}")
    print(f"[dtl workflow] Creating branch {branch!r} off develop...")

    _git_create_branch(project_dir, branch, base="develop")

    print(f"[dtl workflow] Updating status to 'In Progress' in {plan_path.name}...")
    _update_feature_status(plan_path, next_feature["name"], "In Progress")

    prompt = _build_ai_prompt(constraints_block, next_feature)

    print("[dtl workflow] Launching AI with feature spec...")
    print()
    ai_run(project_dir, prompt)


# ---------------------------------------------------------------------------
# PM commands
# ---------------------------------------------------------------------------


def _pm_source_dir() -> Path:
    """Return the pm/ directory adjacent to dtl.py (dev clone or installed)."""
    candidate = Path(__file__).parent / "pm"
    if candidate.is_dir():
        return candidate
    installed = Path("/opt/devtools/pm")
    if installed.is_dir():
        return installed
    raise FileNotFoundError(
        f"pm/ source not found next to {__file__} or at /opt/devtools/pm"
    )


def cmd_pm_install(args: argparse.Namespace) -> None:
    """Handle 'dtl pm install'."""
    workspace = Path(args.workspace).expanduser().resolve()
    dry_run: bool = args.dry_run

    try:
        pm_src = _pm_source_dir()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    claude_dir = workspace / ".claude"
    preserve = {
        claude_dir / "settings.local.json",
        claude_dir / "HANDOFF.md",
    }

    def _log(msg: str) -> None:
        print(f"[dtl pm install] {msg}")

    def _cp(src: Path, dst: Path) -> None:
        if dst in preserve and dst.exists():
            _log(f"  preserve  {dst.relative_to(workspace)}")
            return
        if dry_run:
            _log(f"  [dry-run] copy {src.name} -> {dst.relative_to(workspace)}")
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        _log(f"  copy      {dst.relative_to(workspace)}")

    _log(f"source:    {pm_src}")
    _log(f"workspace: {workspace}")

    if not dry_run:
        for subdir in ("rules", "commands", "scripts"):
            (claude_dir / subdir).mkdir(parents=True, exist_ok=True)

    # workspace/CLAUDE.md
    _cp(pm_src / "CLAUDE.md", workspace / "CLAUDE.md")

    # .claude/settings.json and PROJECTS.md
    _cp(pm_src / "settings.json", claude_dir / "settings.json")
    _cp(pm_src / "PROJECTS.md", claude_dir / "PROJECTS.md")

    # subdirs: rules, commands, scripts
    for subdir in ("rules", "commands", "scripts"):
        src_subdir = pm_src / subdir
        if not src_subdir.is_dir():
            continue
        for src_file in sorted(src_subdir.iterdir()):
            if not src_file.is_file():
                continue
            _cp(src_file, claude_dir / subdir / src_file.name)

    # chmod +x scripts
    if not dry_run:
        scripts_dir = claude_dir / "scripts"
        if scripts_dir.is_dir():
            for script in scripts_dir.iterdir():
                if script.suffix == ".sh":
                    script.chmod(script.stat().st_mode | 0o111)

    preserved_present = sorted(p for p in preserve if p.exists())
    if preserved_present:
        names = ", ".join(str(p.relative_to(workspace)) for p in preserved_present)
        _log(f"Preserved:  {names}")
    _log("Done.")


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="dtl",
        description="Multi-stack project scaffolder for secure containerized development.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # -- new --
    new_parser = subparsers.add_parser(
        "new",
        help="Scaffold a new project",
    )
    new_parser.add_argument(
        "--name",
        required=True,
        help="Project name (used as directory name)",
    )
    new_parser.add_argument(
        "--stack",
        required=True,
        choices=sorted(STACKS.keys()),
        help="Language/runtime stack",
    )
    new_parser.add_argument(
        "--services",
        default="",
        help="Comma-separated optional services (e.g. postgres,redis)",
    )
    new_parser.add_argument(
        "--dir",
        default=".",
        help="Parent directory for the project (default: current directory)",
    )
    new_parser.add_argument(
        "--ai",
        default="",
        help="Comma-separated AI providers (e.g. claude,ollama,openclaw)",
    )
    new_parser.add_argument(
        "--mode",
        "--isolation",
        dest="mode",
        default="docker",
        choices=AI_MODES,
        help="AI isolation mode: docker (lightweight) or vm (QEMU/KVM). Default: docker",
    )
    new_parser.add_argument(
        "--model",
        default=None,
        help="AI model (e.g. opus, sonnet, haiku for Claude)",
    )
    new_parser.add_argument(
        "--template",
        default="general",
        choices=sorted(CLAUDE_MD_TEMPLATES.keys()),
        help="CLAUDE.md template category (default: general)",
    )
    new_parser.set_defaults(func=cmd_new)

    # -- list-stacks --
    list_parser = subparsers.add_parser(
        "list-stacks",
        help="Show available stacks, services, and AI providers",
    )
    list_parser.set_defaults(func=cmd_list_stacks)

    # -- add-mcp --
    mcp_parser = subparsers.add_parser(
        "add-mcp",
        help="Add an isolated MCP server to an existing AI project",
    )
    mcp_parser.add_argument(
        "--name",
        required=True,
        help="MCP server name (e.g. filesystem, github). Known: "
        + ", ".join(sorted(MCP_KNOWN_PACKAGES)),
    )
    mcp_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory (default: current directory)",
    )
    mcp_parser.add_argument(
        "--project-path",
        default="/workspace",
        help="Mount path for project files inside the container (default: /workspace)",
    )
    mcp_parser.set_defaults(func=cmd_add_mcp)

    # -- ai (subcommand group) --
    ai_parser = subparsers.add_parser(
        "ai",
        help="Manage AI providers for projects",
    )
    ai_subparsers = ai_parser.add_subparsers(dest="ai_command")

    # -- ai attach --
    ai_attach_parser = ai_subparsers.add_parser(
        "attach",
        help="Attach an AI provider to an existing project",
    )
    ai_attach_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory",
    )
    ai_attach_parser.add_argument(
        "--provider",
        required=True,
        choices=sorted(AI_PROVIDERS_CONFIG.keys()),
        help="AI provider to attach",
    )
    ai_attach_parser.add_argument(
        "--mode",
        "--isolation",
        dest="mode",
        default="docker",
        choices=AI_MODES,
        help="Isolation mode: docker or vm (default: docker)",
    )
    ai_attach_parser.add_argument(
        "--model",
        default=None,
        help="Model name (e.g. opus, sonnet, haiku)",
    )
    ai_attach_parser.add_argument(
        "--key-source",
        default="env",
        help="API key source: env (default)",
    )
    ai_attach_parser.add_argument(
        "--scaffold-ci",
        action="store_true",
        default=False,
        help="Write a standard .github/workflows/ci.yml if missing",
    )
    ai_attach_parser.add_argument(
        "--no-ci",
        action="store_true",
        default=False,
        help="Skip the CI workflow requirement check (not recommended)",
    )
    ai_attach_parser.set_defaults(func=cmd_ai_attach)

    # -- ai detach --
    ai_detach_parser = ai_subparsers.add_parser(
        "detach",
        help="Remove AI provider from a project",
    )
    ai_detach_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory",
    )
    ai_detach_parser.set_defaults(func=cmd_ai_detach)

    # -- ai start --
    ai_start_parser = ai_subparsers.add_parser(
        "start",
        help="Start AI containers/VM for a project",
    )
    ai_start_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory",
    )
    ai_start_parser.add_argument(
        "--isolation",
        default=None,
        choices=AI_MODES,
        help="Override isolation mode from config: docker or vm",
    )
    ai_start_parser.set_defaults(func=cmd_ai_start)

    # -- ai stop --
    ai_stop_parser = ai_subparsers.add_parser(
        "stop",
        help="Stop AI containers/VM for a project",
    )
    ai_stop_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory",
    )
    ai_stop_parser.set_defaults(func=cmd_ai_stop)

    # -- ai status --
    ai_status_parser = ai_subparsers.add_parser(
        "status",
        help="Show AI status for a project",
    )
    ai_status_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory",
    )
    ai_status_parser.set_defaults(func=cmd_ai_status)

    # -- ai run --
    ai_run_parser = ai_subparsers.add_parser(
        "run",
        help="Run an autonomous AI session with a prompt",
    )
    ai_run_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory",
    )
    ai_run_parser.add_argument(
        "--prompt",
        required=True,
        help="The prompt/task for the AI to execute",
    )
    ai_run_parser.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Continue the previous conversation instead of starting fresh",
    )
    ai_run_parser.add_argument(
        "--max-wall-clock",
        dest="max_wall_clock",
        type=int,
        default=1800,
        metavar="SECONDS",
        help="Hard kill the AI session after this many seconds (default: 1800 = 30 min)",
    )
    ai_run_parser.add_argument(
        "--max-ai-retries",
        dest="max_ai_retries",
        type=int,
        default=3,
        metavar="N",
        help=(
            "Kill the session after N detected retry loops in AI output "
            "(default: 3; 0 = disabled)"
        ),
    )
    ai_run_parser.add_argument(
        "--feature-name",
        dest="feature_name",
        default="",
        help="Feature name to include in FAILURE-REPORT.md (set by workflow run)",
    )
    ai_run_parser.add_argument(
        "--provider",
        default=None,
        help=(
            "Override the AI provider for this run (e.g. claude, ollama, openclaw). "
            "Defaults to the provider configured in .ai/config.json."
        ),
    )
    ai_run_parser.add_argument(
        "--provider-chain",
        dest="provider_chain",
        default=None,
        metavar="CHAIN",
        help=(
            "Comma-separated list of providers to try in order "
            "(e.g. claude,ollama). The first provider in the chain is used; "
            "rotation on quota exhaustion is handled by 'dtl workflow run'."
        ),
    )
    ai_run_parser.set_defaults(func=cmd_ai_run)

    # -- ai config-notify --
    ai_notify_parser = ai_subparsers.add_parser(
        "config-notify",
        help="Configure Telegram notifications for autonomous mode",
    )
    ai_notify_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory",
    )
    ai_notify_parser.add_argument(
        "--telegram-token",
        required=True,
        help="Telegram bot token (from @BotFather)",
    )
    ai_notify_parser.add_argument(
        "--telegram-chat-id",
        required=True,
        help="Telegram chat ID to send notifications to",
    )
    ai_notify_parser.add_argument(
        "--test",
        action="store_true",
        help="Send a test notification after configuring",
    )
    ai_notify_parser.set_defaults(func=cmd_ai_config_notify)

    # -- ai list-providers --
    ai_list_parser = ai_subparsers.add_parser(
        "list-providers",
        help="Show available AI providers and their capabilities",
    )
    ai_list_parser.set_defaults(func=cmd_ai_list_providers)

    # -- ai add-mcp --
    ai_mcp_parser = ai_subparsers.add_parser(
        "add-mcp",
        help="Add an isolated MCP server to an existing AI project",
    )
    ai_mcp_parser.add_argument(
        "--server",
        required=True,
        help="MCP server name (e.g. filesystem, github). Known: "
        + ", ".join(sorted(MCP_KNOWN_PACKAGES)),
    )
    ai_mcp_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project directory (default: current directory)",
    )
    ai_mcp_parser.add_argument(
        "--project-path",
        default="/workspace",
        help="Mount path for project files inside the container (default: /workspace)",
    )
    ai_mcp_parser.set_defaults(func=cmd_ai_add_mcp)

    # -- watchdog (subcommand group) --
    watchdog_parser = subparsers.add_parser(
        "watchdog",
        help="Locally-scheduled watchdog for dtl-managed project health",
    )
    watchdog_subparsers = watchdog_parser.add_subparsers(dest="watchdog_command")

    # -- watchdog install --
    wd_install_parser = watchdog_subparsers.add_parser(
        "install",
        help=(
            "Write ~/.config/systemd/user/dtl-watchdog.{service,timer} "
            "and print activation commands"
        ),
    )
    wd_install_parser.add_argument(
        "--projects",
        required=True,
        help="Comma-separated project directories to monitor",
    )
    wd_install_parser.add_argument(
        "--interval",
        type=int,
        default=120,
        metavar="MINUTES",
        help="Timer interval in minutes (default: 120)",
    )
    wd_install_parser.set_defaults(func=cmd_watchdog_install)

    # -- watchdog check --
    wd_check_parser = watchdog_subparsers.add_parser(
        "check",
        help="Run anomaly checks across monitored projects and emit pass/fail summary",
    )
    wd_check_parser.add_argument(
        "--projects",
        required=True,
        help="Comma-separated project directories to check",
    )
    wd_check_parser.set_defaults(func=cmd_watchdog_check)

    # -- watchdog status --
    wd_status_parser = watchdog_subparsers.add_parser(
        "status",
        help="Print last watchdog run result and next scheduled run",
    )
    wd_status_parser.set_defaults(func=cmd_watchdog_status)

    # -- workflow (subcommand group) --
    workflow_parser = subparsers.add_parser(
        "workflow",
        help="Manage gitflow feature workflow from a DEVPLAN.md",
    )
    workflow_subparsers = workflow_parser.add_subparsers(dest="workflow_command")

    # -- workflow list --
    wf_list_parser = workflow_subparsers.add_parser(
        "list",
        help="Print all features with their status",
    )
    wf_list_parser.add_argument(
        "--plan",
        required=True,
        help="Path to DEVPLAN.md (e.g. docs/DEVPLAN.md)",
    )
    wf_list_parser.set_defaults(func=cmd_workflow_list)

    # -- workflow next --
    wf_next_parser = workflow_subparsers.add_parser(
        "next",
        help="Start the next Not Started feature: create branch, update status, launch AI",
    )
    wf_next_parser.add_argument(
        "--plan",
        required=True,
        help="Path to DEVPLAN.md (e.g. docs/DEVPLAN.md)",
    )
    wf_next_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project/git root (default: current directory)",
    )
    wf_next_parser.set_defaults(func=cmd_workflow_next)

    # -- workflow finish --
    wf_finish_parser = workflow_subparsers.add_parser(
        "finish",
        help="Lint, test, push, create PR for the current feature branch",
    )
    wf_finish_parser.add_argument(
        "--plan",
        required=True,
        help="Path to DEVPLAN.md (e.g. docs/DEVPLAN.md)",
    )
    wf_finish_parser.add_argument(
        "--project",
        default=".",
        help="Path to the project/git root (default: current directory)",
    )
    wf_finish_parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll for PR merge and auto-update status",
    )
    wf_finish_parser.set_defaults(func=cmd_workflow_finish)

    # -- workflow run --
    wf_run_parser = workflow_subparsers.add_parser(
        "run",
        help="Full autonomous loop: branch -> AI -> test -> PR -> wait for merge -> repeat",
    )
    wf_run_parser.add_argument(
        "--projects",
        required=True,
        help="Comma-separated project directories (e.g. ~/proj1,~/proj2)",
    )
    wf_run_parser.add_argument(
        "--schedule",
        default=None,
        help="Defer start until HH:MM (e.g. 02:00 for off-peak)",
    )
    wf_run_parser.add_argument(
        "--max-failures",
        type=int,
        default=3,
        help="Skip a feature after this many consecutive failures (default: 3)",
    )
    wf_run_parser.add_argument(
        "--log",
        default=None,
        metavar="PATH",
        help=(
            "Path for the workflow log file. "
            "Default: $XDG_STATE_HOME/dtl/<first-project-name>-workflow.log "
            "(typically ~/.local/state/dtl/<project>-workflow.log). "
            "WARNING: do not set this to a path inside any --projects directory; "
            "an untracked log file makes the git tree dirty and causes the "
            "dirty-tree skip loop."
        ),
    )
    wf_run_parser.add_argument(
        "--max-wall-clock",
        dest="max_wall_clock",
        type=int,
        default=1800,
        metavar="SECONDS",
        help=(
            "Hard kill each AI session after this many seconds (default: 1800 = 30 min). "
            "Passed through to 'dtl ai run'."
        ),
    )
    wf_run_parser.add_argument(
        "--max-ai-retries",
        dest="max_ai_retries",
        type=int,
        default=3,
        metavar="N",
        help=(
            "Kill an AI session after N detected retry loops in output "
            "(default: 3; 0 = disabled). Passed through to 'dtl ai run'."
        ),
    )
    wf_run_parser.add_argument(
        "--quota-reset-sleep",
        dest="quota_reset_sleep",
        type=int,
        default=3600,
        metavar="SECONDS",
        help=(
            "Seconds to sleep after the provider chain is exhausted by quota limits "
            "before retrying from the first provider (default: 3600 = 1 hour)."
        ),
    )
    wf_run_parser.set_defaults(func=cmd_workflow_run)

    # -- workflow status --
    wf_status_parser = workflow_subparsers.add_parser(
        "status",
        help="Show per-feature state (cause) alongside DEVPLAN status (lifecycle)",
    )
    wf_status_parser.add_argument(
        "--plan",
        required=True,
        help="Path to DEVPLAN.md",
    )
    wf_status_parser.set_defaults(func=cmd_workflow_status)

    # -- notify --
    notify_parser = subparsers.add_parser(
        "notify",
        help="Notification hook management",
    )
    notify_subparsers = notify_parser.add_subparsers(dest="notify_command")
    nt_test_parser = notify_subparsers.add_parser(
        "test",
        help="Send a synthetic event to verify notification config",
    )
    nt_test_parser.add_argument(
        "--event",
        default="idle",
        choices=["ai-failure", "feature-merged", "needs-attention", "idle"],
        help="Event type to send (default: idle)",
    )
    nt_test_parser.set_defaults(func=cmd_notify_test)

    # -- pm (subcommand group) --
    pm_parser = subparsers.add_parser(
        "pm",
        help="PM coordination layer management",
    )
    pm_subparsers = pm_parser.add_subparsers(dest="pm_command")

    # -- pm install --
    pm_install_parser = pm_subparsers.add_parser(
        "install",
        help="Materialize the canonical PM config (pm/) into a workspace",
    )
    pm_install_parser.add_argument(
        "--workspace",
        default="~/Projects",
        help="Target workspace directory (default: ~/Projects)",
    )
    pm_install_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be copied without making changes",
    )
    pm_install_parser.set_defaults(func=cmd_pm_install)

    # -- Parse and dispatch --
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle 'ai' subcommand group
    if args.command == "ai":
        if not getattr(args, "ai_command", None):
            ai_parser.print_help()
            sys.exit(1)

    # Handle 'workflow' subcommand group
    if args.command == "workflow":
        if not getattr(args, "workflow_command", None):
            workflow_parser.print_help()
            sys.exit(1)

    # Handle 'watchdog' subcommand group
    if args.command == "watchdog":
        if not getattr(args, "watchdog_command", None):
            watchdog_parser.print_help()
            sys.exit(1)

    # Handle 'notify' subcommand group
    if args.command == "notify":
        if not getattr(args, "notify_command", None):
            notify_parser.print_help()
            sys.exit(1)

    # Handle 'pm' subcommand group
    if args.command == "pm":
        if not getattr(args, "pm_command", None):
            pm_parser.print_help()
            sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
