"""Tests for the one-click setup helper (stdlib only, no network)."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bootstrap  # noqa: E402


def test_requirements_hash_tracks_content(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("openai\n")
    h1 = bootstrap.requirements_hash(req)
    req.write_text("openai\npytest\n")
    assert bootstrap.requirements_hash(req) != h1


def test_deps_current_compares_stamp_to_hash(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("openai\n")
    stamp = tmp_path / "stamp"
    assert not bootstrap.deps_current(stamp, req)          # no stamp yet
    stamp.write_text(bootstrap.requirements_hash(req) + "\n")
    assert bootstrap.deps_current(stamp, req)
    req.write_text("openai\nextra\n")
    assert not bootstrap.deps_current(stamp, req)          # requirements changed


def test_venv_python_paths_per_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert bootstrap.venv_python(tmp_path).name == "python.exe"
    assert bootstrap.venv_python(tmp_path, windowless=True).name == "pythonw.exe"
    monkeypatch.setattr(sys, "platform", "linux")
    assert bootstrap.venv_python(tmp_path) == tmp_path / "bin" / "python"


def test_running_inside_venv_flag(monkeypatch):
    monkeypatch.setenv(bootstrap.IN_VENV_FLAG, "1")
    assert bootstrap.running_inside_venv()
    monkeypatch.delenv(bootstrap.IN_VENV_FLAG)
    assert not bootstrap.running_inside_venv(Path("/definitely/not/here"))


def test_python_ok_rejects_old_interpreter(monkeypatch):
    monkeypatch.setattr(sys, "version_info", (3, 8, 0, "final", 0))
    assert "3.10" in bootstrap.python_ok()
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    assert bootstrap.python_ok() is None


@pytest.mark.skipif(os.environ.get("RM_SKIP_VENV_TEST") == "1", reason="slow")
def test_ensure_ready_creates_venv_and_installs(tmp_path):
    pytest.importorskip("ensurepip")
    req = tmp_path / "requirements.txt"
    req.write_text("")  # nothing to download; exercises the whole flow offline
    venv = tmp_path / ".venv"
    lines = []
    py = bootstrap.ensure_ready(lines.append, venv=venv, requirements=req)
    assert py.exists()
    assert (venv / bootstrap.STAMP.name).read_text().strip() == bootstrap.requirements_hash(req)
    assert any("creating" in l.lower() for l in lines)
    assert any("installed" in l.lower() for l in lines)
    # Second call is a no-op: stamp matches, nothing logged.
    lines.clear()
    assert bootstrap.ensure_ready(lines.append, venv=venv, requirements=req) == py
    assert lines == []
