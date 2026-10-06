"""Per-project venv for host lint/tests and the sandbox tooling note."""

import importlib.util
import subprocess
import sys
from pathlib import Path

DTL_PATH = Path(__file__).parent.parent / "dtl.py"
spec = importlib.util.spec_from_file_location("dtl", DTL_PATH)
dtl = importlib.util.module_from_spec(spec)
sys.modules.setdefault("dtl", dtl)
spec.loader.exec_module(dtl)


def _make_project(root: Path, name: str = "proj") -> Path:
    project = root / name
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "tiny"\nversion = "0.0.1"\n', encoding="utf-8"
    )
    return project


def test_venv_path_under_cache_outside_project(tmp_path, monkeypatch):
    cache = tmp_path / "cache-root"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    project = _make_project(tmp_path)
    venv = dtl._project_venv(project)
    assert cache / "dtl" / "venvs" in venv.parents
    assert project not in venv.parents
    assert venv.name.startswith("proj-")
    assert (venv / "bin" / "python").exists()


def test_venv_path_stable_and_distinct(tmp_path):
    a = _make_project(tmp_path, "a")
    other = tmp_path / "sub"
    other.mkdir()
    b = _make_project(other, "a")
    assert dtl._project_venv(a) == dtl._project_venv(a)
    assert dtl._project_venv(a) != dtl._project_venv(b)


def test_venv_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PIP_BREAK_SYSTEM_PACKAGES", "1")
    env = dtl._venv_env(tmp_path / "v")
    assert env["VIRTUAL_ENV"] == str(tmp_path / "v")
    assert env["PATH"].startswith(str(tmp_path / "v" / "bin"))
    assert "PIP_BREAK_SYSTEM_PACKAGES" not in env


def test_ci_sh_runs_with_venv_python(tmp_path):
    project = _make_project(tmp_path)
    scripts = project / "scripts"
    scripts.mkdir()
    (scripts / "ci.sh").write_text("#!/usr/bin/env bash\ncommand -v python\n", encoding="utf-8")
    passed, output = dtl._run_lint_and_tests(project)
    venv = dtl._project_venv(project)
    assert passed, output
    assert output.strip().startswith(str(venv / "bin"))


def test_offline_install_of_dependency_free_project(tmp_path):
    project = _make_project(tmp_path)
    (project / "requirements.txt").write_text("", encoding="utf-8")
    venv = dtl._project_venv(project)
    result = subprocess.run(
        [
            str(venv / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "--no-index",
            "-r",
            "requirements.txt",
        ],
        cwd=project,
        env=dtl._venv_env(venv),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    where = subprocess.run(
        [str(venv / "bin" / "python"), "-c", "import sys; print(sys.prefix)"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert where.stdout.strip() == str(venv)


def test_fallback_fails_clearly_without_pytest(tmp_path, monkeypatch):
    project = _make_project(tmp_path)
    calls = []
    real_run = subprocess.run

    def fake_run(cmd, *a, **kw):
        calls.append(cmd)
        if "pip" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return real_run(cmd, *a, **kw)

    monkeypatch.setattr(dtl.subprocess, "run", fake_run)
    passed, output = dtl._run_lint_and_tests(project)
    assert not passed
    assert "pytest is not installed" in output
    pip_cmd = next(c for c in calls if "pip" in c)
    assert f"ruff=={dtl.RUFF_VERSION}" in pip_cmd
    assert pip_cmd[-3:-1] == ["-e", "."]


def test_dev_extra_selected(tmp_path):
    project = _make_project(tmp_path)
    assert not dtl._has_dev_extra(project)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "t"\nversion = "0"\n[project.optional-dependencies]\ndev = ["pytest"]\n',
        encoding="utf-8",
    )
    assert dtl._has_dev_extra(project)


def test_no_break_system_packages_in_dtl():
    text = DTL_PATH.read_text(encoding="utf-8").lower()
    assert "break-system-packages" not in text
    assert "ephemeral usb workstation's system" not in text
    # the only remaining mention is the env var being scrubbed
    assert text.count("break_system_packages") == 1


def test_tooling_note(tmp_path):
    project = _make_project(tmp_path)
    (project / "scripts").mkdir()
    (project / "scripts" / "ci.sh").write_text("true\n", encoding="utf-8")
    note = dtl._sandbox_tooling_note(project)
    assert "/home/claude/.venvs/" in note
    assert "scripts/ci.sh" in note
    assert f"ruff=={dtl.RUFF_VERSION}" in note

    other = tmp_path / "node"
    other.mkdir()
    (other / "package.json").write_text("{}", encoding="utf-8")
    assert dtl._sandbox_tooling_note(other) == ""
