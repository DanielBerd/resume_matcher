"""Tests for the model-comparison report logic, using fabricated runs.

No LM Studio involved: ModelRun objects are built by hand and fed to the pure
report functions.
"""

from pathlib import Path

from resume_matcher.compare import ModelRun, _agreement, format_comparison_html
from resume_matcher.documents import Resume
from resume_matcher.email_ingest import JobPosting
from resume_matcher.scoring import MatchResult


def _run(model, job, scores, elapsed=10.0):
    """scores: {resume_name: score} -> a ModelRun for one job."""
    mr = {
        name: MatchResult(job=job, resume=Resume(path=Path(name), text=""), score=s, comment="c")
        for name, s in scores.items()
    }
    return ModelRun(model=model, elapsed=elapsed, calls=len(scores), scores={job.source: mr})


def test_ranked_sorts_descending():
    job = JobPosting(source="j", title="J", body="")
    run = _run("m", job, {"a.pdf": 40, "b.pdf": 90, "c.pdf": 60})
    order = [r.resume.name for r in run.ranked("j")]
    assert order == ["b.pdf", "c.pdf", "a.pdf"]
    assert run.rank_of("j", "b.pdf") == 1
    assert run.rank_of("j", "a.pdf") == 3


def test_agreement_identical():
    job = JobPosting(source="j", title="J", body="")
    r1 = _run("m1", job, {"a.pdf": 90, "b.pdf": 50})
    r2 = _run("m2", job, {"a.pdf": 80, "b.pdf": 40})  # same order
    assert "identical" in _agreement([r1, r2], "j", top_n=5)


def test_agreement_different_order():
    job = JobPosting(source="j", title="J", body="")
    r1 = _run("m1", job, {"a.pdf": 90, "b.pdf": 50})
    r2 = _run("m2", job, {"a.pdf": 40, "b.pdf": 80})  # flipped
    msg = _agreement([r1, r2], "j", top_n=5)
    assert "different order" in msg


def test_html_has_both_models_and_delta():
    job = JobPosting(source="j", title="Backend Role", body="")
    resumes = [Resume(path=Path("a.pdf"), text=""), Resume(path=Path("b.pdf"), text="")]
    r1 = _run("gemma-12b", job, {"a.pdf": 90, "b.pdf": 50})
    r2 = _run("gemma-e4b", job, {"a.pdf": 70, "b.pdf": 55})
    out = format_comparison_html([r1, r2], [job], resumes, top_n=5, stamp="now")
    assert "gemma-12b" in out and "gemma-e4b" in out
    assert "Backend Role" in out
    assert "-20" in out   # a.pdf: 70 - 90
    assert "+5" in out    # b.pdf: 55 - 50
