"""Tests for loading a single job posting file (used by the GUI drop zone)."""

import pytest

from resume_matcher.email_ingest import load_job_from_file


def test_loads_plain_text(tmp_path):
    path = tmp_path / "backend_role.txt"
    path.write_text("We need a backend developer.", encoding="utf-8")
    job = load_job_from_file(path)
    assert job.title == "backend_role"
    assert "backend developer" in job.body
    assert job.source == "backend_role.txt"


def test_loads_eml_subject_and_body(tmp_path):
    path = tmp_path / "offer.eml"
    path.write_bytes(
        b"From: hr@example.com\r\nSubject: Job Opening: Rust Engineer\r\n"
        b'Content-Type: text/plain; charset="utf-8"\r\n\r\nWe are hiring a Rust engineer.\r\n'
    )
    job = load_job_from_file(path)
    assert job.title == "Job Opening: Rust Engineer"
    assert "Rust engineer" in job.body


def test_loads_docx(tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "role.docx"
    doc = docx.Document()
    doc.add_paragraph("Embedded C++ role with FreeRTOS.")
    doc.save(str(path))
    job = load_job_from_file(path)
    assert "FreeRTOS" in job.body


def test_rejects_unsupported_extension(tmp_path):
    path = tmp_path / "posting.xlsx"
    path.write_text("nope", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported job posting file"):
        load_job_from_file(path)
