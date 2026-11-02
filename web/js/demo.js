// The bundled sample data, fetched from demo/ and handed to the same readers
// the drag-and-drop path uses, so demo files behave exactly like your own.

const BASE = 'demo';
let manifest = null;

async function loadManifest() {
  if (!manifest) {
    const r = await fetch(`${BASE}/manifest.json`);
    if (!r.ok) throw new Error(`demo data is not installed (${r.status})`);
    manifest = await r.json();
  }
  return manifest;
}

/**
 * Fetch one set of demo files as File objects.
 * @param {'resumes'|'jobs'} kind
 */
export async function demoFiles(kind) {
  const names = (await loadManifest())[kind] ?? [];
  return Promise.all(names.map(async (name) => {
    const r = await fetch(`${BASE}/${kind}/${encodeURIComponent(name)}`);
    if (!r.ok) throw new Error(`could not fetch demo file ${name} (${r.status})`);
    return new File([await r.blob()], name);
  }));
}
