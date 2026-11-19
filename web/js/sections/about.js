// About page: what the current run is made of, how numbers are computed, and licences.
//
// - Provenance of the current run (level, run id, code version, inputs).
// - The model runs (/api/meta/runs) and the loaded input batches (/api/meta/imports).
// - Method notes: docs/methods/*.md, served by Nginx at /methods/. The list comes from
//   /methods/README.md; a note opens here with about.html?note=<file>.md, rendered by a
//   small Markdown renderer that builds DOM nodes (text is never parsed as HTML).
// - Licences of the vendored libraries and the open data.

const NOTE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*\.md$/;

const LICENCES = [
  ['Leaflet 1.9.4', 'BSD-2-Clause', 'Map display', 'vendor/leaflet/LICENSE'],
  ['Chart.js 4.4.7', 'MIT', 'Charts', 'vendor/chartjs/LICENSE.md'],
  ['Swagger UI 5.17.14', 'Apache-2.0', 'API documentation page', 'vendor/swagger-ui/LICENSE'],
  ['pandapower 3.5.6', 'BSD-3-Clause', 'Load flow (server side)', null],
  ['FastAPI, pandas, NumPy, GeoPandas, SQLAlchemy', 'MIT / BSD', 'Server side', null],
  ['PostgreSQL with PostGIS', 'PostgreSQL / GPL-2.0', 'Database (server side)', null],
];

const OPEN_DATA = [
  ['OpenStreetMap', 'Open Database Licence (ODbL) 1.0', 'Base map and context layers. © OpenStreetMap contributors.'],
  ['Other open layers', 'As listed with each layer', 'Each open layer’s source and licence is recorded in its import batch (data/open manifest) and in docs/open-data-sources.md.'],
];

// ------------------------------------------------------------------ safe Markdown

const SAFE_HREF = /^(https?:|mailto:|#|\/|\.{0,2}\/|[A-Za-z0-9._-]+(\/|$|#|\.))/;

/** Turn one line of Markdown inline syntax into DOM nodes: `code`, **bold**, *em*, [text](href). */
function inline(text, el, linkHref) {
  const out = [];
  // Underscore emphasis needs a non-word character on both sides, so snake_case names
  // such as loss_mwh_month stay as written.
  const pattern = /(`+)([\s\S]*?)\1|\*\*([^*]+)\*\*|(?<![A-Za-z0-9])__([^_]+)__(?![A-Za-z0-9])|\*([^*\s][^*]*)\*|(?<![A-Za-z0-9])_([^_\s][^_]*)_(?![A-Za-z0-9])|\[([^\]]+)\]\(([^)\s]+)\)/g;
  let last = 0;
  let m;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1]) out.push(el('code', {}, m[2]));
    else if (m[3] || m[4]) out.push(el('strong', {}, inline(m[3] || m[4], el, linkHref)));
    else if (m[5] || m[6]) out.push(el('em', {}, inline(m[5] || m[6], el, linkHref)));
    else if (m[7]) {
      const href = linkHref(m[8]);
      out.push(href && SAFE_HREF.test(href) && !/^javascript:/i.test(href)
        ? el('a', { href, rel: /^https?:/.test(href) ? 'noopener noreferrer' : null }, inline(m[7], el, linkHref))
        : m[7]);
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function splitRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

/**
 * Render Markdown into a DocumentFragment. Supports headings, paragraphs, bullet and
 * numbered lists (nested by indentation), tables, fenced code, block quotes and rules.
 * Headings are shifted down one level because the page already has its h1 and h2.
 */
export function renderMarkdown(source, el, linkHref = (h) => h) {
  const lines = String(source).replace(/\r\n?/g, '\n').split('\n');
  const frag = document.createDocumentFragment();
  let i = 0;
  const isBlank = (l) => /^\s*$/.test(l);
  const listItem = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  const startsBlock = (l) => /^\s*(#{1,6}\s|```|>|\|)/.test(l) || listItem.test(l) || /^\s*([-*_])(\s*\1){2,}\s*$/.test(l);

  while (i < lines.length) {
    const line = lines[i];
    if (isBlank(line)) { i += 1; continue; }

    let m = /^```\s*([\w-]*)\s*$/.exec(line.trim());
    if (m) {
      const code = [];
      i += 1;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { code.push(lines[i]); i += 1; }
      i += 1; // closing fence
      frag.append(el('pre', {}, el('code', { class: m[1] ? `language-${m[1]}` : null }, code.join('\n'))));
      continue;
    }
    m = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(line);
    if (m) {
      const level = Math.min(6, m[1].length + 2);
      frag.append(el(`h${level}`, {}, inline(m[2], el, linkHref)));
      i += 1;
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { frag.append(el('hr')); i += 1; continue; }
    if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
      const head = splitRow(line);
      i += 2;
      const body = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) { body.push(splitRow(lines[i])); i += 1; }
      frag.append(el('div', { class: 'atlas-table-wrap' }, el('table', { class: 'atlas-table' },
        el('thead', {}, el('tr', {}, head.map((h) => el('th', { scope: 'col' }, inline(h, el, linkHref))))),
        el('tbody', {}, body.map((r) => el('tr', {}, r.map((c) => el('td', {}, inline(c, el, linkHref)))))))));
      continue;
    }
    if (/^\s*>/.test(line)) {
      const quote = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { quote.push(lines[i].replace(/^\s*>\s?/, '')); i += 1; }
      frag.append(el('blockquote', {}, renderMarkdown(quote.join('\n'), el, linkHref)));
      continue;
    }
    if (listItem.test(line)) {
      // A stack of open lists, one per indentation level.
      const root = { indent: -1, node: null, children: [] };
      const stack = [];
      while (i < lines.length && (listItem.test(lines[i]) || (!isBlank(lines[i]) && !startsBlock(lines[i]) && stack.length))) {
        const item = listItem.exec(lines[i]);
        if (!item) { // continuation line of the previous item
          const lastLi = stack[stack.length - 1].node.lastElementChild;
          lastLi.append(' ', ...inline(lines[i].trim(), el, linkHref));
          i += 1;
          continue;
        }
        const indent = item[1].replace(/\t/g, '    ').length;
        const ordered = /\d/.test(item[2]);
        while (stack.length && stack[stack.length - 1].indent > indent) stack.pop();
        let top = stack[stack.length - 1];
        if (!top || indent > top.indent) {
          const list = el(ordered ? 'ol' : 'ul');
          if (top) top.node.lastElementChild.append(list);
          else root.children.push(list);
          top = { indent, node: list };
          stack.push(top);
        }
        top.node.append(el('li', {}, inline(item[3], el, linkHref)));
        i += 1;
      }
      frag.append(...root.children);
      continue;
    }
    const para = [];
    while (i < lines.length && !isBlank(lines[i]) && !startsBlock(lines[i])) { para.push(lines[i].trim()); i += 1; }
    if (para.length === 0) { para.push(line.trim()); i += 1; } // a stray line that looked like a block start
    frag.append(el('p', {}, inline(para.join(' '), el, linkHref)));
  }
  return frag;
}

// ------------------------------------------------------------------ page parts

async function fetchText(path) {
  const resp = await fetch(path, { headers: { Accept: 'text/markdown, text/plain' } });
  if (!resp.ok) {
    const err = new Error(`${path}: HTTP ${resp.status}`);
    err.status = resp.status;
    throw err;
  }
  return resp.text();
}

/** Method-note links become about.html?note=<file>#methods; other links stay as written. */
function noteLink(href) {
  const name = href.replace(/^\.\//, '').replace(/^\/?methods\//, '');
  if (NOTE_NAME.test(name)) return `about.html?note=${encodeURIComponent(name)}#methods`;
  return href;
}

function provenancePart(ctx) {
  const { el, fmt } = ctx;
  const p = ctx.provenance;
  if (!p) {
    return el('div', { class: 'atlas-error', role: 'alert' },
      el('strong', {}, 'Provenance unknown. '), 'The API did not answer. Treat every figure as SYNTHETIC.');
  }
  const rows = [
    ['Provenance', p.label || p.level],
    ['Level', p.level],
    ['Real data', p.is_real ? 'Yes' : 'No'],
    ['Run', p.run_id],
    ['Code version', p.code_version],
    ['Run started (EAT)', p.started_at],
    ['Run finished (EAT)', p.finished_at],
  ];
  const detail = p.detail && typeof p.detail === 'object' ? Object.entries(p.detail) : [];
  for (const [key, value] of detail) rows.push([key.replace(/_/g, ' '), value]);
  return el('dl', { class: 'atlas-dl' }, rows.flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, fmt(v))]));
}

async function methodsPart(ctx, box) {
  const { el, params } = ctx;
  const note = params.note && NOTE_NAME.test(params.note) ? params.note : null;
  box.replaceChildren(el('p', { class: 'atlas-loading' }, 'Loading method notes…'));
  try {
    if (note) {
      const text = await fetchText(`/methods/${encodeURIComponent(note)}`);
      box.replaceChildren(
        el('p', {}, el('a', { href: 'about.html#methods' }, '← All method notes'), ' · ',
          el('a', { href: `/methods/${encodeURIComponent(note)}` }, `Raw file (${note})`)),
        el('article', { class: 'atlas-markdown' }, renderMarkdown(text, el, noteLink)));
    } else {
      const text = await fetchText('/methods/README.md');
      box.replaceChildren(el('article', { class: 'atlas-markdown' }, renderMarkdown(text, el, noteLink)));
    }
  } catch (err) {
    box.replaceChildren(el('div', { class: 'atlas-notice', role: 'status' },
      el('strong', {}, 'Method notes are not published yet. '),
      'They live in docs/methods/ and are served at /methods/.',
      el('small', {}, err.message)));
  }
}

function licencesPart(ctx) {
  const { el } = ctx;
  const software = el('table', { class: 'atlas-table' },
    el('thead', {}, el('tr', {}, ['Software', 'Licence', 'Used for', 'Licence text'].map((h) => el('th', { scope: 'col' }, h)))),
    el('tbody', {}, LICENCES.map(([name, licence, use, file]) => el('tr', {},
      el('td', {}, name), el('td', {}, licence), el('td', {}, use),
      el('td', {}, file ? el('a', { href: file }, 'licence') : '–')))));
  const data = el('table', { class: 'atlas-table' },
    el('thead', {}, el('tr', {}, ['Open data', 'Licence', 'Notes'].map((h) => el('th', { scope: 'col' }, h)))),
    el('tbody', {}, OPEN_DATA.map((r) => el('tr', {}, r.map((c) => el('td', {}, c))))));
  return [
    el('div', { class: 'atlas-table-wrap' }, software),
    el('p', {}, 'Versions and checksums of the vendored files: ', el('a', { href: 'vendor/VERSIONS.md' }, 'vendor/VERSIONS.md'), '.'),
    el('div', { class: 'atlas-table-wrap' }, data),
    el('p', {}, 'UETCL data shown in the Atlas stays UETCL’s property and is handled under the data-handling note. Synthetic data is generated by the Atlas itself and is labelled everywhere.'),
  ];
}

export default async function render(root, ctx) {
  const { el, loadTable } = ctx;
  const runsBox = el('div');
  const inputsBox = el('div');
  const methodsBox = el('div');

  root.append(
    el('h3', {}, 'Current run and its provenance'), provenancePart(ctx),
    el('h3', {}, 'Model runs'), runsBox,
    el('h3', {}, 'Inputs loaded'),
    el('p', { class: 'atlas-lede' }, 'Every file the Atlas has loaded, newest first. The Imports page has the details and the quarantine.'),
    inputsBox,
    el('h3', { id: 'methods' }, 'Method notes'),
    el('p', { class: 'atlas-lede' }, 'How each number is computed, written for the mentors who check the methods. A note is signed off at the end once checked.'),
    methodsBox,
    el('h3', { id: 'licences' }, 'Licences'), ...licencesPart(ctx),
    el('h3', {}, 'API'),
    el('p', {}, 'Every table on these pages comes from the read-only API. Its documentation, with units for each field, is at ',
      el('a', { href: '/api/docs' }, '/api/docs'), '.'));

  await Promise.all([
    loadTable(runsBox, '/api/meta/runs', {}, { limit: 10, what: 'The run list' }),
    loadTable(inputsBox, '/api/meta/imports', {}, {
      limit: 15, what: 'The input list',
      columns: ['batch_id', 'dataset', 'template', 'root', 'received_from', 'received_on', 'status', 'rows_loaded', 'rows_rejected'],
    }),
    methodsPart(ctx, methodsBox),
  ]);
  if (ctx.params.note) document.getElementById('methods')?.scrollIntoView();
}
