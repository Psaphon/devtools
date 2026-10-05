"""Tests for ci-ok aggregation gate in generated CI workflows."""

import argparse
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import _CI_YML_SCAFFOLD, STACKS, make_ci_workflow

# ---------------------------------------------------------------------------
# make_ci_workflow — scaffolded per-stack CI template
# ---------------------------------------------------------------------------


def test_make_ci_workflow_contains_ci_ok_job():
    stack = STACKS["python"]
    content = make_ci_workflow("myproject", stack)
    assert "ci-ok:" in content


def test_make_ci_workflow_ci_ok_needs_all_jobs():
    stack = STACKS["python"]
    content = make_ci_workflow("myproject", stack)
    assert "needs: [lint-and-test, shellcheck, security-scan]" in content


def test_make_ci_workflow_ci_ok_runs_always():
    stack = STACKS["python"]
    content = make_ci_workflow("myproject", stack)
    # ci-ok block must have if: always()
    ci_ok_idx = content.index("ci-ok:")
    ci_ok_section = content[ci_ok_idx:]
    assert "if: always()" in ci_ok_section


def test_make_ci_workflow_ci_ok_fails_on_failure():
    """ci-ok must inspect needs.*.result and exit 1 on failure/cancelled."""
    stack = STACKS["python"]
    content = make_ci_workflow("myproject", stack)
    assert "needs.*.result" in content
    assert "exit 1" in content


def test_make_ci_workflow_ci_ok_present_for_all_stacks():
    for stack_name, stack in STACKS.items():
        content = make_ci_workflow(stack_name, stack)
        assert "ci-ok:" in content, f"ci-ok missing for stack {stack_name!r}"
        assert "needs: [lint-and-test, shellcheck, security-scan]" in content, (
            f"ci-ok not wired to all jobs for stack {stack_name!r}"
        )


# ---------------------------------------------------------------------------
# security-scan job — per-stack dependency audit
# ---------------------------------------------------------------------------


def test_make_ci_workflow_security_scan_job_present_for_python():
    content = make_ci_workflow("myproject", STACKS["python"])
    assert "security-scan:" in content


def test_make_ci_workflow_security_scan_job_present_for_node():
    content = make_ci_workflow("myproject", STACKS["node"])
    assert "security-scan:" in content


def test_make_ci_workflow_python_stack_has_pip_audit():
    content = make_ci_workflow("myproject", STACKS["python"])
    assert "pip-audit" in content


def test_make_ci_workflow_node_stack_has_npm_audit():
    content = make_ci_workflow("myproject", STACKS["node"])
    assert "npm audit" in content


def test_make_ci_workflow_security_scan_present_for_all_stacks():
    for stack_name, stack in STACKS.items():
        content = make_ci_workflow(stack_name, stack)
        assert "security-scan:" in content, f"security-scan job missing for stack {stack_name!r}"
        assert "gitleaks" in content, (
            f"gitleaks missing from security-scan for stack {stack_name!r}"
        )


# ---------------------------------------------------------------------------
# _CI_YML_SCAFFOLD — the --scaffold-ci fallback template
# ---------------------------------------------------------------------------


def test_ci_yml_scaffold_contains_ci_ok_job():
    assert "ci-ok:" in _CI_YML_SCAFFOLD


def test_ci_yml_scaffold_ci_ok_needs_lint_and_test():
    assert "needs: [lint-and-test]" in _CI_YML_SCAFFOLD


def test_ci_yml_scaffold_ci_ok_runs_always():
    ci_ok_idx = _CI_YML_SCAFFOLD.index("ci-ok:")
    ci_ok_section = _CI_YML_SCAFFOLD[ci_ok_idx:]
    assert "if: always()" in ci_ok_section


def test_ci_yml_scaffold_ci_ok_fails_on_failure():
    assert "needs.*.result" in _CI_YML_SCAFFOLD
    assert "exit 1" in _CI_YML_SCAFFOLD


# ---------------------------------------------------------------------------
# --scaffold-ci integration: written file contains ci-ok
# ---------------------------------------------------------------------------


def test_scaffold_ci_written_file_contains_ci_ok(tmp_path):
    """cmd_ai_attach --scaffold-ci must write a file that includes ci-ok."""
    from dtl import cmd_ai_attach

    project = tmp_path / "myproject"
    project.mkdir()

    args = argparse.Namespace(
        project=str(project),
        provider="claude",
        mode="docker",
        model=None,
        key_source="env",
        scaffold_ci=True,
        no_ci=False,
    )
    cmd_ai_attach(args)

    ci_path = project / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists()
    content = ci_path.read_text()
    assert "ci-ok:" in content
    assert "needs: [lint-and-test]" in content
    assert "if: always()" in content
    assert "needs.*.result" in content


# ---------------------------------------------------------------------------
# ci-ok structure and behaviour: parsed YAML, and the gate script actually run
# ---------------------------------------------------------------------------

_TEMPLATES = {name: make_ci_workflow("p", STACKS[name]) for name in STACKS}
_TEMPLATES["fallback"] = _CI_YML_SCAFFOLD


@pytest.mark.parametrize("label", sorted(_TEMPLATES))
def test_ci_ok_is_a_job_that_needs_every_other_job(label: str) -> None:
    jobs = yaml.safe_load(_TEMPLATES[label])["jobs"]
    assert "ci-ok" in jobs, "ci-ok must sit under jobs:"
    assert sorted(jobs["ci-ok"]["needs"]) == sorted(j for j in jobs if j != "ci-ok")
    assert "contains(needs" not in _TEMPLATES[label], "skipped must not pass ci-ok"


@pytest.mark.parametrize("label", sorted(_TEMPLATES))
@pytest.mark.parametrize(
    ("results", "ok"),
    [
        ("success success", True),
        ("success skipped", False),
        ("failure", False),
        ("cancelled", False),
    ],
)
def test_ci_ok_gate_requires_every_job_to_succeed(label: str, results: str, ok: bool) -> None:
    step = yaml.safe_load(_TEMPLATES[label])["jobs"]["ci-ok"]["steps"][0]
    proc = subprocess.run(
        ["bash", "-c", step["run"]],
        env={"RESULTS": results, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        check=False,
    )
    assert (proc.returncode == 0) is ok


def test_python_template_runs_on_fix_docs_chore_pushes() -> None:
    push = yaml.safe_load(_TEMPLATES["python"])[True]["push"]["branches"]
    for pattern in ("feature/**", "fix/**", "docs/**", "chore/**"):
        assert pattern in push
