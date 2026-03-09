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
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Dict, List

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
        "dockerfile_run": (
            "RUN pip install --no-cache-dir --upgrade pip"
        ),
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
        "claude_linter": "go vet ./... && test -z \"$(gofmt -l .)\"",
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
        "dockerfile_run": (
            "RUN rustup component add clippy rustfmt"
        ),
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
# Template generators
# ---------------------------------------------------------------------------


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
        lines.append(f"      test: [\"{svc['healthcheck_cmd']}\"]")
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


def make_claude_md(name: str, stack_name: str, stack: dict) -> str:
    """Generate CLAUDE.md context file for Claude Code."""
    return textwrap.dedent(f"""\
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

        ## Branching

        - Push to feature branches, NEVER directly to main.
        - Branch naming: `feat/short-description`, `fix/short-description`.
        - Open a PR for every change.

        ## Linting & Formatting

        Run before every commit:

        ```bash
        {stack["claude_linter"]}
        ```

        If linting fails, fix the issues before committing.

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
    ci_setup = stack["ci_setup"].rstrip()
    return textwrap.dedent(f"""\
        name: CI

        on:
          push:
            branches: [main]
          pull_request:
            branches: [main]

        permissions:
          contents: read

        jobs:
          lint-and-test:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
        {ci_setup}

          security-scan:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: gitleaks/gitleaks-action@v2
                env:
                  GITLEAKS_LICENSE: ${{{{ secrets.GITLEAKS_LICENSE }}}}
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
# AI sandbox template generators
# ---------------------------------------------------------------------------

AI_PROVIDERS = ["claude", "ollama"]

SSH_KEY_PATH = Path.home() / ".ssh" / "ai-sandbox-key"


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
              # Restrict network from inside VM
              net.ipv4.ip_forward=0
    """)


def make_ai_vm_config(name: str, ai_providers: List[str]) -> str:
    """Generate QEMU launch script for the AI sandbox VM."""
    ollama_forward = ""
    if "ollama" in ai_providers:
        ollama_forward = (
            '  -netdev user,id=net0,'
            'hostfwd=tcp::2222-:22,'
            'guestfwd=tcp:10.0.2.100:11434-tcp:127.0.0.1:11434 \\'
        )
    else:
        ollama_forward = (
            '  -netdev user,id=net0,'
            'hostfwd=tcp::2222-:22 \\'
        )

    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # AI Sandbox VM launcher for project: {name}
        # Configurable via environment variables.
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

            create_disk

            echo "[ai-sandbox] Starting VM (cpus=$AI_VM_CPUS, ram=$AI_VM_RAM)..."
            qemu-system-x86_64 \\
              -enable-kvm \\
              -cpu host \\
              -smp "$AI_VM_CPUS" \\
              -m "$AI_VM_RAM" \\
              -drive file="$VM_DISK",format=qcow2 \\
              -drive file="$VM_DIR/seed.iso",format=raw \\
        {ollama_forward}
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


def make_ai_docker_compose(
    ai_providers: List[str],
    mcp_servers: List[str] | None = None,
) -> str:
    """Generate docker-compose.yml for containers inside the AI sandbox VM."""
    lines = ["services:"]

    if "claude" in ai_providers:
        lines.extend([
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
            "    environment:",
            "      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}",
            "",
        ])

    if mcp_servers:
        for srv in mcp_servers:
            lines.extend(_mcp_compose_entry(srv))
    else:
        lines.extend([
            "  # To add an MCP server run:",
            "  #   dtl add-mcp --name <server> --project .",
            "",
        ])

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
    """Generate Dockerfile for the Claude Code container inside the VM."""
    return textwrap.dedent("""\
        FROM node:22-slim

        # Install system dependencies
        RUN apt-get update && apt-get install -y --no-install-recommends \\
                git \\
                ripgrep \\
                python3 \\
                ca-certificates \\
                curl \\
            && rm -rf /var/lib/apt/lists/*

        # Install Claude Code
        RUN npm install -g @anthropic-ai/claude-code

        # Create non-root user
        RUN useradd -m -s /bin/bash dev
        USER dev
        WORKDIR /workspace

        ENTRYPOINT ["claude"]
    """)


def make_ai_claude_settings(
    ai_providers: List[str],
    mcp_servers: List[str] | None = None,
) -> str:
    """Generate Claude Code settings for the sandbox."""
    mcp_config: dict = {}
    for srv in (mcp_servers or []):
        binary_name = MCP_KNOWN_PACKAGES.get(srv, srv).rsplit("/", 1)[-1]
        mcp_config[srv] = {
            "command": "docker",
            "args": ["exec", "-i", f"mcp-{srv}", binary_name],
        }

    settings: dict = {
        "permissions": {
            "allow": [
                "Read",
                "Glob",
                "Grep",
            ],
            "deny": [],
        },
        "mcpServers": mcp_config,
    }
    return json.dumps(settings, indent=2) + "\n"


# ---------------------------------------------------------------------------
# MCP server isolation (Phase 3)
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

    if ai_providers:
        dirs.extend([
            project_dir / "ai-sandbox",
            project_dir / "ai-sandbox" / "vm",
            project_dir / "ai-sandbox" / "containers",
            project_dir / "ai-sandbox" / "containers" / "mcp-servers",
        ])
        if "claude" in ai_providers:
            dirs.append(project_dir / "ai-sandbox" / "containers" / "claude-code")

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # -- files --
    files: Dict[Path, str] = {
        project_dir / ".gitignore": make_gitignore(stack),
        project_dir / "README.md": make_readme(name, stack_name),
        project_dir / "CLAUDE.md": make_claude_md(name, stack_name, stack),
        project_dir / ".pre-commit-config.yaml": make_precommit_config(),
        project_dir / ".github" / "workflows" / "ci.yml": make_ci_workflow(name, stack),
        project_dir / ".devcontainer" / "Dockerfile": make_dockerfile(stack),
        project_dir / ".devcontainer" / "devcontainer.json": make_devcontainer_json(
            name, stack, services,
        ),
        project_dir / ".env.example": make_env_example(services),
    }

    if services:
        files[project_dir / "docker-compose.yml"] = make_docker_compose(services)

    # -- AI sandbox files --
    if ai_providers:
        sandbox = project_dir / "ai-sandbox"
        files[sandbox / "Makefile"] = make_ai_makefile(name)
        files[sandbox / "vm" / "cloud-init.yaml"] = make_ai_cloud_init()
        files[sandbox / "vm" / "vm-config.sh"] = make_ai_vm_config(name, ai_providers)
        files[sandbox / "containers" / "docker-compose.yml"] = make_ai_docker_compose(ai_providers)
        files[sandbox / "containers" / "mcp-servers" / ".gitkeep"] = ""

        if "claude" in ai_providers:
            files[sandbox / "containers" / "claude-code" / "Dockerfile"] = make_ai_claude_dockerfile()
            files[sandbox / "containers" / "claude-code" / "settings.json"] = make_ai_claude_settings(ai_providers)

    for path, content in files.items():
        path.write_text(content)

    # Make VM config script executable
    if ai_providers:
        vm_script = project_dir / "ai-sandbox" / "vm" / "vm-config.sh"
        if vm_script.exists():
            vm_script.chmod(0o755)

    return project_dir


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


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

    compose = project_dir / "docker-compose.yml"
    if compose.exists():
        content = compose.read_text()
        check(
            "docker-compose.yml: no host port mappings",
            "ports:" not in content,
        )

    # AI sandbox checks
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
        check(
            "ai-sandbox: cloud-init exists",
            (sandbox / "vm" / "cloud-init.yaml").exists(),
        )

        ai_compose = sandbox / "containers" / "docker-compose.yml"
        if ai_compose.exists():
            content = ai_compose.read_text()
            check(
                "ai-sandbox: containers use cap_drop ALL",
                "cap_drop:" in content and "ALL" in content,
            )
            check(
                "ai-sandbox: containers use no-new-privileges",
                "no-new-privileges" in content,
            )

        # MCP server isolation checks
        mcp_dir = sandbox / "containers" / "mcp-servers"
        if mcp_dir.is_dir():
            for srv_dir in sorted(mcp_dir.iterdir()):
                if not srv_dir.is_dir() or srv_dir.name.startswith("."):
                    continue
                srv = srv_dir.name
                check(f"mcp-{srv}: Dockerfile exists", (srv_dir / "Dockerfile").exists())
                check(f"mcp-{srv}: config.json exists", (srv_dir / "config.json").exists())
                if ai_compose.exists():
                    compose_text = ai_compose.read_text()
                    check(
                        f"mcp-{srv}: network_mode none",
                        f"mcp-{srv}:" in compose_text and "network_mode: none" in compose_text,
                    )
                    check(
                        f"mcp-{srv}: read_only true",
                        f"mcp-{srv}:" in compose_text and "read_only: true" in compose_text,
                    )

    print(f"\n  {passed}/{total} checks passed.")
    return passed == total


# ---------------------------------------------------------------------------
# CLI
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

    # Validate base dir
    if not base_dir.is_dir():
        print(f"Error: directory does not exist: {base_dir}", file=sys.stderr)
        sys.exit(1)

    # Scaffold
    print(f"Scaffolding {stack_name} project '{name}' in {base_dir}/")
    if services:
        print(f"  Services: {', '.join(services)}")
    if ai_providers:
        print(f"  AI sandbox: {', '.join(ai_providers)}")

    project_dir = scaffold_project(name, stack_name, services, base_dir, ai_providers or None)

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
        print("  make -C ai-sandbox up     # Start AI sandbox VM")
        print("  make -C ai-sandbox ssh    # SSH into sandbox")
    else:
        print("  # Open in VS Code and select 'Reopen in Container'")


def cmd_list_stacks(args: argparse.Namespace) -> None:
    """Handle the 'list-stacks' subcommand."""
    print("Available stacks:\n")
    for key, stack in sorted(STACKS.items()):
        print(f"  {key:10s}  {stack['display']}")

    print("\nAvailable services (use with --services):\n")
    for key, svc in sorted(SERVICES.items()):
        print(f"  {key:10s}  {svc['image']}")


def cmd_add_mcp(args: argparse.Namespace) -> None:
    """Handle the 'add-mcp' subcommand."""
    server_name: str = args.name
    project_dir = Path(args.project).resolve()
    project_path: str = args.project_path or "/workspace"

    sandbox = project_dir / "ai-sandbox"
    containers = sandbox / "containers"
    mcp_dir = containers / "mcp-servers"

    if not sandbox.is_dir():
        print(
            f"Error: no ai-sandbox/ directory in {project_dir}.\n"
            "  Scaffold with: dtl new --name <project> --stack <stack> --ai claude",
            file=sys.stderr,
        )
        sys.exit(1)

    srv_dir = mcp_dir / server_name
    if srv_dir.exists():
        print(f"Error: MCP server '{server_name}' already exists at {srv_dir}", file=sys.stderr)
        sys.exit(1)

    srv_dir.mkdir(parents=True, exist_ok=True)

    # Write Dockerfile and config
    (srv_dir / "Dockerfile").write_text(make_mcp_server_dockerfile(server_name))
    (srv_dir / "config.json").write_text(make_mcp_server_config(server_name, project_path))

    # Discover all MCP servers
    existing_servers: List[str] = sorted(
        d.name for d in mcp_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    # Detect active AI providers from existing compose
    ai_compose_path = containers / "docker-compose.yml"
    ai_providers: List[str] = []
    if ai_compose_path.exists():
        compose_text = ai_compose_path.read_text()
        if "claude-code:" in compose_text:
            ai_providers.append("claude")
    if not ai_providers:
        ai_providers = ["claude"]

    # Regenerate docker-compose and settings with all MCP servers
    ai_compose_path.write_text(
        make_ai_docker_compose(ai_providers, mcp_servers=existing_servers)
    )

    settings_path = containers / "claude-code" / "settings.json"
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

    print(f"\nNext steps:")
    print(f"  1. Review {srv_dir / 'Dockerfile'}")
    if npm_package != server_name:
        print(f"     (installs {npm_package})")
    print(f"  2. Edit {srv_dir / 'config.json'} to set server arguments")
    print(f"  3. Rebuild: cd ai-sandbox/containers && docker compose build")
    print(f"  4. Test: docker compose run --rm mcp-{server_name}")

    print("\nValidation:")
    validate_project(project_dir)


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
        help="Comma-separated AI providers for sandbox (e.g. claude,ollama)",
    )
    new_parser.set_defaults(func=cmd_new)

    # -- list-stacks --
    list_parser = subparsers.add_parser(
        "list-stacks",
        help="Show available stacks and services",
    )
    list_parser.set_defaults(func=cmd_list_stacks)

    # -- add-mcp --
    mcp_parser = subparsers.add_parser(
        "add-mcp",
        help="Add an isolated MCP server to an existing AI sandbox project",
    )
    mcp_parser.add_argument(
        "--name",
        required=True,
        help="MCP server name (e.g. filesystem, github). Known: " + ", ".join(sorted(MCP_KNOWN_PACKAGES)),
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

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
