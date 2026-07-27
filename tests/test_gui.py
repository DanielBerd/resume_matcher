"""Tests for the GUI's non-visual helpers.

Skipped when tkinter is unavailable (it ships with Python on Windows and
macOS; on Linux it may need a python3-tk package).
"""

import queue

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
