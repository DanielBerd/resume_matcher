# resume_matcher

Scaffolding for a local, private resume-to-job matcher. It scores every resume in a
folder against each job posting using a local Gemma model
(`google/gemma-4-12b-qat`) served by [LM Studio](https://lmstudio.ai/), then
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

1. Download and load `google/gemma-4-12b-qat`.
2. Start the local server (default `http://localhost:1234/v1`).

Note: `.doc` (legacy Word) files additionally need `antiword` or LibreOffice
installed; `.pdf` and `.docx` work out of the box.

## Usage

The simplest way to run it: put your job postings in `jobs/` and resumes in
`resumes/`, then run the launcher. It scores everything, opens the HTML report
in your browser, and keeps the window open so you can read any messages.

- **Windows:** double-click **`run_matcher.bat`**.
- **macOS / Linux:** double-click or run **`run_matcher.py`** (`python run_matcher.py`).

For flags and test mode, use the module form directly:

```bash
python -m resume_matcher --jobs jobs/ --resumes resumes/
```

By default the tool reads real inputs from `jobs/` and `resumes/`. To try the
pipeline without any real data, run in test mode, which uses the bundled
sample job postings and resumes in `examples/`:

```bash
python -m resume_matcher --test-mode
```

The examples include five job postings (one as a saved `.eml` email) and five
resumes in PDF/DOCX format with deliberately varied fit — a strong match for
each job, a generalist, and a marketing resume that should score low across
the board — so you can eyeball whether the model's rankings make sense.

While running, each scoring line shows overall progress across all
job × resume pairs. Results are printed and also saved under `results/`
(gitignored, one timestamped set per run) in three formats: an HTML report,
plain text, and JSON. Open the `.html` file in a browser for a readable
summary — each job is an expandable section listing its top matches with
color-coded score badges, and every resume name links to the source file on
disk.

Scanned PDFs with no text layer, and plain image files (.png/.jpg/.webp), are
OCR-ed with [Tesseract](https://github.com/tesseract-ocr/tesseract)
automatically when it is installed (seconds per page, fully offline; see
requirements.txt for install pointers — on Windows the default install
location is auto-detected). If Tesseract is unavailable, pass `--ocr` to fall
back to transcribing the image with the model's vision input instead — no
extra install, but minutes per page on partial GPU offload, and it requires a
vision-capable model. Either way the extracted text is scored in a fresh
call, like any other resume; with neither option available, image-based
resumes are skipped with a note.

Before matching starts, the tool queries LM Studio for the loaded models and
asks you to pick one (auto-selected when only one is loaded, or when running
non-interactively). Pass `--model NAME` to skip the picker.

Options: `--top N` (default 5), `--model NAME`, `--base-url URL`. Environment
variables `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL` are also honored (see
`resume_matcher/config.py`).

## Comparing models

To decide between models (say a smaller, faster one vs a larger one), run both
over the same data and compare side by side:

```bash
python -m resume_matcher.compare --test-mode google/gemma-4-12b-qat google/gemma-4-e4b
```

It scores every resume against every job with each model in turn, then writes
`results/compare_<timestamp>.html`: a per-job table of each model's score and
rank for every resume, the score delta between two models, a note on whether
they agree on the top-N ranking, and a speed summary (total and per-call time).
Pass `--jobs`/`--resumes` to compare on your own data instead of the examples.

Instead of saving postings to `jobs/` by hand, the tool can watch your Outlook
inbox: when a job email arrives it scores every resume against it and emails
the ranked results back to your own mailbox (the account being watched), so
the matches land in the same inbox.

Start it by double-clicking **`watch_inbox.bat`** (Windows) or running
`python watch_inbox.py`. It polls the inbox on an interval and keeps running
until you close the window.

**Requirements and limits** — this uses the *classic* Outlook desktop app
through COM automation, so it uses your already-signed-in mailbox with no
passwords or setup:

- **Native Windows only** — it does not work under WSL, macOS, or Linux.
- The **classic** Outlook desktop app must be installed and configured; the
  newer "Outlook for Windows" app does not expose COM automation.
- Needs `pywin32`, installed automatically on Windows by `requirements.txt`.

Useful settings (flags to `watch_inbox.py` / `python -m resume_matcher.email_watch`,
or the matching `RM_*` environment variables):

- `--subject-filter TEXT` — only process unread emails whose subject contains
  TEXT (e.g. `--subject-filter "[job]"`), so not every email is treated as a
  posting. Default: every unread email.
- `--to ADDRESS` — send all results to a fixed address instead of back to the
  monitored mailbox.
- `--interval SECONDS` — how often to poll (default 60).

## Project layout

| Module | Responsibility |
| --- | --- |
| `resume_matcher/email_ingest.py` | Load job postings from `jobs/` folder; IMAP fetch stub |
| `resume_matcher/outlook.py` | Read/send mail via the Windows Outlook desktop app (COM) |
| `resume_matcher/email_watch.py` | Poll the inbox, match each job email, reply with results |
| `resume_matcher/documents.py` | Extract text from PDF/DOCX/DOC resumes |
| `resume_matcher/llm_client.py` | Talk to LM Studio's OpenAI-compatible server |
| `resume_matcher/scoring.py` | Match prompt + robust parsing of the model's score/comment |
| `resume_matcher/matcher.py` | Loop jobs × resumes, sort, keep top N |
| `resume_matcher/report.py` | Print top matches and save HTML/text/JSON reports |
| `resume_matcher/compare.py` | Score the set with multiple models and report them side by side |
| `resume_matcher/cli.py` | Command-line entry point |
| `run_matcher.py` | Double-click launcher (runs the tool, opens the report) |
| `run_matcher.bat` | Windows double-click launcher (finds Python, runs `run_matcher.py`) |
| `watch_inbox.py` / `.bat` | Launchers for the Outlook inbox watcher |

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
