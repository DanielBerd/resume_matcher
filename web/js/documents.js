// Reading resumes and job postings in the browser. Nothing is uploaded
// anywhere: files are parsed here and only the extracted text is sent to the
// model server.

export const RESUME_EXT = ['.pdf', '.docx', '.txt', '.md'];
export const JOB_EXT = ['.txt', '.md', '.eml', '.pdf', '.docx'];

const extOf = (name) => {
  const i = name.lastIndexOf('.');
  return i < 0 ? '' : name.slice(i).toLowerCase();
};

// ---------- DOCX ----------
// A .docx is a zip. Browsers ship DecompressionStream('deflate-raw'), so
// word/document.xml is read without a zip library.

async function docxText(buf) {
  const dv = new DataView(buf), td = new TextDecoder();

  let eocd = -1;
  for (let i = buf.byteLength - 22; i >= 0; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('not a .docx (no zip directory)');

  const count = dv.getUint16(eocd + 10, true);
  let off = dv.getUint32(eocd + 16, true);

  for (let i = 0; i < count; i++) {
    const nameLen = dv.getUint16(off + 28, true);
    const extraLen = dv.getUint16(off + 30, true);
    const cmtLen = dv.getUint16(off + 32, true);
    const method = dv.getUint16(off + 10, true);
    const csize = dv.getUint32(off + 20, true);
    const localHeader = dv.getUint32(off + 42, true);
    const name = td.decode(new Uint8Array(buf, off + 46, nameLen));

    if (name === 'word/document.xml') {
      const lName = dv.getUint16(localHeader + 26, true);
      const lExtra = dv.getUint16(localHeader + 28, true);
      const raw = new Uint8Array(buf, localHeader + 30 + lName + lExtra, csize);

      let xml;
      if (method === 0) {
        xml = td.decode(raw);
      } else {
        const stream = new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
        xml = td.decode(await new Response(stream).arrayBuffer());
      }

      const doc = new DOMParser().parseFromString(xml, 'application/xml');
      const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
      return [...doc.getElementsByTagNameNS(W, 'p')]
        .map((p) => {
          let out = '';
          for (const node of p.getElementsByTagNameNS(W, '*')) {
            if (node.localName === 't') out += node.textContent;
            else if (node.localName === 'tab') out += '\t';
            else if (node.localName === 'br') out += '\n';
          }
          return out;
        })
        .join('\n');
    }
    off += 46 + nameLen + extraLen + cmtLen;
  }
  throw new Error('word/document.xml not found');
}

// ---------- PDF ----------
// pdf.js is vendored under vendor/pdfjs so the app works with no CDN and no
// network beyond the model server. Loaded lazily: most runs never touch it.

let pdfjs = null;
async function loadPdfjs() {
  if (!pdfjs) {
    pdfjs = await import('../vendor/pdfjs/pdf.min.mjs');
    pdfjs.GlobalWorkerOptions.workerSrc = new URL('../vendor/pdfjs/pdf.worker.min.mjs', import.meta.url).href;
  }
  return pdfjs;
}

async function pdfText(buf) {
  const lib = await loadPdfjs();
  const doc = await lib.getDocument({ data: buf }).promise;
  const pages = [];

  for (let n = 1; n <= doc.numPages; n++) {
    const content = await (await doc.getPage(n)).getTextContent();
    // PDF text runs carry no explicit spaces and no line breaks; rebuild lines
    // from each item's y position so words do not run together.
    let lastY = null, line = [], lines = [];
    for (const item of content.items) {
      const y = item.transform[5];
      if (lastY !== null && Math.abs(lastY - y) > 2) { lines.push(line.join(' ')); line = []; }
      if (item.str.trim()) line.push(item.str.trim());
      lastY = y;
    }
    if (line.length) lines.push(line.join(' '));
    pages.push(lines.join('\n'));
  }
  await doc.destroy();
  return pages.join('\n');
}

// ---------- .eml ----------

function parseEml(text, fallbackTitle) {
  const split = text.search(/\r?\n\r?\n/);
  const headerBlock = split < 0 ? text : text.slice(0, split);
  const body = split < 0 ? '' : text.slice(split).replace(/^[\r\n]+/, '');

  // Unfold headers that wrap onto indented continuation lines.
  const unfolded = headerBlock.replace(/\r?\n[ \t]+/g, ' ');
  const subject = unfolded.match(/^Subject:\s*(.+)$/im);

  return {
    title: subject ? subject[1].trim() : fallbackTitle,
    body: body || text,
  };
}

// ---------- public API ----------

async function textOf(file) {
  const ext = extOf(file.name);
  if (ext === '.pdf') return pdfText(await file.arrayBuffer());
  if (ext === '.docx') return docxText(await file.arrayBuffer());
  return file.text();
}

/** Extract text from one resume file. Returns null when there is nothing usable. */
export async function readResume(file) {
  if (!RESUME_EXT.includes(extOf(file.name))) return null;
  try {
    const text = await textOf(file);
    return text.trim() ? { name: file.name, text } : null;
  } catch (e) {
    console.warn(`Could not read ${file.name}:`, e);
    return null;
  }
}

/** Extract one job posting. .eml keeps its Subject as the title; otherwise the
 *  first non-empty line is used. */
export async function readJob(file) {
  if (!JOB_EXT.includes(extOf(file.name))) return null;
  try {
    const stem = file.name.replace(/\.[^.]+$/, '');
    if (extOf(file.name) === '.eml') {
      const { title, body } = parseEml(await file.text(), stem);
      return { source: file.name, title, body };
    }
    const text = await textOf(file);
    if (!text.trim()) return null;
    const title = text.split('\n').map((l) => l.trim()).find((l) => l.length > 0) || stem;
    return { source: file.name, title, body: text };
  } catch (e) {
    console.warn(`Could not read ${file.name}:`, e);
    return null;
  }
}
