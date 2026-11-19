// Imports page: the import log and the quarantine.
//
// Every delivered file becomes an import batch (/api/meta/imports). Each row that broke
// a rule is logged as an issue (/api/meta/imports/issues); a row with any `error` issue
// was not loaded: that is the quarantine. Warnings were loaded but deserve a look.
//
// Click a batch to see its issues. Filters are kept in the page URL, so a link to
// imports.html?batch_id=12&severity=error opens exactly that view.

const SEVERITIES = ['error', 'warning', 'info'];

export default async function render(root, ctx) {
  const { el, api, table, showError, loading, fmt } = ctx;
  const state = {
    dataset: ctx.params.dataset || '',
    batch_id: ctx.params.batch_id || '',
    severity: ctx.params.severity || '',
  };

  const intro = el('p', {},
    'Each delivered file is one batch. Rows that fail a check are listed below the batches. ',
    el('strong', {}, 'Errors'), ' mean the row was not loaded (quarantined); ',
    el('strong', {}, 'warnings'), ' mean it was loaded but looks unusual.');

  const datasetSelect = el('select', { name: 'dataset' }, el('option', { value: '' }, 'All datasets'));
  const severitySelect = el('select', { name: 'severity' },
    el('option', { value: '' }, 'All severities'),
    SEVERITIES.map((s) => el('option', { value: s }, s)));
  severitySelect.value = state.severity;
  const clearBatch = el('button', { type: 'button', class: 'atlas-button' }, 'Show all batches’ issues');
  const toolbar = el('div', { class: 'atlas-toolbar', role: 'group', 'aria-label': 'Filters' },
    el('label', {}, 'Dataset', datasetSelect),
    el('label', {}, 'Issue severity', severitySelect),
    clearBatch);

  const batchesBox = el('div');
  const issuesHeading = el('h3');
  const issuesSummary = el('p', { class: 'atlas-lede', 'aria-live': 'polite' });
  const issuesBox = el('div');

  root.append(intro, toolbar, el('h3', {}, 'Import batches'), batchesBox, issuesHeading, issuesSummary, issuesBox);

  function syncUrl() {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(state)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(null, '', url);
  }

  function fillDatasets(rows) {
    const names = [...new Set(rows.map((r) => r.dataset).filter(Boolean))].sort();
    datasetSelect.replaceChildren(el('option', { value: '' }, 'All datasets'),
      ...names.map((n) => el('option', { value: n }, n)));
    datasetSelect.value = names.includes(state.dataset) ? state.dataset : '';
  }

  async function loadBatches(first = false) {
    loading(batchesBox, 'Loading batches');
    try {
      const resp = await api('/api/meta/imports', { dataset: state.dataset });
      if (first) {
        // The dataset list comes from an unfiltered call, so every dataset stays selectable.
        const all = state.dataset ? await api('/api/meta/imports') : resp;
        fillDatasets(all.rows);
      }
      table(batchesBox, resp, {
        emptyText: 'No files have been loaded yet. Run ./atlas load (or the synthetic bootstrap).',
        onRowClick: (row) => { state.batch_id = String(row.batch_id); syncUrl(); loadIssues(); },
        cell: (row, col, text) => {
          if (col.key === 'n_errors' && row.n_errors > 0) return el('span', { class: 'sev-error' }, text);
          if (col.key === 'n_warnings' && row.n_warnings > 0) return el('span', { class: 'sev-warning' }, text);
          if (col.key === 'status' && row.status && row.status !== 'ok') return el('span', { class: 'sev-warning' }, text);
          return text;
        },
      });
    } catch (err) {
      showError(batchesBox, err, 'The import log');
    }
  }

  async function loadIssues() {
    issuesHeading.textContent = state.batch_id ? `Issues in batch ${state.batch_id}` : 'Issues in all batches';
    clearBatch.hidden = !state.batch_id;
    issuesSummary.textContent = '';
    loading(issuesBox, 'Loading issues');
    try {
      const resp = await api('/api/meta/imports/issues', {
        batch_id: state.batch_id, dataset: state.dataset, severity: state.severity,
      });
      // A count of the listed rows by severity: a tally of what is shown, not a result.
      const counts = Object.fromEntries(SEVERITIES.map((s) => [s, 0]));
      for (const row of resp.rows) if (row.severity in counts) counts[row.severity] += 1;
      issuesSummary.textContent = `${fmt(resp.rows.length, 0)} issues listed: `
        + SEVERITIES.map((s) => `${fmt(counts[s], 0)} ${s}`).join(', ') + '.';
      table(issuesBox, resp, {
        limit: 200,
        emptyText: 'No issues for this selection. Clean data.',
        cell: (row, col, text) => (col.key === 'severity' ? el('span', { class: `sev-${row.severity}` }, text) : text),
      });
    } catch (err) {
      showError(issuesBox, err, 'The quarantine list');
    }
  }

  datasetSelect.addEventListener('change', () => {
    state.dataset = datasetSelect.value;
    state.batch_id = '';
    syncUrl();
    loadBatches();
    loadIssues();
  });
  severitySelect.addEventListener('change', () => { state.severity = severitySelect.value; syncUrl(); loadIssues(); });
  clearBatch.addEventListener('click', () => { state.batch_id = ''; syncUrl(); loadIssues(); });

  await Promise.all([loadBatches(true), loadIssues()]);
}
