# Resume Matcher — web version

A third take on the tool, on the `web` branch: **plain HTML, CSS and JavaScript**,
no build step, no framework, no backend of its own. Everything runs in the
browser and talks to an OpenAI-compatible model server. Built to be hosted on a
home server and used from any device on the network, including a phone.

![Results](docs/results.png)

## Why this one is different

The desktop versions read a folder and run on one machine. This one runs
wherever you open it, and **nothing is installed on the client at all**.

Resumes are parsed in the browser — the files themselves are never uploaded
anywhere. Only the extracted text goes to the model server, exactly as in the
desktop versions, one job and one resume per request.

## The one thing that decides your setup: origins

A browser blocks a page on one origin from calling an API on another unless
that API sends CORS headers. I verified this in Chromium against a mock server:

```
model server WITHOUT CORS headers: blocked — "Response to preflight request
                                   doesn't pass access control check"
model server WITH    CORS headers: works
```

So you have two options.

### Recommended: one origin, via a reverse proxy

Put the page and the model API behind the same host. The browser then sees one
origin, and CORS never enters the picture:

```
browser ──► http://truenas.lan:8080/        ──► this app (static files)
            http://truenas.lan:8080/v1/*    ──► vLLM, a separate app
```

**vLLM stays its own TrueNAS app.** Nothing needs to share a container. The
proxy just maps paths to backends; they can be different containers, or
different machines.

`Caddyfile` and `docker-compose.yml` here do exactly that:

```bash
VLLM_UPSTREAM=192.168.1.10:8000 docker compose up -d
```

On TrueNAS SCALE: *Apps > Discover Apps > Custom App*, install via YAML. Point
`VLLM_UPSTREAM` at wherever vLLM listens — from inside a container that is the
TrueNAS host's LAN address, **not** `localhost`.

Then open `http://<truenas>:8080` and leave *Base URL* as `/v1`.

### Alternative: let vLLM send CORS headers

Unlike Unsloth Desktop, vLLM's OpenAI server can allow browser origins itself
(`--allowed-origins`; check the flag against your version). Then you can point
*Base URL* straight at `http://truenas.lan:8000/v1` with no proxy. It works,
but you lose the single URL and any API key has to live in the browser.

## Using it

1. **Server tab** — set the Base URL (`/v1` behind the proxy), press *Fetch*.
   vLLM serves one model, so it is filled in for you.
2. **Match tab** — drop your resumes folder on the left, job postings on the
   right. Drag-and-drop takes folders as well as files, or click to browse.
3. **Run match.** Results appear in the page; *Download report* saves a
   standalone HTML file.

### Trying it without your own data

*Use demo resumes* and *Use demo job postings* load the bundled sample set from
`demo/` — five resumes (PDF and DOCX) and five postings (including one saved
`.eml`), with deliberately varied fit so you can see whether the model's
ranking makes sense.

The boxes are **additive**: your own files and the demo set are kept separately
and merged for a run, so you can score your real resume against the demo
postings, or try a demo resume against a real job ad. Unticking a box removes
only that set. If one of your files has the same name as a demo file, yours
replaces it. The count says where things came from — *"6 resumes loaded
(2 of yours + 4 demo)"*. *Clear files* drops everything and unticks both.

Settings are kept in `localStorage`, per browser.

Supported: `.pdf`, `.docx`, `.txt`, `.md` resumes; those plus `.eml` for job
postings, which keeps the email's Subject as the title.

## Speed in the log

Each call logs its own time and rate, and the run ends with a summary:

```
[1/5] anna_kovacs_senior_python_engineer.pdf scored 94 · 0.5s · 33 tok/s (18 out, 479 in)
...
5 request(s) in 1.0s · 88 completion + 2327 prompt tokens · 90.0 tok/s throughput, 34.4 tok/s per call
```

**The two rates are different numbers and only one of them is the one to
watch.** Measured against a mock server on one job and five resumes:

| | per call | throughput | wall time |
| --- | --- | --- | --- |
| concurrency 1 | 32.9 tok/s | 32.8 tok/s | 2.7s |
| concurrency 4 | 34.4 tok/s | **90.0 tok/s** | 1.0s |

- **per call** is one request's completion tokens over its own elapsed time.
  It barely moves as concurrency rises, so on its own it makes batching look
  pointless.
- **throughput** is every completion token over the run's wall clock. This is
  what actually finishes the work, and the number to use when tuning
  concurrency against your server's slots.

Two caveats on what these mean. The rates are **end to end**: with no
streaming, a request's elapsed time includes queueing and prompt processing as
well as decoding, so per-call tok/s reads lower than the decode speed a model
server reports for itself. And token counts come from the response's `usage`
field — vLLM and llama.cpp both send it, but a server that omits it gets
timings only, and the log says so rather than inventing numbers.

## Security

**Keep this on your LAN.** There is no authentication. Anyone who can reach the
page can read whatever resumes they load, use your GPU, and see your settings.
Resumes are other people's personal data.

If you ever point it at a hosted API, put the key in the reverse proxy and
leave it out of the browser — anything the page holds is readable in DevTools
by anyone who can load it.

## Layout

```
index.html          the page
css/app.css         follows the browser's light/dark preference
js/scoring.js       prompt + reply parsing, ported from main
js/documents.js     PDF, DOCX, EML and text extraction in the browser
js/llm.js           OpenAI-compatible client and its retry policy
js/matcher.js       the job x resume matrix, concurrency, top N
js/report.js        in-page results and the downloadable report
js/config.js        settings in localStorage
js/demo.js          fetches the bundled sample set
js/app.js           wiring
demo/               sample resumes and postings, with a manifest
vendor/pdfjs/       pdf.js 4.10.38, vendored (Apache-2.0)
Caddyfile           the one-origin reverse proxy
docker-compose.yml  Caddy serving the site and proxying /v1
```

`pdf.js` is vendored rather than loaded from a CDN so the app works with no
internet access at all, which is the point of running it at home. `demo/` is a
copy of `app/examples/` rather than a link to it, because the web root is
deployed on its own.

## Behaviour carried over from the desktop versions

These were expensive to get right and are deliberately identical:

- A request that **times out is never resent** — the server is probably still
  working on it, and a second copy doubles the load for a reply nobody reads.
  Only a refused request (429/503) is retried, with backoff.
- **One job and one resume per request**, always a fresh context. Resumes are
  never mixed.
- Ties break by resume name, so two runs of the same data agree.

## What was verified

Run end to end in headless Chromium against a mock vLLM serving the site and
`/v1` from one origin, using the real sample files from `app/examples/`:

- 5 resumes (PDF + DOCX) and 2 job postings (`.txt` + `.eml`) parsed in-browser
- ranked correctly — 94 / 71 / 62 / 28 / 8 for the Python job
- server side saw **exactly 10 calls for 2 jobs × 5 resumes** — no duplicates —
  with `peak_concurrency=4` matching the setting
- no console or page errors

The demo toggles were tested the same way: ticking both gives 5 + 5; adding two
files of your own (one new name, one shadowing a demo file) gives *6 resumes
(2 of yours + 4 demo)*; unticking leaves only your own; *Clear files* resets
both and unticks the boxes.

Not verified: a real vLLM server, Safari and Firefox (the folder picker uses
`webkitdirectory`; the "pick individual files instead" link is the fallback),
and the Caddy/TrueNAS deployment itself.
