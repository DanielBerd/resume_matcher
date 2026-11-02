// Settings, persisted in localStorage (per browser, per origin).

const KEY = 'resume-matcher.settings';

export const DEFAULTS = {
  // Relative by default: with the page and the model server behind one reverse
  // proxy, every request is same-origin and CORS never applies.
  baseUrl: '/v1',
  apiKey: '',
  model: '',
  concurrency: 4,
  topN: 5,
  temperature: 0.1,
  maxTokens: 2048,
  timeoutSeconds: 600,
  busyWaitSeconds: 120,
};

export const PRESETS = [
  { name: 'Same origin (reverse proxy)', baseUrl: '/v1', needsKey: false },
  { name: 'vLLM on this network', baseUrl: 'http://truenas.lan:8000/v1', needsKey: false },
  { name: 'Unsloth Desktop', baseUrl: 'http://localhost:8888/v1', needsKey: false },
  { name: 'OpenAI', baseUrl: 'https://api.openai.com/v1', needsKey: true },
  { name: 'Custom', baseUrl: '', needsKey: true },
];

export function load() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') };
  } catch {
    return { ...DEFAULTS };
  }
}

export function save(settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
    return true;
  } catch {
    return false;    // private mode, or storage disabled
  }
}

/** True when the request would leave this origin, so resume text goes elsewhere. */
export function isRemote(baseUrl) {
  if (!baseUrl || baseUrl.startsWith('/')) return false;
  try {
    return new URL(baseUrl, location.href).origin !== location.origin;
  } catch {
    return true;
  }
}
