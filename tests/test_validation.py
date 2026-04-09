"""Tests for smart port-mapping validation in validate_project."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import _check_ai_port_mappings

# ---------------------------------------------------------------------------
# _check_ai_port_mappings
# ---------------------------------------------------------------------------

AI_WITH_PORTS = """\
version: "3.9"
services:
  claude-code:
    image: ghcr.io/anthropics/claude-code:latest
    ports:
      - "2222:22"
    cap_drop:
      - ALL
"""

AI_WITHOUT_PORTS = """\
version: "3.9"
services:
  claude-code:
    image: ghcr.io/anthropics/claude-code:latest
    cap_drop:
      - ALL
"""

OPENCLAW_WITH_PORTS = """\
version: "3.9"
services:
  openclaw-gateway:
    image: openclaw:latest
    ports:
      - "8080:8080"
"""

SERVICE_WITH_PORTS_NO_AI = """\
version: "3.9"
services:
  db:
    image: postgres:16
    ports:
      - "5432:5432"
  cache:
    image: redis:7
    ports:
      - "6379:6379"
"""

OLLAMA_WITH_PORTS = """\
version: "3.9"
services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
"""

MIXED_AI_AND_SERVICE = """\
version: "3.9"
services:
  db:
    image: postgres:16
    ports:
      - "5432:5432"
  claude-code:
    image: ghcr.io/anthropics/claude-code:latest
    ports:
      - "2222:22"
"""

MIXED_AI_OK_SERVICE_PORTS = """\
version: "3.9"
services:
  db:
    image: postgres:16
    ports:
      - "5432:5432"
  claude-code:
    image: ghcr.io/anthropics/claude-code:latest
    cap_drop:
      - ALL
"""

NO_PORTS_AT_ALL = """\
version: "3.9"
services:
  app:
    image: myapp:latest
"""


def test_ai_container_with_ports_fails():
    """AI container (claude-code) with ports: should fail."""
    assert _check_ai_port_mappings(AI_WITH_PORTS) is False


def test_openclaw_gateway_with_ports_fails():
    """AI container (openclaw-gateway) with ports: should fail."""
    assert _check_ai_port_mappings(OPENCLAW_WITH_PORTS) is False


def test_ai_container_without_ports_passes():
    """AI container without ports: should pass."""
    assert _check_ai_port_mappings(AI_WITHOUT_PORTS) is True


def test_service_containers_with_ports_pass():
    """Non-AI service containers (postgres, redis) with ports: should pass."""
    assert _check_ai_port_mappings(SERVICE_WITH_PORTS_NO_AI) is True


def test_ollama_with_ports_passes():
    """Ollama service with ports: should pass (not an AI container)."""
    assert _check_ai_port_mappings(OLLAMA_WITH_PORTS) is True


def test_mixed_ai_with_ports_and_service_with_ports_fails():
    """Service container OK with ports, but AI container with ports should fail."""
    assert _check_ai_port_mappings(MIXED_AI_AND_SERVICE) is False


def test_mixed_ai_ok_service_with_ports_passes():
    """Service container with ports is fine as long as AI container has none."""
    assert _check_ai_port_mappings(MIXED_AI_OK_SERVICE_PORTS) is True


def test_no_ports_at_all_passes():
    """No ports anywhere should pass."""
    assert _check_ai_port_mappings(NO_PORTS_AT_ALL) is True
