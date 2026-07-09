"""Resume text extraction for .pdf, .docx, and .doc files.

Step 2 of the workflow: the user has a folder with resumes in Word or PDF format.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}


@dataclass
class Resume:
    """A resume file and its extracted plain text."""

    path: Path
    text: str

    @property
    def name(self) -> str:
        return self.path.name


def load_resumes(resumes_dir: Path) -> list[Resume]:
    """Extract text from every supported resume file in a folder."""
    resumes: list[Resume] = []
    for path in sorted(resumes_dir.iterdir()):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        text = extract_text(path)
        if text.strip():
            resumes.append(Resume(path=path, text=text))
        else:
            print(f"[warn] No text extracted from {path.name}; skipping.")
    return resumes


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".doc":
        return _extract_doc(path)
    raise ValueError(f"Unsupported file type: {path}")


def _extract_pdf(path: Path) -> str:
    import fitz  # pymupdf

    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _extract_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def _extract_doc(path: Path) -> str:
    """Extract text from a legacy .doc file.

    Requires an external tool. Tries antiword, then LibreOffice (soffice)
    as a fallback conversion to .docx.
    """
    if shutil.which("antiword"):
        result = subprocess.run(["antiword", str(path)], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout

    if shutil.which("soffice"):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "docx", "--outdir", tmp, str(path)],
                capture_output=True,
            )
            converted = Path(tmp) / (path.stem + ".docx")
            if converted.exists():
                return _extract_docx(converted)

    print(f"[warn] Cannot extract {path.name}: install antiword or LibreOffice for .doc support.")
    return ""
