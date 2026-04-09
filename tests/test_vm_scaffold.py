"""Tests for VM scaffold file generation and config validation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import (
    AI_MODES,
    make_ai_cloud_init,
    make_ai_makefile,
    make_ai_vm_compose,
    make_ai_vm_config,
)

# ---------------------------------------------------------------------------
# make_ai_cloud_init
# ---------------------------------------------------------------------------


def test_cloud_init_starts_with_header() -> None:
    content = make_ai_cloud_init()
    assert content.startswith("#cloud-config")


def test_cloud_init_hostname() -> None:
    content = make_ai_cloud_init()
    assert "hostname: ai-sandbox" in content


def test_cloud_init_dev_user() -> None:
    content = make_ai_cloud_init()
    assert "name: dev" in content


def test_cloud_init_docker_installed() -> None:
    content = make_ai_cloud_init()
    assert "docker.io" in content


def test_cloud_init_iptables_persistent_installed() -> None:
    content = make_ai_cloud_init()
    assert "iptables-persistent" in content


def test_cloud_init_docker_enabled() -> None:
    content = make_ai_cloud_init()
    assert "systemctl enable --now docker" in content


def test_cloud_init_claude_code_installed() -> None:
    content = make_ai_cloud_init()
    assert "@anthropic-ai/claude-code" in content


def test_cloud_init_workspace_mount() -> None:
    content = make_ai_cloud_init()
    assert "mkdir -p /workspace" in content


def test_cloud_init_iptables_output_drop() -> None:
    """Default policy drops all outbound traffic."""
    content = make_ai_cloud_init()
    assert "iptables -P OUTPUT DROP" in content


def test_cloud_init_iptables_allow_slirp_subnet() -> None:
    """Allow traffic within the QEMU SLIRP virtual network."""
    content = make_ai_cloud_init()
    assert "iptables -A OUTPUT -d 10.0.2.0/24 -j ACCEPT" in content


def test_cloud_init_iptables_allow_established() -> None:
    content = make_ai_cloud_init()
    assert "ESTABLISHED,RELATED" in content


def test_cloud_init_anthropic_hosts_entry() -> None:
    """Anthropic API routed through guestfwd proxy address."""
    content = make_ai_cloud_init()
    assert "10.0.2.101" in content
    assert "api.anthropic.com" in content


def test_cloud_init_ip_forward_disabled() -> None:
    content = make_ai_cloud_init()
    assert "net.ipv4.ip_forward=0" in content


# ---------------------------------------------------------------------------
# make_ai_vm_config — without Ollama
# ---------------------------------------------------------------------------


def test_vm_config_contains_project_name() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "myproject" in content


def test_vm_config_enable_kvm() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "-enable-kvm" in content


def test_vm_config_configurable_cpus() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "AI_VM_CPUS" in content


def test_vm_config_configurable_ram() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "AI_VM_RAM" in content


def test_vm_config_configurable_disk() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "AI_VM_DISK" in content


def test_vm_config_cloud_image_env_var() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "AI_VM_CLOUD_IMAGE" in content


def test_vm_config_network_restricted() -> None:
    """SLIRP restrict=on must be present to block all non-whitelisted traffic."""
    content = make_ai_vm_config("myproject", ["claude"])
    assert "restrict=on" in content


def test_vm_config_ssh_forward() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "hostfwd=tcp::2222-:22" in content


def test_vm_config_anthropic_proxy_guestfwd() -> None:
    """Anthropic API allowed via guestfwd to host-side proxy."""
    content = make_ai_vm_config("myproject", ["claude"])
    assert "guestfwd=tcp:10.0.2.101:443-tcp:127.0.0.1:4430" in content


def test_vm_config_no_ollama_forward_without_provider() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    # The guestfwd line for Ollama must not be present when Ollama is not a provider
    assert "guestfwd=tcp:10.0.2.100:11434" not in content


def test_vm_config_anthropic_proxy_function() -> None:
    """Host-side proxy must be started before the VM."""
    content = make_ai_vm_config("myproject", ["claude"])
    assert "start_anthropic_proxy" in content
    assert "api.anthropic.com" in content
    assert "4430" in content


def test_vm_config_proxy_stopped_on_vm_stop() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "stop_anthropic_proxy" in content


def test_vm_config_virtfs_workspace() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "mount_tag=workspace" in content


def test_vm_config_daemonize() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "-daemonize" in content


def test_vm_config_pidfile() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    assert "PIDFILE" in content


def test_vm_config_start_stop_status_destroy() -> None:
    content = make_ai_vm_config("myproject", ["claude"])
    for cmd in ("start", "stop", "status", "destroy"):
        assert cmd in content


# ---------------------------------------------------------------------------
# make_ai_vm_config — with Ollama
# ---------------------------------------------------------------------------


def test_vm_config_ollama_guestfwd_present() -> None:
    """Ollama guestfwd added when ollama is in providers."""
    content = make_ai_vm_config("myproject", ["claude", "ollama"])
    assert "guestfwd=tcp:10.0.2.100:11434-tcp:127.0.0.1:11434" in content


def test_vm_config_ollama_and_anthropic_both_forwarded() -> None:
    content = make_ai_vm_config("myproject", ["claude", "ollama"])
    assert "guestfwd=tcp:10.0.2.100:11434" in content
    assert "guestfwd=tcp:10.0.2.101:443" in content


def test_vm_config_ollama_still_restricted() -> None:
    """restrict=on must be present even when Ollama is enabled."""
    content = make_ai_vm_config("myproject", ["claude", "ollama"])
    assert "restrict=on" in content


# ---------------------------------------------------------------------------
# make_ai_makefile
# ---------------------------------------------------------------------------


def test_makefile_contains_project_name() -> None:
    content = make_ai_makefile("myproject")
    assert "myproject" in content


def test_makefile_up_target() -> None:
    content = make_ai_makefile("myproject")
    assert "up:" in content


def test_makefile_down_target() -> None:
    content = make_ai_makefile("myproject")
    assert "down:" in content


def test_makefile_ssh_target() -> None:
    content = make_ai_makefile("myproject")
    assert "ssh:" in content


def test_makefile_status_target() -> None:
    content = make_ai_makefile("myproject")
    assert "status:" in content


def test_makefile_destroy_target() -> None:
    content = make_ai_makefile("myproject")
    assert "destroy:" in content


def test_makefile_phony_all_targets() -> None:
    content = make_ai_makefile("myproject")
    assert ".PHONY:" in content
    for target in ("up", "down", "ssh", "status", "destroy"):
        assert target in content


def test_makefile_ssh_key() -> None:
    content = make_ai_makefile("myproject")
    assert "ai-sandbox-key" in content


def test_makefile_vm_config_script() -> None:
    content = make_ai_makefile("myproject")
    assert "vm-config.sh" in content


# ---------------------------------------------------------------------------
# make_ai_vm_compose
# ---------------------------------------------------------------------------


def test_vm_compose_services_header() -> None:
    content = make_ai_vm_compose(["claude"])
    assert content.startswith("services:")


def test_vm_compose_claude_service() -> None:
    content = make_ai_vm_compose(["claude"])
    assert "claude-code:" in content


def test_vm_compose_cap_drop_all() -> None:
    content = make_ai_vm_compose(["claude"])
    assert "- ALL" in content


def test_vm_compose_no_new_privileges() -> None:
    content = make_ai_vm_compose(["claude"])
    assert "no-new-privileges:true" in content


def test_vm_compose_workspace_volume() -> None:
    content = make_ai_vm_compose(["claude"])
    assert "/workspace:/workspace" in content


def test_vm_compose_resource_limits() -> None:
    content = make_ai_vm_compose(["claude"])
    assert "memory: 4G" in content


def test_vm_compose_no_claude_when_not_requested() -> None:
    content = make_ai_vm_compose(["ollama"])
    assert "claude-code:" not in content


def test_vm_compose_mcp_server_included() -> None:
    content = make_ai_vm_compose(["claude"], mcp_servers=["filesystem"])
    assert "mcp-filesystem:" in content


# ---------------------------------------------------------------------------
# AI_MODES constant
# ---------------------------------------------------------------------------


def test_ai_modes_includes_vm() -> None:
    assert "vm" in AI_MODES


def test_ai_modes_includes_docker() -> None:
    assert "docker" in AI_MODES
