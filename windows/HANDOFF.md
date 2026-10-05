# Handoff brief — `windows-native` branch

You are picking this up cold. This file is the context you would otherwise have
to re-derive. Read it before changing anything; `README.md` next to it describes
the app itself.

**Branch:** `windows-native` (commit `56a2409`) · **Baseline:** `main` (`c5c586b`)
**Owner:** Daniel (`DanielBerd/resume_matcher`)

---

## 1. What this is

`main` holds a working Python/tkinter app: it scores every resume in a folder
against each job posting using a local Gemma model over an OpenAI-compatible
API, and reports the top 5 per job. It works, but it requires the user to
install Python, and a long tail of Windows problems came with that.

This branch is an experiment: the same tool rebuilt in C#, shipping as one
self-contained `ResumeMatcher.exe` that needs neither Python nor .NET on the
machine. `main` is untouched and still the shipping version. Nothing has been
merged and no decision to merge has been made.

```
windows/
  src/ResumeMatcher.Core/     all logic, plain net8.0, no UI and no Windows types
  src/ResumeMatcher.App/      the window (Avalonia), ~400 lines of glue
  tests/ResumeMatcher.Tests/  42 tests, run on any OS
  installer/ResumeMatcher.iss Inno Setup script
  docs/                       screenshots (taken on Linux — see §4)
.github/workflows/windows-build.yml   builds exe + installer on a Windows runner
```

`Core` is deliberately free of UI and platform types. That is what makes the
logic testable anywhere, and what would let the UI be replaced without touching
the logic. Keep it that way.

## 2. Environment

Built with .NET SDK **8.0.131**, Avalonia **11.3.22**, PdfPig **0.1.16**.

```bash
dotnet test tests/ResumeMatcher.Tests                      # 42 tests
dotnet publish src/ResumeMatcher.App -p:PublishProfile=win-x64
```

Publish output: `src/ResumeMatcher.App/bin/publish/win-x64/ResumeMatcher.exe`,
46,693,548 bytes, confirmed `PE32+ executable (GUI) x86-64`.

The installer needs Windows: `ISCC.exe installer\ResumeMatcher.iss`.

## 3. Why the UI is Avalonia and not WPF/WinUI 3

This is the decision most likely to be revisited, so here is the actual reason.

It was **partly forced**. The work was done in a Linux sandbox where
`builds.dotnet.microsoft.com` is blocked by network policy and Ubuntu's
`dotnet-sdk-8.0` package strips the Windows Desktop SDK targets, so
`Microsoft.NET.Sdk.WindowsDesktop.targets` was simply absent and WPF could not
be cross-built at all. (`EnableWindowsTargeting=true` gets you past the first
error; the missing targets file is the wall.)

It was **partly chosen**: Avalonia builds *and runs* on Linux, so the UI could be
driven end to end against a mock server and every screenshot is of the real
application rather than unrun code.

Architecturally it is the same kind of toolkit as WPF — both draw their own
Fluent-styled controls rather than wrapping Win32 common controls — so "native
look" holds. But it is not first-party Microsoft UI.

**On Windows this constraint disappears.** If the owner wants WinUI 3 or WPF,
rewrite `ResumeMatcher.App` only; `Core` carries over untouched. That is the
whole reason for the split.

## 4. Verified vs. assumed — read this before claiming anything works

Everything below was run in a Linux sandbox. **The app has never been run on
Windows.**

### Actually executed and observed

- `Core` builds clean; **42/42 tests pass** against a real loopback HTTP server
  (`tests/.../FakeServer.cs`), not a mocked handler.
- Text extraction against the 5 real sample resumes (PDF + DOCX) and 5 job
  postings (including `.eml`) from `app/examples/` on `main`. Non-ASCII
  (`Malmö`) survives.
- The window runs; light and dark variants both render correctly.
- **Full end-to-end run through the real UI** against a mock model server:
  clicked *Run all jobs*, 5 jobs × 5 resumes = **25 requests, no duplicates**,
  live progress, HTML report written and correct (score badges, `file://`
  links, HTML escaping).
- Server tab auto-fetches models on launch and reports `Connected — 2 model(s)`.
- Publish produces a single PE32+ GUI executable.

### Assumed, never verified

- That it runs on Windows at all.
- **Font rendering.** Linux has no Segoe UI, so the screenshots in `docs/` fall
  back to DejaVu. Windows will look different — better — but unconfirmed.
- **Taskbar icon and `Pin to taskbar`.** The installer sets `AppUserModelID`;
  untested. See §6 for why this specific thing is fragile.
- Title-bar dark mode, and the `app.manifest` per-monitor DPI awareness.
- **The installer has never been compiled** — no Inno Setup in the sandbox. The
  `.iss` is unrun code. Treat it as a draft.
- **The CI workflow has never run.**
- Drag-and-drop from Explorer (only the click-to-browse path was exercised).
- The Windows file picker, and `Process.Start(UseShellExecute: true)` for
  *Open folders* / *Open last report*.
- Theme following the Windows app mode. `RequestedThemeVariant="Default"` should
  do it, but Linux has no app mode to follow, so it was never observed working.
  `RM_FORCE_THEME=Light|Dark` exists as a documentation aid for capturing both.

## 5. Decisions already made — do not "fix" these

These were settled with the owner over a long thread. Each looks like something
an agent would helpfully change, and changing it is a regression.

- **A timed-out request is NEVER resent.** This is the single most important
  rule in the codebase. The server is probably still working on it; a resend
  doubles load and produces a reply nobody reads. Only a 429/503 — where the
  request was *refused outright* — is retried, with backoff. This came from a
  real bug on `main` where SDK auto-retries caused duplicate requests and
  ignored ratings. Do not add retries "for robustness."
- **One job + one resume per request, always a fresh context.** An explicit
  owner requirement: resumes must never be mixed. Do not batch them, do not
  reuse conversation history. `LlmClientTests` asserts this.
- **Requests are sent buffered, not via `PostAsJsonAsync`.** That serialises
  lazily, so the body goes out chunked with no `Content-Length`; some
  OpenAI-compatible servers and API gateways reject that. Found by observation,
  not theory.
- **Ties break by resume name** so two runs of the same data agree.
- **Top 5 per job**, concurrency default **4**.
- **The GUI is the only entry point.** `main` had a CLI, a console launcher and
  an Outlook inbox watcher; all were deliberately deleted to cut complexity.
  Do not add a CLI back.
- **Working folders live in `Documents\Resume Matcher`**, settings in
  `%APPDATA%\ResumeMatcher\settings.json` — an app in `Program Files` cannot
  write next to itself.
- **Azure preset targets the OpenAI-compatible `/openai/v1` endpoint.** The
  classic `?api-version=` endpoint uses an `api-key:` header instead of
  `Authorization: Bearer` and this client cannot talk to it.

## 6. Gotchas already hit — don't rediscover them

- **Never hand-write `InitializeComponent()` in an Avalonia window.** It shadows
  the XAML-compiler-generated one that assigns the `x:Name` fields, so every
  control reference is null and the constructor throws `NullReferenceException`.
  Cost an hour.
- **Don't use WinUI resource keys** (`LayerFillColorDefaultBrush` etc.) with
  `DynamicResource` — they silently fail to resolve, leaving invisible borders
  and, where used for `Foreground`, invisible text. The app defines its own
  palette in `App.axaml` under `ThemeDictionaries`. Use those keys, via the
  `Brush(string)` helper which falls back rather than returning null.
- **Don't put `RuntimeIdentifier` in the `.csproj`.** It makes `dotnet run`
  build a Windows binary that won't execute on the dev machine. It lives in
  `Properties/PublishProfiles/win-x64.pubxml`.
- **Taskbar pinning is not automatic.** Windows groups taskbar buttons by
  application id. Pinning a running window only works if a Start Menu shortcut
  carries the *same* `AppUserModelID` the process declares — otherwise Windows
  pins the bare executable, showing a generic icon and launching nothing. On
  `main` this took three attempts. The `.iss` sets `AppUserModelID` on both
  shortcuts; the value must stay in sync with whatever the app declares.

## 7. Candidate next moves

In the order I would do them.

### a. Run the CI workflow (cheapest, do first)
`.github/workflows/windows-build.yml` builds the exe, runs the tests and
compiles the installer on `windows-latest`. It has never run, so expect it to
need fixing — the Inno Setup invocation is the likeliest failure, and the runner
may not have Inno Setup preinstalled (add a `choco install innosetup` step if
not). Green CI confirms everything except how the app feels.

### b. Verify the installed app by hand
Install it, then check the §4 "assumed" list: fonts, taskbar icon, *Pin to
taskbar*, dark title bar, DPI scaling at 125%/150%, drag-and-drop from Explorer,
and what SmartScreen says about an unsigned download. These are visual and
interactive; screenshots are the deliverable.

### c. Add OCR with `Windows.Media.Ocr`
The most valuable feature gap. Scanned PDFs and image resumes are currently
skipped. `Windows.Media.Ocr` is built into Windows 10+, so this would make the
C# version *better* than `main`, which needs a separate Tesseract install.
Needs a `net8.0-windows10.0.19041.0` target — which means it belongs in a
Windows-only project, not in `Core`. Suggested shape: an `IOcrEngine` interface
in `Core` with the Windows implementation injected by `App`, so `Core` stays
cross-platform and testable. `Windows.Data.Pdf` can render PDF pages to
bitmaps to feed it.

### d. Decide the UI toolkit
Only worth doing if the owner wants first-party Microsoft UI. See §3. Rewrite
`ResumeMatcher.App` against `Core`; budget for re-doing the theming and
drag-and-drop, and re-verify everything in §4.

### e. Code signing
Out of scope until someone decides to pay for a certificate. An unsigned
downloaded `.exe` trips SmartScreen; a locally built one does not. The owner has
already decided to skip this once on `main`.

## 8. Working agreements

- **Commits are authored `Daniel <daniel.ber@outlook.com>`** with Claude as
  co-author. Set `user.name` / `user.email` before committing — a fresh
  container will not have them. The owner's other email address must never
  appear in git history; it was deliberately rewritten out.
- Commit message trailer, matching the existing history:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- `main` is trunk-based — the owner pushes straight to it and does not want
  feature branches there. This branch is the explicit exception, created on
  request for an experiment.
- Do not open a pull request unless asked.
- The owner values being told plainly what was verified and what was not. If you
  could not run something, say so rather than implying it works.
