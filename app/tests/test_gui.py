"""Tests for the GUI's non-visual helpers.

Skipped when tkinter is unavailable (it ships with Python on Windows and
macOS; on Linux it may need a python3-tk package).
"""

import os
import queue
import sys

import pytest

pytest.importorskip("tkinter")

from resume_matcher.gui import _PROGRESS_RE, _QueueWriter  # noqa: E402


def test_queue_writer_emits_complete_lines():
    q = queue.Queue()
    writer = _QueueWriter(q)
    writer.write("first line\nsecond ")
    assert q.get_nowait() == ("log", "first line")
    assert q.empty()          # partial line is buffered, not emitted

    writer.write("line\n")
    assert q.get_nowait() == ("log", "second line")


def test_queue_writer_flushes_trailing_text():
    q = queue.Queue()
    writer = _QueueWriter(q)
    writer.write("no newline yet")
    assert q.empty()
    writer.flush()
    assert q.get_nowait() == ("log", "no newline yet")


def test_progress_regex_reads_matcher_output():
    match = _PROGRESS_RE.search("  [7/25 total, 28%] scoring anna.pdf ...")
    assert match and (int(match.group(1)), int(match.group(2))) == (7, 25)


def test_progress_regex_ignores_other_lines():
    assert _PROGRESS_RE.search("Report saved to results/run.html") is None


def test_host_of_extracts_hostname():
    from resume_matcher.gui import host_of

    assert host_of("https://api.openai.com/v1") == "api.openai.com"
    assert host_of("http://localhost:8888/v1") == "localhost"
    assert host_of("not a url") == "not a url"


def test_summary_text_flags_hosted_mode():
    from resume_matcher.config import Config
    from resume_matcher.gui import summary_text

    local = Config()
    assert summary_text(local) == "Using gemma-4-12b @ localhost (local)"
    hosted = Config()
    hosted.llm_mode, hosted.llm_base_url, hosted.llm_model = "hosted", "https://api.openai.com/v1", "gpt-x"
    assert "data leaves this machine" in summary_text(hosted)
    assert "api.openai.com" in summary_text(hosted)
    hosted.llm_model = ""
    assert "(no model set)" in summary_text(hosted)


def test_unreachable_text_names_host_and_tab():
    from resume_matcher.gui import unreachable_text

    text = unreachable_text("http://localhost:8888/v1")
    assert "localhost" in text and "Server tab" in text


def test_ensure_tcl_env_points_at_base_install(tmp_path, monkeypatch):
    from resume_matcher.gui import ensure_tcl_env

    base = tmp_path / "Python313"
    (base / "tcl" / "tcl8.6").mkdir(parents=True)
    (base / "tcl" / "tcl8.6" / "init.tcl").write_text("")
    (base / "tcl" / "tk8.6").mkdir()
    (base / "tcl" / "tk8.6" / "tk.tcl").write_text("")
    (base / "tcl" / "tix8.4.3").mkdir()          # must be ignored
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "base_prefix", str(base))
    monkeypatch.delenv("TCL_LIBRARY", raising=False)
    monkeypatch.delenv("TK_LIBRARY", raising=False)

    ensure_tcl_env()
    assert os.environ["TCL_LIBRARY"] == str(base / "tcl" / "tcl8.6")
    assert os.environ["TK_LIBRARY"] == str(base / "tcl" / "tk8.6")


def test_ensure_tcl_env_keeps_existing_and_skips_elsewhere(tmp_path, monkeypatch):
    from resume_matcher.gui import ensure_tcl_env

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))   # no tcl folder at all
    monkeypatch.setenv("TCL_LIBRARY", "C:/custom/tcl")
    monkeypatch.delenv("TK_LIBRARY", raising=False)
    ensure_tcl_env()
    assert os.environ["TCL_LIBRARY"] == "C:/custom/tcl"
    assert "TK_LIBRARY" not in os.environ

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("TCL_LIBRARY", raising=False)
    ensure_tcl_env()
    assert "TCL_LIBRARY" not in os.environ
