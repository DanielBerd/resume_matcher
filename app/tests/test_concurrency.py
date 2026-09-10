"""Tests for concurrent scoring: correctness, speed, and thread safety.

Uses a fake LLM that sleeps, so no model or server is involved.
"""

import time
from pathlib import Path

from resume_matcher.documents import Resume
from resume_matcher.email_ingest import JobPosting
from resume_matcher.matcher import Progress, match_job

JOB = JobPosting(source="j.txt", title="Job", body="Need an engineer.")


class SleepyLLM:
    """Returns a score derived from the resume text after a fixed delay."""

    def __init__(self, delay=0.05, fail_for=()):
        self.delay = delay
        self.fail_for = set(fail_for)

    def complete(self, system_prompt, user_prompt):
        time.sleep(self.delay)
        for name in self.fail_for:
            if name in user_prompt:
                raise RuntimeError("model exploded")
        score = 90 if "senior" in user_prompt else 40
        return '{"score": %d, "comment": "ok"}' % score


def _resumes(n):
    return [Resume(path=Path(f"r{i}.pdf"), text="senior" if i == 0 else "junior") for i in range(n)]


def test_concurrent_scores_every_resume():
    resumes = _resumes(8)
    progress = Progress(len(resumes))
    results = match_job(SleepyLLM(), JOB, resumes, top_n=10, progress=progress, concurrency=4)

    assert len(results) == 8
    assert progress.done == 8                       # no lost ticks across threads
    assert {r.resume.name for r in results} == {f"r{i}.pdf" for i in range(8)}
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


def test_concurrency_is_faster_than_sequential():
    resumes = _resumes(8)
    llm = SleepyLLM(delay=0.05)

    start = time.perf_counter()
    match_job(llm, JOB, resumes, 10, Progress(8), concurrency=1)
    sequential = time.perf_counter() - start

    start = time.perf_counter()
    match_job(llm, JOB, resumes, 10, Progress(8), concurrency=4)
    concurrent = time.perf_counter() - start

    # 8 x 50ms serially is ~0.4s; with 4 workers it should be roughly a
    # quarter of that. Allow generous slack for scheduling noise.
    assert concurrent < sequential / 2


def test_failures_do_not_stop_the_rest():
    resumes = _resumes(6)
    llm = SleepyLLM(delay=0.01, fail_for=("junior",))  # every resume but r0
    progress = Progress(6)
    results = match_job(llm, JOB, resumes, 10, progress, concurrency=3)

    assert [r.resume.name for r in results] == ["r0.pdf"]
    assert progress.done == 6      # failures still count toward progress


def test_ties_order_deterministically():
    # All resumes score the same; order must not depend on reply arrival.
    resumes = [Resume(path=Path(n), text="junior") for n in ("c.pdf", "a.pdf", "b.pdf")]
    runs = [
        [r.resume.name for r in match_job(SleepyLLM(0.01), JOB, list(resumes), 10, Progress(3), concurrency=3)]
        for _ in range(3)
    ]
    assert runs[0] == ["a.pdf", "b.pdf", "c.pdf"]
    assert runs[0] == runs[1] == runs[2]
