"""Tests for MCP container config generation and validation."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import (
    MCP_KNOWN_PACKAGES,
    _mcp_compose_entry,
    make_ai_claude_settings,
    make_mcp_server_config,
    make_mcp_server_dockerfile,
)

# ---------------------------------------------------------------------------
# MCP_KNOWN_PACKAGES
# ---------------------------------------------------------------------------


def test_known_packages_count() -> None:
    assert len(MCP_KNOWN_PACKAGES) == 10


def test_known_packages_contains_required() -> None:
    required = {
        "filesystem",
        "github",
        "memory",
        "brave-search",
        "fetch",
        "sqlite",
        "postgres",
        "slack",
        "puppeteer",
        "sequential-thinking",
    }
    assert required == set(MCP_KNOWN_PACKAGES.keys())


def test_known_packages_use_modelcontextprotocol_scope() -> None:
    for pkg in MCP_KNOWN_PACKAGES.values():
        assert pkg.startswith("@modelcontextprotocol/"), pkg


# ---------------------------------------------------------------------------
# _mcp_compose_entry
# ---------------------------------------------------------------------------


def test_compose_entry_network_none() -> None:
    lines = _mcp_compose_entry("filesystem")
    assert "    network_mode: none" in lines


def test_compose_entry_read_only() -> None:
    lines = _mcp_compose_entry("filesystem")
    assert "    read_only: true" in lines


def test_compose_entry_cap_drop_all() -> None:
    lines = _mcp_compose_entry("filesystem")
    assert "      - ALL" in lines


def test_compose_entry_no_new_privileges() -> None:
    lines = _mcp_compose_entry("filesystem")
    assert "      - no-new-privileges:true" in lines


def test_compose_entry_memory_limit() -> None:
    lines = _mcp_compose_entry("filesystem")
    assert "          memory: 512M" in lines


def test_compose_entry_cpu_limit() -> None:
    lines = _mcp_compose_entry("filesystem")
    assert "          cpus: '1'" in lines


def test_compose_entry_workspace_readonly() -> None:
    lines = _mcp_compose_entry("github")
    assert "      - /workspace:/workspace:ro" in lines


def test_compose_entry_stdin_open() -> None:
    lines = _mcp_compose_entry("memory")
    assert "    stdin_open: true" in lines


def test_compose_entry_service_name() -> None:
    lines = _mcp_compose_entry("myserver")
    assert lines[0] == "  mcp-myserver:"


def test_compose_entry_build_path() -> None:
    lines = _mcp_compose_entry("myserver")
    assert "    build: ./mcp-servers/myserver" in lines


# ---------------------------------------------------------------------------
# make_mcp_server_dockerfile
# ---------------------------------------------------------------------------


def test_dockerfile_known_package() -> None:
    content = make_mcp_server_dockerfile("filesystem")
    assert "@modelcontextprotocol/server-filesystem" in content


def test_dockerfile_unknown_package_passthrough() -> None:
    content = make_mcp_server_dockerfile("my-custom-server")
    assert "my-custom-server" in content


def test_dockerfile_nonroot_user() -> None:
    content = make_mcp_server_dockerfile("filesystem")
    assert "USER mcp" in content


def test_dockerfile_node_base() -> None:
    content = make_mcp_server_dockerfile("filesystem")
    assert content.startswith("FROM node:")


def test_dockerfile_entrypoint_uses_binary_name() -> None:
    content = make_mcp_server_dockerfile("filesystem")
    binary = MCP_KNOWN_PACKAGES["filesystem"].rsplit("/", 1)[-1]
    assert f'ENTRYPOINT ["{binary}"]' in content


def test_dockerfile_custom_server_entrypoint() -> None:
    content = make_mcp_server_dockerfile("some-custom-pkg")
    assert 'ENTRYPOINT ["some-custom-pkg"]' in content


# ---------------------------------------------------------------------------
# make_mcp_server_config
# ---------------------------------------------------------------------------


def test_config_is_valid_json() -> None:
    raw = make_mcp_server_config("filesystem", "/workspace")
    data = json.loads(raw)
    assert isinstance(data, dict)


def test_config_known_package_resolved() -> None:
    data = json.loads(make_mcp_server_config("filesystem", "/workspace"))
    assert data["package"] == "@modelcontextprotocol/server-filesystem"


def test_config_unknown_package_passthrough() -> None:
    data = json.loads(make_mcp_server_config("my-server", "/myproject"))
    assert data["package"] == "my-server"


def test_config_project_path_stored() -> None:
    data = json.loads(make_mcp_server_config("memory", "/home/user/proj"))
    assert data["project_path"] == "/home/user/proj"


def test_config_name_field() -> None:
    data = json.loads(make_mcp_server_config("github", "/workspace"))
    assert data["name"] == "github"


# ---------------------------------------------------------------------------
# make_ai_claude_settings — MCP wiring
# ---------------------------------------------------------------------------


def test_settings_no_mcp_servers() -> None:
    raw = make_ai_claude_settings(["claude"])
    data = json.loads(raw)
    assert data["mcpServers"] == {}


def test_settings_mcp_uses_docker_exec() -> None:
    raw = make_ai_claude_settings(["claude"], mcp_servers=["filesystem"])
    data = json.loads(raw)
    entry = data["mcpServers"]["filesystem"]
    assert entry["command"] == "docker"
    assert "exec" in entry["args"]
    assert "-i" in entry["args"]


def test_settings_mcp_container_name() -> None:
    raw = make_ai_claude_settings(["claude"], mcp_servers=["github"])
    data = json.loads(raw)
    assert "mcp-github" in data["mcpServers"]["github"]["args"]


def test_settings_mcp_binary_name() -> None:
    raw = make_ai_claude_settings(["claude"], mcp_servers=["filesystem"])
    data = json.loads(raw)
    binary = MCP_KNOWN_PACKAGES["filesystem"].rsplit("/", 1)[-1]
    assert binary in data["mcpServers"]["filesystem"]["args"]


def test_settings_multiple_mcp_servers() -> None:
    raw = make_ai_claude_settings(
        ["claude"], mcp_servers=["filesystem", "github", "memory"]
    )
    data = json.loads(raw)
    assert set(data["mcpServers"].keys()) == {"filesystem", "github", "memory"}


def test_settings_unknown_mcp_server_passthrough() -> None:
    raw = make_ai_claude_settings(["claude"], mcp_servers=["my-custom-mcp"])
    data = json.loads(raw)
    assert "my-custom-mcp" in data["mcpServers"]
    entry = data["mcpServers"]["my-custom-mcp"]
    assert "mcp-my-custom-mcp" in entry["args"]


def test_settings_permissions_present() -> None:
    raw = make_ai_claude_settings(["claude"])
    data = json.loads(raw)
    assert "permissions" in data
    assert "allow" in data["permissions"]
    assert len(data["permissions"]["allow"]) > 0
