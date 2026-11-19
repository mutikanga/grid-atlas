// Grid Atlas: shared browser code for every page (an ES module, no external URLs).
//
// What it does on every page, as soon as it is imported:
//   1. reads the current provenance from /api/meta/provenance and draws the banner
//      fixed at the top (red stripes when the data is synthetic), plus the footer;
//   2. finds every <section class="atlas-section" data-module="js/sections/x.js">,
//      imports that module and calls its `export default async function render(el, ctx)`.
//
// What it offers to sections (through ctx) and to js/map.js (through imports):
//   api(path, params)            GET JSON from the API; throws ApiError on failure
//   table(el, response, opts)    render a table response: units in headers, number
//                                formatting, click-to-sort, empty state, downloads
//   loadTable(el, path, params, opts)   fetch + table + loading/error states in one call
//   chart(canvas, config)        new Chart.js chart with the provenance watermark
//   fmt(value, decimals, unit)   number formatting used everywhere on screen
//   el(tag, attrs, ...children)  build DOM safely (text is never parsed as HTML)
//   downloads(el, response)      CSV and Excel buttons from response.export
//
// The screen never does arithmetic on results: values arrive rounded from the API
// (same rounding as the CSV), and fmt() only adds separators and units.

const PROVENANCE_PATH = '/api/meta/provenance';
const SECTION_MODULE = /^js\/sections\/[a-z0-9][a-z0-9-]*\.js$/;
const NUMBER_LOCALE = 'en-GB';
const DASH = '–';

// ------------------------------------------------------------------ state

let currentProvenance = null;
let resolveProvenance;
/** Resolves with the provenance object (or null when it could not be read). */
export const provenanceReady = new Promise((resolve) => { resolveProvenance = resolve; });

/** The provenance known so far (null until loaded, or when the API is down). */
export function getProvenance() {
  return currentProvenance;
}

// ------------------------------------------------------------------ DOM helper

/**
 * Create an element. attrs: class, text, dataset {...}, style {...}, onX handlers,
 * anything else becomes an attribute (false/null skips it). Children may be nodes,
 * strings, numbers, arrays or null. Strings are always text, never HTML.
 */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  appendChildren(node, children);
  return node;
}

function appendChildren(node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/** Escape text for the rare place that must build an HTML string (prefer el()). */
export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

// ------------------------------------------------------------------ formatting

const numberFormats = new Map();
function numberFormat(decimals) {
  const key = decimals ?? 'auto';
  if (!numberFormats.has(key)) {
    const opts = decimals === null || decimals === undefined
      ? { maximumFractionDigits: 6 }
      : { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
    numberFormats.set(key, new Intl.NumberFormat(NUMBER_LOCALE, opts));
  }
  return numberFormats.get(key);
}

/**
 * Format a value for display: 12345.6 -> "12,345.6", with an optional unit
 * ("12,345.6 MWh", "87 %"). Missing values show as an en dash. Booleans show Yes/No.
 */
export function fmt(value, decimals = null, unit = '') {
  if (value === null || value === undefined || value === '' || (typeof value === 'number' && Number.isNaN(value))) {
    return DASH;
  }
  let text;
  if (typeof value === 'boolean') text = value ? 'Yes' : 'No';
  else if (typeof value === 'number') text = numberFormat(decimals).format(value);
  else if (Array.isArray(value)) text = value.map((v) => fmt(v)).join(', ');
  else if (typeof value === 'object') text = JSON.stringify(value);
  else text = String(value);
  if (!unit || typeof value === 'boolean') return text;
  return `${text} ${unit}`; // narrow no-break space keeps the unit on the same line
}

/**
 * Text for one table cell. A column without decimals holds ids, codes and years
 * (run 1234, commissioned 1998), so whole numbers there are shown without a
 * thousands separator; "1,998" would be wrong for a year.
 */
export function cellText(value, col) {
  const noDecimals = col.decimals === null || col.decimals === undefined;
  if (noDecimals && typeof value === 'number' && Number.isInteger(value)) return String(value);
  return fmt(value, col.decimals);
}

/** Header text for a column: "Losses (MWh)". */
export function columnHeader(col) {
  return col.unit ? `${col.label} (${col.unit})` : col.label;
}

// ------------------------------------------------------------------ API access

/** An API call that failed. `status` is the HTTP status, or 0 when the API was unreachable. */
export class ApiError extends Error {
  constructor(status, message, path) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.path = path;
  }
}

/**
 * GET a JSON endpoint of our own API. `params` become the query string (empty values
 * are left out). Throws ApiError on a network failure or a non-2xx answer.
 */
export async function api(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  let resp;
  try {
    resp = await fetch(url, { headers: { Accept: 'application/json' } });
  } catch (err) {
    throw new ApiError(0, 'The Atlas API could not be reached.', path);
  }
  if (!resp.ok) {
    let detail = resp.statusText || 'request failed';
    try {
      const body = await resp.json();
      if (body && body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch (err) { /* not JSON: keep the status text */ }
    throw new ApiError(resp.status, detail, path);
  }
  const body = await resp.json();
  if (body && body.provenance && typeof body.provenance === 'object') noteProvenance(body.provenance);
  return body;
}

// ------------------------------------------------------------------ states

/** Show a "Loading ..." line in a container. */
export function loading(container, what = 'Loading') {
  container.replaceChildren(el('p', { class: 'atlas-loading', role: 'status' }, `${what}…`));
}

/**
 * Show an error in place of content. A 404 means "this endpoint or view is not built
 * yet", which is normal while the Atlas is being built, so it is shown as a notice.
 */
export function showError(container, err, what = 'This part') {
  const status = err && err.status;
  let box;
  if (status === 404) {
    box = el('div', { class: 'atlas-notice', role: 'status' },
      el('strong', {}, 'Not available yet. '), `${what} has no data in the current run.`,
      el('small', {}, err.message || ''));
  } else if (status === 0) {
    box = el('div', { class: 'atlas-error', role: 'alert' },
      el('strong', {}, 'The API is not answering. '), 'Check that the Atlas is running, then reload the page.');
  } else {
    box = el('div', { class: 'atlas-error', role: 'alert' },
      el('strong', {}, 'Could not load. '), `${what} failed${status ? ` (HTTP ${status})` : ''}.`,
      el('small', {}, (err && err.message) || String(err)));
  }
  container.replaceChildren(box);
  return box;
}

// ------------------------------------------------------------------ downloads

/** CSV and Excel buttons for a table response (uses response.export). */
export function downloads(container, response) {
  const links = response && response.export;
  if (!links || (!links.csv && !links.xlsx)) return null;
  const box = el('div', { class: 'atlas-downloads' },
    el('span', {}, 'Download:'),
    links.csv ? el('a', { href: links.csv, download: '', title: 'CSV, rounded as on screen' }, 'CSV') : null,
    links.xlsx ? el('a', { href: links.xlsx, download: '', title: 'Excel, full precision with a README sheet' }, 'Excel') : null);
  if (container) container.append(box);
  return box;
}

// ------------------------------------------------------------------ tables

function isNumericColumn(col, rows) {
  if (col.decimals !== null && col.decimals !== undefined) return true;
  return rows.length > 0 && rows.every((r) => r[col.key] === null || r[col.key] === undefined || typeof r[col.key] === 'number');
}

// Compare two cell values for sorting; dir is 1 (ascending) or -1. Blanks always go last.
function compareValues(a, b, dir) {
  const aMissing = a === null || a === undefined || a === '';
  const bMissing = b === null || b === undefined || b === '';
  if (aMissing || bMissing) return aMissing === bMissing ? 0 : aMissing ? 1 : -1;
  return dir * compareFilled(a, b);
}

function compareFilled(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), NUMBER_LOCALE, { numeric: true });
}

/**
 * Render a table response ({columns, rows, export, title}) into `container`.
 * opts:
 *   columns:    keys to show (default: all, in API order)
 *   caption:    caption text (true = response.title)
 *   limit:      show this many rows first, with a "Show all" button
 *   onRowClick: function(row, tr) for clickable rows (also Enter/Space)
 *   cell:       function(row, col, text) -> Node|string, to decorate a cell
 *   emptyText:  what to say when there are no rows
 *   downloads:  false to hide the CSV/Excel buttons
 * Returns the <table> element (or the empty-state paragraph).
 */
export function table(container, response, opts = {}) {
  const allColumns = (response && response.columns) || [];
  const columns = opts.columns ? allColumns.filter((c) => opts.columns.includes(c.key)) : allColumns;
  const rows = ((response && response.rows) || []).slice();
  container.replaceChildren();
  if (opts.downloads !== false) downloads(container, response);

  if (rows.length === 0) {
    const empty = el('p', { class: 'atlas-empty' }, opts.emptyText || 'No rows for this selection.');
    container.append(empty);
    return empty;
  }

  const numeric = Object.fromEntries(columns.map((c) => [c.key, isNumericColumn(c, rows)]));
  const sortState = { key: null, dir: 1 };
  let showAll = !opts.limit || rows.length <= opts.limit;
  const tbody = el('tbody');

  const headerCells = columns.map((col) => {
    const th = el('th', { scope: 'col', class: numeric[col.key] ? 'num' : null, 'aria-sort': 'none' },
      el('button', { type: 'button', title: 'Sort by this column' },
        col.label, col.unit ? el('span', { class: 'unit' }, `(${col.unit})`) : null));
    th.querySelector('button').addEventListener('click', () => {
      sortState.dir = sortState.key === col.key ? -sortState.dir : 1;
      sortState.key = col.key;
      rows.sort((a, b) => compareValues(a[col.key], b[col.key], sortState.dir));
      for (const other of headerCells) other.setAttribute('aria-sort', 'none');
      th.setAttribute('aria-sort', sortState.dir === 1 ? 'ascending' : 'descending');
      drawBody();
    });
    return th;
  });

  function drawBody() {
    const visible = showAll ? rows : rows.slice(0, opts.limit);
    tbody.replaceChildren(...visible.map((row) => {
      const tr = el('tr');
      for (const col of columns) {
        const text = cellText(row[col.key], col);
        const content = opts.cell ? opts.cell(row, col, text) : text;
        tr.append(el('td', { class: numeric[col.key] ? 'num' : null }, content ?? text));
      }
      if (opts.onRowClick) {
        tr.classList.add('is-clickable');
        tr.tabIndex = 0;
        const choose = () => {
          for (const other of tbody.querySelectorAll('tr.is-selected')) other.classList.remove('is-selected');
          tr.classList.add('is-selected');
          opts.onRowClick(row, tr);
        };
        tr.addEventListener('click', choose);
        tr.addEventListener('keydown', (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); choose(); }
        });
      }
      return tr;
    }));
  }
  drawBody();

  const captionText = opts.caption === true ? response.title : opts.caption;
  const tableEl = el('table', { class: 'atlas-table' },
    captionText ? el('caption', {}, captionText) : null,
    el('thead', {}, el('tr', {}, headerCells)),
    tbody);
  container.append(el('div', { class: 'atlas-table-wrap' }, tableEl));

  if (!showAll) {
    const more = el('button', { type: 'button', class: 'atlas-button atlas-table-more' },
      `Show all ${fmt(rows.length, 0)} rows`);
    more.addEventListener('click', () => { showAll = true; drawBody(); more.remove(); });
    container.append(more);
  }
  return tableEl;
}

/** Fetch a table endpoint and render it, with loading and error states. Returns the response or null. */
export async function loadTable(container, path, params = {}, opts = {}) {
  loading(container);
  try {
    const response = await api(path, params);
    table(container, response, opts);
    return response;
  } catch (err) {
    showError(container, err, opts.what || 'This table');
    return null;
  }
}

// ------------------------------------------------------------------ provenance banner and footer

const BANNER_TEXT = {
  synthetic: 'Every number on this page is made up for testing. Do not use it in any slide, paper or ERA material.',
  approximate: 'Built from hand-built or standard-shape inputs. Indicative only, not an official UETCL figure.',
  open: 'Model estimates from real and open inputs. Not official UETCL figures until the method notes are signed.',
  real: 'Model estimates from real inputs. Not official UETCL figures until the method notes are signed.',
  none: 'No model run has finished yet, so there are no results to show.',
  unknown: 'The data provenance could not be read. Treat every figure as SYNTHETIC.',
};

const FALLBACK_LABEL = {
  synthetic: 'SYNTHETIC: NOT UETCL DATA',
  approximate: 'APPROXIMATE',
  none: 'NO MODEL RUN YET',
  unknown: 'PROVENANCE UNKNOWN',
};

/** The provenance kind, with 'unknown' when there is none. */
export function provenanceKind(prov) {
  return (prov && prov.kind) || 'unknown';
}

/** The watermark text for charts and the map: empty only when the data is real. */
export function watermarkText(prov = currentProvenance) {
  if (!prov) return 'PROVENANCE UNKNOWN: TREAT AS SYNTHETIC';
  if (prov.is_real) return '';
  return prov.watermark || 'SYNTHETIC: NOT UETCL DATA';
}

/** Draw (or redraw) the fixed provenance banner at the top of the page. */
export function banner(prov = currentProvenance) {
  let box = document.getElementById('atlas-banner');
  if (!box) {
    box = el('div', { id: 'atlas-banner' });
    document.body.prepend(box);
  }
  const kind = provenanceKind(prov);
  const label = (prov && prov.label) || FALLBACK_LABEL[kind] || String(kind).toUpperCase();
  box.className = `atlas-banner atlas-banner--${kind}`;
  box.setAttribute('role', prov && prov.is_real ? 'status' : 'alert');
  const parts = [el('strong', {}, label), el('span', {}, BANNER_TEXT[kind] || BANNER_TEXT.unknown)];
  if (prov && prov.run_id !== null && prov.run_id !== undefined) {
    parts.push(el('span', { class: 'atlas-banner-run' }, `Run ${prov.run_id}`));
  }
  box.replaceChildren(...parts); // native replaceChildren would print a null as text
  document.body.dataset.provenance = kind;
  // Tabs and window titles carry the label too, so screenshots of the tab bar do.
  const base = document.title.replace(/^\[[^\]]*\]\s*/, '');
  document.title = prov && prov.is_real ? base : `[${kind === 'approximate' ? 'APPROXIMATE' : 'SYNTHETIC'}] ${base}`;
  return box;
}

/** Fill the footer with the run id, code version and provenance level. */
export function footer(prov = currentProvenance) {
  const box = document.getElementById('atlas-footer');
  if (!box) return null;
  const run = prov && prov.run_id !== null && prov.run_id !== undefined ? String(prov.run_id) : DASH;
  box.replaceChildren(
    el('span', {}, 'UETCL Grid Atlas (MVP)'),
    el('span', {}, 'Run ', el('strong', { 'data-run-id': '' }, run)),
    el('span', {}, 'Code version ', el('strong', {}, (prov && prov.code_version) || DASH)),
    el('span', {}, 'Provenance ', el('strong', {}, (prov && (prov.label || prov.level)) || 'unknown')),
    el('span', {}, el('a', { href: '/api/docs' }, 'API documentation')),
    el('span', {}, el('a', { href: 'about.html' }, 'About, methods and licences')));
  return box;
}

function setProvenance(prov) {
  currentProvenance = prov;
  banner(prov);
  footer(prov);
  redrawCharts();
}

// A response from a newer run (someone pinned a run meanwhile) updates the banner.
function noteProvenance(prov) {
  if (!currentProvenance || currentProvenance.run_id !== prov.run_id || currentProvenance.kind !== prov.kind) {
    setProvenance(prov);
  }
}

async function loadProvenance() {
  try {
    const prov = await api(PROVENANCE_PATH);
    setProvenance(prov);
    return prov;
  } catch (err) {
    setProvenance(null);
    return null;
  }
}

// ------------------------------------------------------------------ charts

const watermarkPlugin = {
  id: 'atlasWatermark',
  afterDraw(chartInstance) {
    const text = watermarkText();
    if (!text) return;
    const { ctx, width, height } = chartInstance;
    const angle = -Math.atan2(height, width);
    const diagonal = Math.hypot(width, height);
    const size = Math.max(12, Math.min(48, (diagonal / text.length) * 1.3));
    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.rotate(angle);
    ctx.font = `700 ${size}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(176, 0, 32, 0.22)';
    ctx.fillText(text, 0, 0);
    ctx.restore();
  },
};

let chartSetupDone = false;
function setupChartJs(Chart) {
  if (chartSetupDone) return;
  chartSetupDone = true;
  Chart.register(watermarkPlugin); // global: every chart on every page gets the watermark
  const css = getComputedStyle(document.documentElement);
  Chart.defaults.font.family = css.getPropertyValue('--font-sans').trim() || 'system-ui, sans-serif';
  Chart.defaults.color = css.getPropertyValue('--text-muted').trim() || '#4f5b67';
  Chart.defaults.borderColor = css.getPropertyValue('--border').trim() || '#d5dbe2';
  Chart.defaults.maintainAspectRatio = false;
}

function redrawCharts() {
  const Chart = window.Chart;
  if (!Chart || !Chart.instances) return;
  for (const instance of Object.values(Chart.instances)) instance.draw();
}

/**
 * Create a Chart.js chart. `target` may be a <canvas> or any container (a canvas is
 * created inside a sized wrapper). Every chart carries the provenance watermark.
 * Returns the Chart instance, or null when Chart.js is not loaded on this page.
 */
export function chart(target, config) {
  const Chart = window.Chart;
  if (!Chart) {
    const where = target instanceof HTMLCanvasElement ? target.parentElement : target;
    if (where) showError(where, new Error('Chart.js (vendor/chartjs/chart.umd.js) is not loaded on this page.'), 'The chart');
    return null;
  }
  setupChartJs(Chart);
  let canvas = target;
  if (!(target instanceof HTMLCanvasElement)) {
    canvas = el('canvas', { role: 'img', 'aria-label': (config && config.ariaLabel) || 'Chart' });
    target.append(el('div', { class: 'atlas-chart' }, canvas));
  }
  return new Chart(canvas, config);
}

// ------------------------------------------------------------------ sections

/** URL query parameters of the page, as a plain object. */
export function pageParams() {
  return Object.fromEntries(new URLSearchParams(window.location.search));
}

/** The ctx object handed to every section's render(el, ctx). */
export function makeContext(section) {
  return {
    api, table, chart, fmt, el, downloads,
    provenance: currentProvenance,
    params: pageParams(),
    // extras beyond the contract, for convenience
    loadTable, loading, showError, columnHeader, watermarkText, section,
  };
}

async function loadSection(section) {
  const modulePath = section.dataset.module || '';
  const title = section.dataset.title || '';
  if (!section.id) section.id = modulePath.replace(/^js\/sections\//, '').replace(/\.js$/, '');
  const body = el('div', { class: 'atlas-section-body' });
  section.replaceChildren(...(title ? [el('h2', {}, title)] : []), body);
  section.setAttribute('aria-busy', 'true');
  loading(body);

  if (!SECTION_MODULE.test(modulePath)) {
    showError(body, new Error(`Invalid section module name "${modulePath}".`), 'This section');
    section.removeAttribute('aria-busy');
    return;
  }
  let mod;
  try {
    mod = await import(new URL(modulePath, document.baseURI).href);
  } catch (err) {
    body.replaceChildren(el('div', { class: 'atlas-notice', role: 'status' },
      el('strong', {}, 'This section is not available yet. '),
      'Its code has not been delivered or failed to load.',
      el('small', {}, `${modulePath}: ${err && err.message ? err.message : err}`)));
    section.removeAttribute('aria-busy');
    return;
  }
  if (typeof mod.default !== 'function') {
    showError(body, new Error(`${modulePath} has no default export render(el, ctx).`), 'This section');
    section.removeAttribute('aria-busy');
    return;
  }
  try {
    body.replaceChildren();
    await mod.default(body, makeContext(section));
  } catch (err) {
    showError(body, err, 'This section');
    console.error(`section ${modulePath} failed`, err);
  } finally {
    section.removeAttribute('aria-busy');
  }
}

/** Load every section on the page, side by side; one failing section never stops the others. */
export async function loadSections(root = document) {
  const sections = Array.from(root.querySelectorAll('section.atlas-section[data-module]'));
  await Promise.all(sections.map((s) => loadSection(s)));
}

// ------------------------------------------------------------------ start-up

function markCurrentNav() {
  const page = window.location.pathname.split('/').pop() || 'index.html';
  for (const link of document.querySelectorAll('.atlas-nav a')) {
    if (link.getAttribute('href') === page) link.setAttribute('aria-current', 'page');
  }
}

let started = false;
/** Run once per page: banner, footer, nav highlight, then the sections. */
export async function init() {
  if (started) return provenanceReady;
  started = true;
  markCurrentNav();
  // Until the API answers, the page's own HTML banner says "checking ... treat as synthetic".
  footer(null);
  const prov = await loadProvenance();
  resolveProvenance(prov);
  await loadSections();
  return prov;
}

init();
