"""The AI sandbox must run as a uid that can write the repo, rootless or not.

Under rootless Docker, container uid 0 is the host user and uid 1000 maps to an
unrelated subordinate id that cannot write the bind-mounted repo. The compose
file runs as ${UID}:${GID}, which bash never exports, so it always ran as 1000
(hub, 2026-09-29).
"""

import os
import subprocess
from collections.abc import Iterator

import pytest

import dtl


@pytest.fixture(autouse=True)
def _fresh_detection() -> Iterator[None]:
    dtl._docker_is_rootless.cache_clear()
    yield
    dtl._docker_is_rootless.cache_clear()


def _fake_info(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        assert cmd[:2] == ["docker", "info"]
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(dtl.subprocess, "run", fake_run)


def test_rootless_runs_the_sandbox_as_container_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_info(monkeypatch, '["name=seccomp,profile=builtin","name=rootless","name=cgroupns"]')
    env = dtl._compose_env()
    assert (env["UID"], env["GID"]) == ("0", "0")


def test_rootful_runs_the_sandbox_as_the_host_user(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_info(monkeypatch, '["name=apparmor","name=seccomp,profile=builtin"]')
    env = dtl._compose_env()
    assert (env["UID"], env["GID"]) == (str(os.getuid()), str(os.getgid()))


def test_no_docker_counts_as_not_rootless(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        raise FileNotFoundError

    monkeypatch.setattr(dtl.subprocess, "run", missing)
    assert dtl._docker_is_rootless() is False


def test_compose_commands_get_the_uid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[tuple[str, ...], dict[str, str]] = {}
    monkeypatch.setattr(dtl, "_compose_env", lambda: {"UID": "0", "GID": "0", "PATH": "/bin"})

    def fake_run(
        cmd: list[str], env: dict[str, str], check: bool = False
    ) -> subprocess.CompletedProcess:
        seen[tuple(cmd[:2])] = env
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(dtl.subprocess, "run", fake_run)
    dtl._run_cmd(["docker", "compose", "ps"])
    dtl._run_cmd(["git", "status"])
    assert seen[("docker", "compose")]["UID"] == "0"
    # Other commands get the plain environment, untouched.
    assert seen[("git", "status")].get("UID") == os.environ.get("UID")


def test_templates_own_home_by_the_run_uid() -> None:
    """Image home dir and container user must come from the same UID/GID."""
    dockerfile = dtl.make_ai_claude_dockerfile()
    assert "ARG HOME_UID=1000" in dockerfile
    assert "chown -R ${HOME_UID}:${HOME_GID} /home/claude" in dockerfile
    assert "1000:1000" not in dockerfile

    # devtools has no YAML dependency; check the generated text line by line.
    compose = dtl.make_ai_docker_compose("claude").splitlines()
    assert '    user: "${UID:-1000}:${GID:-1000}"' in compose
    build = compose.index("    build:")
    assert compose[build + 1 : build + 5] == [
        "      context: ./claude-code",
        "      args:",
        '        HOME_UID: "${UID:-1000}"',
        '        HOME_GID: "${GID:-1000}"',
    ]
