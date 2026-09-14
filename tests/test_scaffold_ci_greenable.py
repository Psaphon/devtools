"""Tests for the scaffold-ci-greenable feature.

Verifies that:
- A freshly scaffolded Python project actually passes its own CI (not just that
  CI jobs were emitted — the previous test anti-pattern that let all seven defects ship).
- CI (ci.yml) and the local preflight (_run_lint_and_tests) invoke the SAME script
  so parity is structural, not disciplinary.
- Generated notify.py is already ruff-formatted so the first push is green.
- The dev-extra install path locks down the atrade PR #7 failure (respx was in
  [dev] but CI installed a hand-listed package set and never saw it).
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import (
    _CI_YML_SCAFFOLD,
    RUFF_VERSION,
    STACKS,
    _run_lint_and_tests,
    make_ci_sh,
    make_ci_workflow,
    make_notify_script,
    scaffold_project,
)


# ---------------------------------------------------------------------------
# Defect 2: notify.py must ship ruff-formatted so the first push is green
# ---------------------------------------------------------------------------


def test_notify_py_is_ruff_formatted(tmp_path):
    """Generated notify.py must pass ruff format --check as-is."""
    notify_path = tmp_path / "notify.py"
    notify_path.write_text(make_notify_script())
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", str(notify_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"Generated notify.py is not ruff-formatted:\n{result.stdout}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Defect 1: pytest must gate — || true masked all failures
# ---------------------------------------------------------------------------


def test_ci_sh_pytest_exit_code_5_tolerated():
    """scripts/ci.sh must tolerate pytest exit-5 (no tests) but fail on all others."""
    ci_sh = make_ci_sh("python")
    # Must have exit-5 tolerance
    assert '[ "$rc" -eq 5 ]' in ci_sh or "[ $rc -eq 5 ]" in ci_sh, (
        "ci.sh must tolerate pytest exit-5 (no tests collected on empty scaffold)"
    )
    # Must NOT blanket suppress failures
    assert "|| true" not in ci_sh, "ci.sh must not mask failures with || true"


# ---------------------------------------------------------------------------
# Defect 7 (atrade): CI must install from declared deps, not a hand-listed set
# ---------------------------------------------------------------------------


def test_ci_sh_installs_from_dev_extra(tmp_path):
    """scripts/ci.sh must install from .[dev], never a hand-written package list.

    This is the exact atrade PR #7 failure: respx was declared in [dev] and the
    local preflight installed it via -e .[dev], but CI installed a hand-listed set
    that omitted it.  ModuleNotFoundError at 02:00; batch stalled all night.
    """
    project_dir = scaffold_project("atrade", "python", [], tmp_path)
    ci_sh = project_dir / "scripts" / "ci.sh"
    assert ci_sh.exists(), "Python scaffold must generate scripts/ci.sh"

    content = ci_sh.read_text()
    # Must install from the project's declared extra
    assert ".[dev]" in content, "ci.sh must install from .[dev] extra"
    # Must NOT hard-list test packages
    assert "pip install pytest" not in content, "ci.sh must not hard-list pytest"
    assert "pip install ruff pytest" not in content, "ci.sh must not hard-list test deps"
    # Must NOT have a fallback that silently degrades the environment
    assert "|| pip install" not in content, (
        "ci.sh must not have a || pip install fallback — broken extras must fail loudly"
    )


def test_ci_sh_pins_ruff():
    """scripts/ci.sh must pin ruff at the fleet version so upstream releases cannot red CI."""
    ci_sh_content = make_ci_sh("python")
    assert f"ruff=={RUFF_VERSION}" in ci_sh_content, (
        f"ci.sh must pin ruff at RUFF_VERSION ({RUFF_VERSION!r})"
    )


def test_ci_yml_calls_ci_sh_not_restated_steps(tmp_path):
    """Generated ci.yml must call bash scripts/ci.sh, not restate lint/test steps."""
    stack = STACKS["python"]
    content = make_ci_workflow("myproject", stack)
    assert "bash scripts/ci.sh" in content, (
        "ci.yml lint-and-test job must delegate to scripts/ci.sh rather than restating steps"
    )
    # Old anti-patterns must be gone
    assert "pip install ruff pytest" not in content
    assert "pip install pytest" not in content


# ---------------------------------------------------------------------------
# Parity: ci.yml and _run_lint_and_tests must invoke the SAME script
# ---------------------------------------------------------------------------


def test_run_lint_and_tests_uses_ci_sh_when_present(tmp_path):
    """_run_lint_and_tests must call bash scripts/ci.sh when the script exists."""
    (tmp_path / "scripts").mkdir()
    ci_sh = tmp_path / "scripts" / "ci.sh"
    ci_sh.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n")
    ci_sh.chmod(0o755)

    with patch("dtl.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        passed, _output = _run_lint_and_tests(tmp_path)

    assert passed
    called_cmd = mock_run.call_args_list[0][0][0]
    assert called_cmd == ["bash", str(ci_sh)], (
        f"_run_lint_and_tests must call ['bash', '<ci.sh>'], got {called_cmd!r}"
    )


def test_run_lint_and_tests_falls_back_without_ci_sh(tmp_path):
    """_run_lint_and_tests must use the legacy path when scripts/ci.sh is absent."""
    # Empty project dir: no ci.sh, no stack files → success (nothing to check)
    passed, _output = _run_lint_and_tests(tmp_path)
    assert passed


def test_ci_parity_enforced_by_structure(tmp_path):
    """Both ci.yml and _run_lint_and_tests must reference the SAME scripts/ci.sh.

    This is the structural fix: parity is enforced by a test, not by discipline.
    Previously ci.yml restated the steps and _run_lint_and_tests had its own copy —
    two definitions that will eventually disagree, discovered at 02:00.
    """
    project_dir = scaffold_project("parity", "python", [], tmp_path)

    # ci.yml calls the script
    ci_yml = (project_dir / ".github" / "workflows" / "ci.yml").read_text()
    assert "bash scripts/ci.sh" in ci_yml, "ci.yml must call scripts/ci.sh"

    # _run_lint_and_tests also calls the same script
    with patch("dtl.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_lint_and_tests(project_dir)

    called_cmd = mock_run.call_args_list[0][0][0]
    assert called_cmd[0] == "bash", "_run_lint_and_tests must use bash"
    assert "ci.sh" in called_cmd[1], (
        f"_run_lint_and_tests must invoke ci.sh, got {called_cmd[1]!r}"
    )


# ---------------------------------------------------------------------------
# Defects 3/4: gitleaks CLI instead of brittle gitleaks-action
# ---------------------------------------------------------------------------


def test_ci_yml_uses_gitleaks_cli_not_action():
    """Generated ci.yml must use gitleaks CLI, not gitleaks-action@v2 (defects 3 & 4).

    gitleaks-action requires GITHUB_TOKEN + pull-requests:write and returns
    'Unexpected exit code 1' on clean scans.  The CLI has no such requirements.
    """
    content = make_ci_workflow("myproject", STACKS["python"])
    assert "gitleaks-action" not in content, (
        "ci.yml must not use gitleaks-action@v2 — needs GITHUB_TOKEN, fails on clean PRs"
    )
    assert "gitleaks detect" in content, "ci.yml must use gitleaks CLI (gitleaks detect)"


def test_ci_yml_gitleaks_present_all_stacks():
    """gitleaks CLI must appear in all stack-generated CI workflows."""
    for stack_name, stack in STACKS.items():
        content = make_ci_workflow(stack_name, stack)
        assert "gitleaks detect" in content, (
            f"gitleaks CLI missing from generated ci.yml for stack {stack_name!r}"
        )
        assert "gitleaks-action" not in content, (
            f"gitleaks-action still present in ci.yml for stack {stack_name!r}"
        )


# ---------------------------------------------------------------------------
# Defect 6: pip-audit must audit an isolated venv, not the runner's ambient env
# ---------------------------------------------------------------------------


def test_ci_yml_pip_audit_uses_isolated_venv():
    """Generated ci.yml must audit deps in an isolated venv (defect 6).

    pip-audit with no args audits whatever is globally installed — on a GH runner
    that's dozens of stale, vulnerable system packages unrelated to the project.
    The security-scan job always fails.  Audit a clean venv instead.
    """
    content = make_ci_workflow("myproject", STACKS["python"])
    assert "python -m venv .audit-venv" in content, (
        "pip-audit must run in an isolated venv, not the runner's ambient environment"
    )
    assert "--skip-editable" in content, (
        "pip-audit must use --skip-editable to audit transitive deps only"
    )


# ---------------------------------------------------------------------------
# _CI_YML_SCAFFOLD (--scaffold-ci fallback) fixes
# ---------------------------------------------------------------------------


def test_ci_scaffold_yml_pins_ruff():
    """_CI_YML_SCAFFOLD (--scaffold-ci) must pin ruff at the fleet version."""
    assert f"ruff=={RUFF_VERSION}" in _CI_YML_SCAFFOLD, (
        "The --scaffold-ci fallback template must pin ruff to avoid upstream-release CI failures"
    )


def test_ci_scaffold_yml_no_hand_listed_test_deps():
    """_CI_YML_SCAFFOLD must not hard-list test packages on the pip line."""
    assert "pip install pytest" not in _CI_YML_SCAFFOLD, (
        "_CI_YML_SCAFFOLD must not hard-list pytest — use project declared deps"
    )


# ---------------------------------------------------------------------------
# Strongest: scaffold a project, add one importing test, assert CI goes green
#
# This test actually EXECUTES scripts/ci.sh.  Do NOT mark it skip/xfail.
# A skipped proof is the green-but-blind failure this feature exists to remove.
# ---------------------------------------------------------------------------


def test_scaffold_goes_green(tmp_path):
    """A freshly scaffolded Python project with one importing test must pass CI.

    Executes the generated scripts/ci.sh in a fresh venv and asserts exit 0.
    This catches the whole class of green-but-blind template bugs — not just the
    known instances.  If something is missing in the generated CI logic this test
    will fail, not silently pass.
    """
    project_dir = scaffold_project("greentest", "python", [], tmp_path)

    # Minimal pyproject.toml with pytest in [dev] — the source of truth for test deps.
    # Mirrors the atrade project structure: test deps declared in dev extra only.
    # Uses setuptools.build_meta (stable since setuptools ~43) for broad compatibility.
    (project_dir / "pyproject.toml").write_text(
        textwrap.dedent("""\
            [project]
            name = "greentest"
            version = "0.1.0"
            requires-python = ">=3.11"

            [project.optional-dependencies]
            dev = ["pytest"]

            [build-system]
            requires = ["setuptools"]
            build-backend = "setuptools.build_meta"
        """)
    )

    # A trivial test that imports a package installed ONLY via the [dev] extra.
    # If CI installs from a hand-listed set it may accidentally pass.
    # If CI installs from [dev], it passes structurally — the only correct way.
    (project_dir / "tests" / "test_import.py").write_text(
        textwrap.dedent("""\
            def test_dev_extra_installed():
                import pytest  # available only when [dev] extra is installed

                assert pytest is not None
        """)
    )

    ci_sh = project_dir / "scripts" / "ci.sh"
    assert ci_sh.exists(), "Python scaffold must generate scripts/ci.sh"

    # Create a fresh isolated venv.  Pre-install ruff and setuptools so that
    # ci.sh's `pip install "ruff==X"` step is a fast no-op (already satisfied)
    # and `pip install -e '.[dev]'` has a working build backend.  Uses pip's
    # download cache — no fresh network download needed when packages have
    # already been installed on this machine.
    venv_dir = tmp_path / ".ci-venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True,
        capture_output=True,
    )
    venv_pip = str(venv_dir / "bin" / "pip")
    subprocess.run(
        [venv_pip, "install", "-q", f"ruff=={RUFF_VERSION}", "setuptools"],
        check=True,
        capture_output=True,
    )

    env = os.environ.copy()
    venv_bin = str(venv_dir / "bin")
    env["PATH"] = venv_bin + ":" + env.get("PATH", "")
    env["VIRTUAL_ENV"] = str(venv_dir)
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        ["bash", str(ci_sh)],
        cwd=project_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"scripts/ci.sh exited {result.returncode} — scaffold does not pass its own CI.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
