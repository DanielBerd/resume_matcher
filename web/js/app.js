// Wires the page together. Everything heavy lives in the other modules.

import * as cfg from './config.js';
import { readResume, readJob, RESUME_EXT, JOB_EXT } from './documents.js';
import { LlmClient, LlmError } from './llm.js';
import { run as runMatch } from './matcher.js';
import { resultsMarkup, standaloneReport, timestamp } from './report.js';

const $ = (id) => document.getElementById(id);

const state = {
  settings: cfg.load(),
  resumes: [],
  jobs: [],
  results: null,
  controller: null,
};

// ---------- tabs ----------

for (const tab of document.querySelectorAll('.tab')) {
  tab.addEventListener('click', () => selectTab(tab.dataset.tab));
}

function selectTab(name) {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.setAttribute('aria-selected', String(tab.dataset.tab === name));
  }
  $('tab-match').hidden = name !== 'match';
  $('tab-server').hidden = name !== 'server';
}

// ---------- file pickers ----------

function wireZone(zone, { accept, multiple, directory, onFiles }) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = accept.join(',');
  input.multiple = multiple;
  if (directory) { input.webkitdirectory = true; input.directory = true; }
  input.hidden = true;
  document.body.append(input);

  const open = () => input.click();
  zone.addEventListener('click', open);
  zone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
  });
  input.addEventListener('change', () => { onFiles([...input.files]); input.value = ''; });
  zone.dataset.wired = '1';

  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', async (e) => {
    e.preventDefault();
    zone.classList.remove('over');
    onFiles(await filesFromDrop(e.dataTransfer));
  });
}

/** Files from a drop, walking into any dropped folders. */
async function filesFromDrop(dt) {
  const entries = [...dt.items].map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  if (entries.length === 0) return [...dt.files];

  const out = [];
  const walk = async (entry) => {
    if (entry.isFile) {
      out.push(await new Promise((res, rej) => entry.file(res, rej)));
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      for (;;) {
        const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
        if (!batch.length) break;
        for (const child of batch) await walk(child);
      }
    }
  };
  for (const entry of entries) await walk(entry);
  return out;
}

/** A file picker not attached to a zone, for the "individual files" escape hatch. */
function filePicker(accept, onFiles) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = accept.join(',');
  input.multiple = true;
  input.hidden = true;
  document.body.append(input);
  input.addEventListener('change', () => { onFiles([...input.files]); input.value = ''; });
  return () => input.click();
}

wireZone($('resume-zone'), {
  accept: RESUME_EXT, multiple: true, directory: true,
  onFiles: (files) => loadFiles(files, 'resumes'),
});
wireZone($('job-zone'), {
  accept: JOB_EXT, multiple: true, directory: false,
  onFiles: (files) => loadFiles(files, 'jobs'),
});

// The resume zone picks a folder, matching the desktop versions. Some people
// only want a handful of files, so offer that too.
const pickResumeFiles = filePicker(RESUME_EXT, (files) => loadFiles(files, 'resumes'));
$('pick-resume-files').addEventListener('click', (e) => { e.stopPropagation(); pickResumeFiles(); });

async function loadFiles(files, kind) {
  if (!files.length) return;
  const read = kind === 'resumes' ? readResume : readJob;
  log(`Reading ${files.length} file(s) for ${kind}…`);

  const loaded = [];
  let skipped = 0;
  for (const file of files) {
    const item = await read(file);
    if (item) loaded.push(item); else skipped += 1;
  }

  state[kind] = loaded;
  const label = kind === 'resumes' ? 'resume' : 'job posting';
  $(`${kind === 'resumes' ? 'resume' : 'job'}-status`).textContent =
    loaded.length === 0
      ? `No readable ${label}s found.`
      : `${loaded.length} ${label}${loaded.length === 1 ? '' : 's'} loaded` +
        (skipped ? ` (${skipped} skipped — unsupported or empty)` : '') + '.';

  log(`${kind}: ${loaded.length} loaded, ${skipped} skipped.`);
  refresh();
}

$('clear-files').addEventListener('click', () => {
  state.resumes = []; state.jobs = []; state.results = null;
  $('resume-status').textContent = 'No resumes loaded.';
  $('job-status').textContent = 'No job postings loaded.';
  $('results').hidden = true;
  $('download').disabled = true;
  $('bar').style.width = '0';
  setStatus('Ready.');
  refresh();
});

// ---------- the run ----------

$('run').addEventListener('click', start);
$('stop').addEventListener('click', () => state.controller?.abort(new DOMException('stopped', 'AbortError')));

async function start() {
  readSettingsFromForm();
  if (!state.settings.model) {
    setStatus('Set a model on the Server tab first.', 'error');
    selectTab('server');
    return;
  }

  cfg.save(state.settings);
  state.controller = new AbortController();
  busy(true);
  $('results').hidden = true;
  $('bar').style.width = '0';

  const client = new LlmClient(state.settings);
  try {
    setStatus('Checking the server…');
    await client.listModels(state.controller.signal);

    const { jobs, resumes } = state;
    log(`Matching ${jobs.length} job(s) against ${resumes.length} resume(s) using ${state.settings.model}`);
    setStatus('Working…');

    const results = await runMatch(
      client, jobs, resumes, state.settings,
      ({ done, total, message }) => {
        $('bar').style.width = `${total ? (done / total) * 100 : 0}%`;
        log(message);
      },
      state.controller.signal,
    );

    state.results = results;
    $('results').innerHTML = resultsMarkup(results);
    $('results').hidden = false;
    $('download').disabled = false;
    $('bar').style.width = '100%';
    setStatus(`Done — ${jobs.length} job(s) scored.`);
  } catch (e) {
    if (e?.name === 'AbortError') {
      setStatus('Stopped.');
      log('Stopped before finishing.');
    } else {
      setStatus(e.message, 'error');
      log(`Error: ${e.message}`);
      if (e instanceof LlmError) selectTab('server');
    }
  } finally {
    state.controller = null;
    busy(false);
  }
}

function busy(on) {
  $('run').disabled = on || !ready();
  $('stop').disabled = !on;
  $('clear-files').disabled = on;
}

const ready = () => state.resumes.length > 0 && state.jobs.length > 0;

function refresh() {
  $('run').disabled = !ready() || state.controller !== null;
  refreshSummary();
}

// ---------- report download ----------

$('download').addEventListener('click', () => {
  if (!state.results) return;
  const stamp = timestamp();
  const blob = new Blob([standaloneReport(state.results, stamp)], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `resume-matcher_${stamp}.html`;
  a.click();
  URL.revokeObjectURL(url);
});

// ---------- server tab ----------

const preset = $('preset');
preset.append(...cfg.PRESETS.map((p) => new Option(p.name, p.name)));
preset.addEventListener('change', () => {
  const p = cfg.PRESETS.find((x) => x.name === preset.value);
  if (!p) return;
  if (p.baseUrl) $('base-url').value = p.baseUrl;
  if (!p.needsKey) $('api-key').value = '';
  readSettingsFromForm();
  refreshSummary();
});

$('toggle-key').addEventListener('click', () => {
  const field = $('api-key');
  const shown = field.type === 'text';
  field.type = shown ? 'password' : 'text';
  $('toggle-key').textContent = shown ? 'Show' : 'Hide';
});

$('save').addEventListener('click', () => {
  readSettingsFromForm();
  const saved = cfg.save(state.settings);
  setServerStatus(saved ? 'Saved in this browser.' : 'Could not save — storage is blocked.', saved ? 'ok' : 'error');
  refreshSummary();
});

$('test').addEventListener('click', fetchModels);
$('fetch-models').addEventListener('click', fetchModels);

async function fetchModels() {
  readSettingsFromForm();
  setServerStatus('Connecting…');
  try {
    const models = await new LlmClient(state.settings).listModels();
    $('model-list').innerHTML = '';
    $('model-list').append(...models.map((m) => new Option(m)));

    // vLLM serves one model, so preselecting it saves typing the served name.
    if (!state.settings.model && models.length > 0) {
      $('model').value = models[0];
      readSettingsFromForm();
    }
    setServerStatus(`Connected — ${models.length} model(s): ${models.slice(0, 6).join(', ')}`, 'ok');
  } catch (e) {
    setServerStatus(e.message, 'error');
  }
  refreshSummary();
}

for (const id of ['base-url', 'api-key', 'model', 'concurrency', 'top-n']) {
  $(id).addEventListener('input', () => { readSettingsFromForm(); refreshSummary(); });
}

function readSettingsFromForm() {
  state.settings = {
    ...state.settings,
    baseUrl: $('base-url').value.trim(),
    apiKey: $('api-key').value,
    model: $('model').value.trim(),
    concurrency: Math.max(1, Number($('concurrency').value) || 4),
    topN: Math.max(1, Number($('top-n').value) || 5),
  };
}

function writeSettingsToForm() {
  const s = state.settings;
  $('base-url').value = s.baseUrl;
  $('api-key').value = s.apiKey;
  $('model').value = s.model;
  $('concurrency').value = s.concurrency;
  $('top-n').value = s.topN;
  preset.value = cfg.PRESETS.find((p) => p.baseUrl === s.baseUrl)?.name ?? 'Custom';
}

// ---------- status lines ----------

function refreshSummary() {
  const s = state.settings;
  const remote = cfg.isRemote(s.baseUrl);
  const where = s.baseUrl.startsWith('/') ? 'this server' : (s.baseUrl || '(no server set)');

  $('summary').className = 'summary' + (remote ? ' remote' : '');
  $('summary').textContent =
    `Using ${s.model || '(no model set)'} @ ${where}` +
    (remote ? ' — resume text leaves this network' : '') +
    ` · ${state.resumes.length} resume(s), ${state.jobs.length} job(s)`;

  $('privacy').hidden = !remote;
  $('privacy').textContent = remote
    ? 'This server is on another origin: every job posting and the full text of every resume is sent there. '
      + 'Resumes are personal data — use this knowingly. It also needs CORS headers, or the browser will block it.'
    : '';
}

function setStatus(text, kind = '') { $('status').className = `muted ${kind}`; $('status').textContent = text; }
function setServerStatus(text, kind = '') { $('server-status').className = `muted ${kind}`; $('server-status').textContent = text; }

function log(line) {
  const el = $('log');
  el.textContent += (el.textContent ? '\n' : '') + line;
  el.scrollTop = el.scrollHeight;
}

// ---------- start ----------

writeSettingsToForm();
refresh();
selectTab('match');
