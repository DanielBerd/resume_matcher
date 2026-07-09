"""Orchestration: score every resume against every job and keep the top N.

Step 4 of the workflow: collect ratings per job, then report the top 5.
"""

from __future__ import annotations

from .config import Config
from .documents import Resume, ocr_with_tesseract, pdf_page_images, tesseract_available
from .email_ingest import JobPosting
from .llm_client import LocalLLM, guess_mime_type
from .scoring import MatchResult, score_resume


class Progress:
    """Counter for overall progress across all job x resume pairs."""

    def __init__(self, total: int):
        self.total = total
        self.done = 0

    def tick(self) -> str:
        self.done += 1
        percent = 100 * self.done // self.total if self.total else 100
        return f"[{self.done}/{self.total} total, {percent}%]"


def transcribe_resumes(llm: LocalLLM, resumes: list[Resume], vision_fallback: bool) -> list[Resume]:
    """Extract text from image-based resumes (scanned PDFs, image files).

    Tesseract OCR is the first choice: it is local and takes seconds. The
    model's vision input is the fallback (behind --ocr) since transcribing a
    page can take minutes on partial GPU offload. Either way the resulting
    text is scored in a fresh call like any other resume; resumes that still
    have no text afterwards are dropped.
    """
    usable: list[Resume] = []
    use_tesseract = any(r.needs_ocr for r in resumes) and tesseract_available()
    for resume in resumes:
        if not resume.needs_ocr:
            usable.append(resume)
            continue
        if use_tesseract:
            print(f"OCR-ing image-based resume {resume.name} with Tesseract ...")
            try:
                resume.text = ocr_with_tesseract(resume.path)
            except Exception as exc:
                print(f"[warn] Tesseract OCR of {resume.name} failed: {exc}")
        if not resume.text.strip() and vision_fallback:
            print(f"Transcribing {resume.name} with the model's vision input (this can take minutes) ...")
            try:
                if resume.path.suffix.lower() == ".pdf":
                    pages = [llm.transcribe_image(image) for image in pdf_page_images(resume.path)]
                else:
                    mime = guess_mime_type(resume.name)
                    pages = [llm.transcribe_image(resume.path.read_bytes(), mime_type=mime)]
                resume.text = "\n".join(pages)
            except Exception as exc:
                print(f"[warn] transcription of {resume.name} failed: {exc}")
        if resume.text.strip():
            usable.append(resume)
        else:
            print(
                f"[note] Skipping image-based {resume.name}: install Tesseract for fast local OCR, "
                "or rerun with --ocr to transcribe it with the model."
            )
    return usable


def match_job(
    llm: LocalLLM,
    job: JobPosting,
    resumes: list[Resume],
    top_n: int,
    progress: Progress,
) -> list[MatchResult]:
    """Score all resumes against one job posting and return the top N results."""
    results: list[MatchResult] = []
    for resume in resumes:
        print(f"  {progress.tick()} scoring {resume.name} ...")
        try:
            results.append(score_resume(llm, job, resume))
        except Exception as exc:  # keep going if one call fails
            print(f"  [warn] failed to score {resume.name}: {exc}")
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_n]


def run(config: Config, jobs: list[JobPosting], resumes: list[Resume]) -> dict[str, list[MatchResult]]:
    """Run the full matching pipeline. Returns {job source: top-N results}."""
    llm = LocalLLM(config)
    resumes = transcribe_resumes(llm, resumes, vision_fallback=config.ocr)
    progress = Progress(total=len(jobs) * len(resumes))
    top_matches: dict[str, list[MatchResult]] = {}
    for job in jobs:
        print(f"\nJob: {job.title} ({job.source})")
        top_matches[job.source] = match_job(llm, job, resumes, config.top_n, progress)
    return top_matches
