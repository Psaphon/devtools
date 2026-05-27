"""Tests for ci-ok aggregation gate in generated CI workflows."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dtl import STACKS, _CI_YML_SCAFFOLD, make_ci_workflow


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
