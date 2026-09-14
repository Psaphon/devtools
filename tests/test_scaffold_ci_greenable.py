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
    assert "ci.sh" in called_cmd[1], f"_run_lint_and_tests must invoke ci.sh, got {called_cmd[1]!r}"


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
    assert "gitleaks dir ." in content, "ci.yml must scan the working tree with the gitleaks CLI"
    assert "-C /usr/local/bin" not in content, "the runner user cannot write /usr/local/bin"


def test_ci_yml_gitleaks_present_all_stacks():
    """gitleaks CLI must appear in all stack-generated CI workflows."""
    for stack_name, stack in STACKS.items():
        content = make_ci_workflow(stack_name, stack)
        assert "gitleaks dir ." in content, (
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
    assert "python -m venv /tmp/auditenv" in content, (
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
    """An untouched python scaffold plus one importing test must pass its own CI.

    Runs the generated scripts/ci.sh in a fresh venv and asserts exit 0. Three
    things keep this honest:

    - The scaffold's own pyproject.toml is used as generated, never rewritten, so
      a scaffold that declares no test dependencies fails here as it would on CI.
    - The test imports ``devonlyprobe``, a local package declared ONLY in the dev
      extra. A CI that hand-lists its test packages cannot install it, so this is
      the atrade PR #7 failure (respx declared in [dev], missing in CI) as a test.
    - The subprocess cannot see the host's user site or ~/.local/bin, so a pytest
      installed on the developer's machine cannot stand in for a missing one.
    """
    project_dir = scaffold_project("greentest", "python", [], tmp_path)
    pyproject = project_dir / "pyproject.toml"
    assert pyproject.exists(), "python scaffold must declare its own dependencies"

    probe = tmp_path / "devonlyprobe"
    (probe / "devonlyprobe").mkdir(parents=True)
    (probe / "devonlyprobe" / "__init__.py").write_text("MARKER = 'dev-extra'\n")
    (probe / "pyproject.toml").write_text(
        textwrap.dedent("""\
            [project]
            name = "devonlyprobe"
            version = "0.0.1"

            [build-system]
            requires = ["setuptools>=61"]
            build-backend = "setuptools.build_meta"
        """)
    )
    generated = pyproject.read_text()
    assert 'dev = ["pytest"]' in generated
    pyproject.write_text(
        generated.replace(
            'dev = ["pytest"]',
            f'dev = ["pytest", "devonlyprobe @ {probe.as_uri()}"]',
        )
    )

    (project_dir / "tests" / "test_import.py").write_text(
        textwrap.dedent("""\
            import devonlyprobe


            def test_dev_extra_installed():
                assert devonlyprobe.MARKER == "dev-extra"
        """)
    )

    ci_sh = project_dir / "scripts" / "ci.sh"
    assert ci_sh.exists(), "Python scaffold must generate scripts/ci.sh"

    venv_dir = tmp_path / ".ci-venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, capture_output=True)

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {
        "PATH": f"{venv_dir / 'bin'}:/usr/bin:/bin",
        "VIRTUAL_ENV": str(venv_dir),
        "HOME": str(fake_home),
        "PYTHONNOUSERSITE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }
    # Guard the guard: pytest must not be reachable before ci.sh installs it.
    pre = subprocess.run(
        ["bash", "-c", "command -v pytest"], env=env, capture_output=True, text=True, check=False
    )
    assert pre.returncode != 0, f"pytest leaked into the isolated env: {pre.stdout}"

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
    assert "1 passed" in result.stdout, f"the importing test did not run:\n{result.stdout}"
