"""Orchestration: score every resume against every job and keep the top N.

Step 4 of the workflow: collect ratings per job, then report the top 5.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import Config
from .documents import Resume, ocr_with_tesseract, pdf_page_images, tesseract_available
from .email_ingest import JobPosting
from .llm_client import LocalLLM, guess_mime_type
from .scoring import MatchResult, score_resume


class Progress:
    """Counter for overall progress across all job x resume pairs.

    Ticked from worker threads when scoring concurrently, so it takes a lock.
    """

    def __init__(self, total: int):
        self.total = total
        self.done = 0
        self._lock = threading.Lock()

    def tick(self) -> str:
        with self._lock:
            self.done += 1
            done = self.done
        percent = 100 * done // self.total if self.total else 100
        return f"[{done}/{self.total} total, {percent}%]"


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
    concurrency: int = 1,
) -> list[MatchResult]:
    """Score all resumes against one job posting and return the top N results.

    With concurrency > 1 several resumes are scored at once. Each request is
    still a separate, stateless call containing only this job and one resume -
    concurrency changes how many are in flight, never what the model sees.
    """
    lock = threading.Lock()
    results: list[MatchResult] = []

    def score_one(resume: Resume) -> None:
        try:
            result = score_resume(llm, job, resume)
        except Exception as exc:  # keep going if one call fails
            print(f"  {progress.tick()} [warn] failed to score {resume.name}: {exc}")
            return
        with lock:
            results.append(result)
        print(f"  {progress.tick()} {resume.name}: {result.score}/100")

    if concurrency > 1:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(score_one, resume) for resume in resumes]
            for future in as_completed(futures):
                future.result()  # surface unexpected errors in score_one itself
    else:
        for resume in resumes:
            score_one(resume)

    # Sort by score, then name, so equal scores order deterministically
    # regardless of the order concurrent replies arrived in.
    results.sort(key=lambda r: (-r.score, r.resume.name))
    return results[:top_n]


def run(config: Config, jobs: list[JobPosting], resumes: list[Resume]) -> dict[str, list[MatchResult]]:
    """Run the full matching pipeline. Returns {job source: top-N results}."""
    llm = LocalLLM(config)
    resumes = transcribe_resumes(llm, resumes, vision_fallback=config.ocr)
    progress = Progress(total=len(jobs) * len(resumes))
    top_matches: dict[str, list[MatchResult]] = {}
    for job in jobs:
        print(f"\nJob: {job.title} ({job.source})")
        top_matches[job.source] = match_job(
            llm, job, resumes, config.top_n, progress, config.concurrency
        )
    return top_matches
