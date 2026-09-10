# resume_matcher

Scaffolding for a local, private resume-to-job matcher. It scores every resume in a
folder against each job posting using a local Gemma 4 model served by
[Unsloth Desktop](https://unsloth.ai/), then reports the top 5 matches per
job. Everything runs on your own machine; nothing leaves it.

## Workflow

1. **Job postings arrive by email.** For now, save each posting into the `jobs/`
   folder as a `.txt` or `.eml` file (live IMAP fetching is stubbed in
   `resume_matcher/email_ingest.py`).
2. **Resumes live in a folder** (`resumes/` by default) as `.pdf`, `.docx`, or `.doc`.
3. For every job posting, each resume is sent to Gemma with the posting and the
   model returns a 0–100 match score plus a one-sentence comment.
4. Scores are collected and the **top 5 resumes per job** are reported.

## Setup

You need two things installed: **Python 3.10 or newer** (from
[python.org](https://www.python.org/downloads/); on Windows tick *Add Python to
PATH*) and **Unsloth Desktop** with a model loaded. That's it - no `pip`, no
virtual environments. The first time you run a launcher it creates a private
environment next to the code and installs everything into it, showing progress
in a small window (a minute or two); after that it opens straight away.

In Unsloth Desktop:

1. Download one of the supported Gemma 4 QAT models (pick by the memory you
   have - VRAM, or RAM if running on CPU):

   | Model | Needs roughly | When to pick it |
   | --- | --- | --- |
   | `gemma-4-e4b-it-qat` | ~6 GB | Small GPUs (6-8 GB) or CPU-only. Fastest; least discerning. |
   | `gemma-4-12b-it-qat` | ~12 GB | The default. Ranks the bundled examples correctly. |
   | `gemma-4-26b-a4b-it-qat` | ~24 GB | Best quality. Mixture-of-experts with ~4B active, so it still decodes quickly once loaded. |

   The sizes are approximate and include room for the context length the tool
   needs (see *Throughput* below). If a model fails to load or falls back to
   CPU, step down one row.
2. Load the model and start Unsloth Desktop's local server.
3. Check the server address it shows. The tool assumes
   `http://localhost:8888/v1`; if yours differs, enter it on the window's
   *Server* tab, or set `RM_LLM_BASE_URL` / pass `--base-url` - **including
   the `/v1` suffix**.

The tool preselects whichever loaded model's id contains the configured name
(`gemma-4-12b` by default, `RM_LLM_MODEL` to change), so the exact id the
server reports does not need to be typed in.

Note: `.doc` (legacy Word) files additionally need `antiword` or LibreOffice
installed; `.pdf` and `.docx` work out of the box.

## Usage

Put your resumes in `resumes/`, then double-click **`run_gui.pyw`** (Windows;
`run_gui.bat` also works but blinks a console for a moment) or run
`python run_gui.py` (macOS / Linux). A window opens:

![The Resume Matcher window](docs/gui_window.png)

*(Captured on Linux; on Windows the layout is the same but the controls use
native Windows styling.)*

- **Drop a job posting** (`.txt`, `.eml`, `.pdf`, `.docx`) on the drop zone to
  score that one job against every resume in `resumes/`. Clicking the zone
  opens a file browser instead.
- **"Run all jobs in jobs/ folder"** does the regular matching over every
  posting in `jobs/`.
- Pick the model from the dropdown (populated from the server), watch progress
  and log output live, and the HTML report opens automatically when finished.

On Windows the launcher starts the app with `pythonw`, so you get just the
window with no console behind it; if it cannot start, the reason appears in a
dialog box.

#### Server tab: local server or hosted API

The *Server* tab decides where the model runs. Pick a preset and the fields
fill in:

- **Local server** - Unsloth Desktop (default) or any other OpenAI-compatible
  server on this machine. Nothing leaves the computer. *Fetch models* lists
  what the server has loaded and preselects the configured one.
- **Hosted API** - OpenAI, OpenRouter, Groq, or a custom OpenAI-compatible
  endpoint. Paste your API key and type the model id (hosted catalogs are
  too large to pick from). A notice on the tab spells out the trade-off:
  **job postings and the full text of every resume are sent to that
  provider.** Use it knowingly - resumes are personal data.

*Test connection* checks the address and key. *Save* writes the tab to
`settings.json` next to the launchers; every run also saves it, so what you
see is what runs. The file is gitignored because it can contain an API key.

If the window cannot reach the model server, the *Server* tab gets a red dot
and the line at the top of the *Match* tab turns red; clicking it takes you to
the Server tab. Runs also check the connection first, so a stopped server
fails immediately with that highlight rather than after scoring every resume.

Everything speaks the same OpenAI-compatible API, so the command line works
against hosted providers too: set `RM_LLM_BASE_URL`, `RM_LLM_API_KEY`, and
`RM_LLM_MODEL` (or just use the values saved from the GUI, which the CLI
reads as well). The preset model ids are starting points; providers rename
models often, so check their current lists.

Drag-and-drop needs the optional `tkinterdnd2` package from
`requirements.txt`; without it the drop zone still works as click-to-browse.
The window itself needs tkinter, which ships with Python on Windows and macOS
(on Linux: `sudo apt install python3-tk`).

### Console launcher

`run_matcher.bat` / `run_matcher.py` does the same as the window's *Run all
jobs* button without a window: it scores everything in `jobs/`, opens the HTML
report, and keeps the console open so you can read any messages. It sets up
the environment on first run just like the window does.

### Command line

For flags and test mode, use the module form from inside the environment the
launchers created (`.venv/Scripts/python` on Windows, `.venv/bin/python`
elsewhere), or your own if you prefer to manage it yourself:

```bash
.venv/bin/python -m resume_matcher --jobs jobs/ --resumes resumes/
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

Before matching starts, the tool queries the server for the loaded models and
asks you to pick one (auto-selected when only one is loaded, or when running
non-interactively). Pass `--model NAME` to skip the picker.

Options: `--top N` (default 5), `--model NAME`, `--base-url URL`.

Settings layer in this order, later ones winning: built-in defaults, then
`settings.json` (written by the GUI's Server tab), then environment variables
(`RM_LLM_BASE_URL`, `RM_LLM_API_KEY`, `RM_LLM_MODEL`, `RM_CONCURRENCY`), then
command-line flags. See `resume_matcher/config.py`.

## Throughput (concurrent scoring)

Scoring calls are independent, so the tool keeps several in flight at once and
lets the server batch them. This is a large speed-up on GPU: in a local
benchmark against a mock server, a 30-call run went from 12.3s to 4.3s.

Each request still contains exactly one job and one resume, so concurrency
changes only how many are in flight - never what the model sees.

Set it with `-j` / `--concurrency` (default 4, `1` for sequential), or the
`RM_CONCURRENCY` environment variable:

```bash
python -m resume_matcher -j 4
```

**Matching settings in Unsloth Desktop** (in the model/server settings;
reload the model after changing them). The exact labels may differ, but the
two that matter are:

- **Parallel requests / concurrent slots** - must be >= your `-j` value (4),
  or the extra requests just queue on the server and you gain nothing.
- **Context length** - llama.cpp-based servers divide the context across
  concurrent slots, so the per-request budget is roughly
  `context length / parallel slots`. A job + resume + reply needs ~3-4k
  tokens, so for 4 slots set the context to **16384**. If replies start coming
  back empty or truncated after raising concurrency, this is the cause: raise
  the context or lower `-j`.

Also put as many layers on the GPU as fit: batching wins come from the GPU
decoding several sequences at once, and a mostly-CPU model gains much less.
If the server offers flash attention or GPU KV-cache options, leave them on.

Note that resumes are scored concurrently *within* a job, while jobs are
processed one after another, so a run with many jobs and few resumes will not
saturate a high `-j`.

## Comparing models

To decide between models (say a smaller, faster one vs a larger one), run both
over the same data and compare side by side:

```bash
python -m resume_matcher.compare --test-mode gemma-4-12b-it-qat gemma-4-e4b-it-qat
```

It scores every resume against every job with each model in turn, then writes
`results/compare_<timestamp>.html`: a per-job table of each model's score and
rank for every resume, the score delta between two models, a note on whether
they agree on the top-N ranking, and a speed summary (total and per-call time).
Pass `--jobs`/`--resumes` to compare on your own data instead of the examples.

## Watching an Outlook inbox

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
| `resume_matcher/llm_client.py` | Talk to Unsloth Desktop's OpenAI-compatible server |
| `resume_matcher/scoring.py` | Match prompt + robust parsing of the model's score/comment |
| `resume_matcher/matcher.py` | Loop jobs × resumes, sort, keep top N |
| `resume_matcher/report.py` | Print top matches and save HTML/text/JSON reports |
| `resume_matcher/compare.py` | Score the set with multiple models and report them side by side |
| `resume_matcher/cli.py` | Command-line entry point |
| `resume_matcher/gui.py` | Desktop window: Match tab (drag-and-drop / run folder) and Server tab |
| `resume_matcher/providers.py` | Presets for the Server tab (local servers and hosted APIs) |
| `bootstrap.py` | First-run setup shared by the launchers: create `.venv`, install requirements, relaunch |
| `run_matcher.py` | Double-click launcher (runs the tool, opens the report) |
| `run_matcher.bat` | Windows double-click launcher (finds Python, runs `run_matcher.py`) |
| `watch_inbox.py` / `.bat` | Launchers for the Outlook inbox watcher |
| `run_gui.py` / `.pyw` / `.bat` | Launchers for the desktop window (`.pyw`: no console at all on Windows) |

## Tests

```bash
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest
```

## Next steps (not yet implemented)

- Live IMAP email fetching (`fetch_jobs_from_imap` stub)
