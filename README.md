# resume_matcher

Scaffolding for a local, private resume-to-job matcher. It scores every resume in a
folder against each job posting using a local Gemma model
(`google/gemma-4-26b-a4b-qat`) served by [LM Studio](https://lmstudio.ai/), then
reports the top 5 matches per job.

## Workflow

1. **Job postings arrive by email.** For now, save each posting into the `jobs/`
   folder as a `.txt` or `.eml` file (live IMAP fetching is stubbed in
   `resume_matcher/email_ingest.py`).
2. **Resumes live in a folder** (`resumes/` by default) as `.pdf`, `.docx`, or `.doc`.
3. For every job posting, each resume is sent to Gemma with the posting and the
   model returns a 0–100 match score plus a one-sentence comment.
4. Scores are collected and the **top 5 resumes per job** are reported.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then in LM Studio:

1. Download and load `google/gemma-4-26b-a4b-qat`.
2. Start the local server (default `http://localhost:1234/v1`).

Note: `.doc` (legacy Word) files additionally need `antiword` or LibreOffice
installed; `.pdf` and `.docx` work out of the box.

## Usage

```bash
python -m resume_matcher --jobs jobs/ --resumes resumes/
```

By default the tool reads real inputs from `jobs/` and `resumes/`. To try the
pipeline without any real data, run in test mode, which uses the bundled
sample job postings and resumes in `examples/`:

```bash
python -m resume_matcher --test-mode
```

The examples include four job postings (one as a saved `.eml` email) and five
resumes in PDF/DOCX format with deliberately varied fit — a strong match for
each job, a generalist, and a marketing resume that should score low across
the board — so you can eyeball whether the model's rankings make sense.

Options: `--top N` (default 5), `--model NAME`, `--base-url URL`. Environment
variables `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL` are also honored (see
`resume_matcher/config.py`).

## Project layout

| Module | Responsibility |
| --- | --- |
| `resume_matcher/email_ingest.py` | Load job postings from `jobs/` folder; IMAP fetch stub |
| `resume_matcher/documents.py` | Extract text from PDF/DOCX/DOC resumes |
| `resume_matcher/llm_client.py` | Talk to LM Studio's OpenAI-compatible server |
| `resume_matcher/scoring.py` | Match prompt + robust parsing of the model's score/comment |
| `resume_matcher/matcher.py` | Loop jobs × resumes, sort, keep top N |
| `resume_matcher/report.py` | Print top matches per job |
| `resume_matcher/cli.py` | Command-line entry point |

## Tests

```bash
pip install pytest
pytest
```

## Next steps (not yet implemented)

- Live IMAP email fetching (`fetch_jobs_from_imap` stub)
- Persisting scores to SQLite between runs
- Truncation/chunking for resumes or postings that exceed the model context
- Optional web UI (Streamlit/Gradio)
