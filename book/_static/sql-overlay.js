// _static/sql-overlay.js
let schemaOverlayEl = null;

// ---------- Overlay structure ----------
function ensureSchemaOverlay() {
    if (schemaOverlayEl) return schemaOverlayEl;
    const el = document.createElement('div');
    el.className = 'sql-schema-overlay';
    el.innerHTML = `
    <div class="sql-schema-panel" role="dialog" aria-modal="true" aria-label="Database Schema">
      <div class="sql-schema-header">
        <span>Database tools</span>
        <button class="sql-schema-close" aria-label="Close">Close</button>
      </div>
      <div class="sql-schema-body">
        <div class="sql-schema-loading">Loading schema…</div>

        <div class="sql-schema-content" style="display:none;">
          <div class="sql-schema-tabs" role="tablist" aria-label="Schema/Data">
            <button class="sql-schema-tab" role="tab" id="tab-schema" aria-controls="panel-schema" aria-selected="true">Schema</button>
            <button class="sql-schema-tab" role="tab" id="tab-data"   aria-controls="panel-data"   aria-selected="false">Data</button>
          </div>

          <!-- Schema tab -->
          <div class="sql-schema-tabpanel active" role="tabpanel" id="panel-schema" aria-labelledby="tab-schema">
            <div class="sql-schema-sections">
              <section class="sql-schema-section">
                <h3>Tables</h3>
                <div class="sql-schema-list tables"></div>
              </section>
              <section class="sql-schema-section">
                <h3>Views</h3>
                <div class="sql-schema-list views"></div>
              </section>
            </div>
            
          </div>

          <!-- Data tab -->
          <div class="sql-schema-tabpanel" role="tabpanel" id="panel-data" aria-labelledby="tab-data">
            <div class="sql-data-config" style="display:flex; gap:.5rem; align-items:center; flex-wrap:wrap;">
                <label for="sql-data-table">Table:</label>
                <select id="sql-data-table">
                    <option value="" selected disabled>Pick a table</option>
                </select>

                <label for="sql-data-view">View:</label>
                <select id="sql-data-view">
                    <option value="" selected disabled>Pick a view</option>
                </select>

                <button class="sql-live-btn" id="sql-data-preview-btn">Preview</button>
            </div>

            <!-- 🟩 Preview area -->
            <div class="sql-data-preview" id="sql-data-preview">
              <div class="sql-data-hint" style="opacity:.8;">Select a table and click Preview.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
    document.body.appendChild(el);

    // Simple focus trap inside the dialog panel
    const panel = el.querySelector('.sql-schema-panel');
    el.addEventListener('keydown', (e) => {
        if (e.key !== 'Tab') return;
        const focusables = panel.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault(); first.focus();
        }
    });


    // close + tab code (unchanged) ...
    const closeBtn = el.querySelector('.sql-schema-close');
    const onClose = () => {
        el.classList.remove('visible');
        el.dispatchEvent(new CustomEvent('schema-overlay:closed'));
    };
    closeBtn.addEventListener('click', onClose);
    el.addEventListener('click', (e) => { if (e.target === el) onClose(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && el.classList.contains('visible')) onClose();
    });

    const tabSchema = el.querySelector('#tab-schema');
    const tabData = el.querySelector('#tab-data');
    const panelSchema = el.querySelector('#panel-schema');
    const panelData = el.querySelector('#panel-data');
    function activateTab(which) {
        const isSchema = which === 'schema';
        tabSchema.setAttribute('aria-selected', String(isSchema));
        tabData.setAttribute('aria-selected', String(!isSchema));
        panelSchema.classList.toggle('active', isSchema);
        panelData.classList.toggle('active', !isSchema);
        (isSchema ? tabSchema : tabData).focus();
    }
    tabSchema.addEventListener('click', () => activateTab('schema'));
    tabData.addEventListener('click', () => activateTab('data'));

    schemaOverlayEl = el;
    return el;
}

// ---------- Helpers ----------
function showLoading(el, show) {
    el.querySelector('.sql-schema-loading').style.display = show ? '' : 'none';
    el.querySelector('.sql-schema-content').style.display = show ? 'none' : '';
}

function renderList(containerEl, items, kind, ctx) {
    // kind: 'table' | 'view'
    containerEl.innerHTML = '';
    if (!items.length) {
        containerEl.innerHTML = `<div class="sql-schema-empty">None</div>`;
        return;
    }
    const frag = document.createDocumentFragment();
    items.forEach(name => {
        const row = document.createElement('div');
        row.className = 'sql-schema-list-item';
        row.setAttribute('data-kind', kind);
        row.setAttribute('data-name', name);

        // Unique ID for aria-controls
        const bodyId = `acc-body-${kind}-${name.replace(/\W+/g, '_')}`;

        row.innerHTML = `
  <div class="sql-acc-head"
       role="button"
       tabindex="0"
       aria-expanded="false"
       aria-controls="${bodyId}">
    ${escapeHtml(name)}
  </div>
  <div class="sql-acc-body" id="${bodyId}"></div>
`;

        // Toggle function (open/close + ARIA)
        async function toggleAccordion() {
            const head = row.querySelector('.sql-acc-head');
            const body = row.querySelector('.sql-acc-body');
            const open = body.classList.contains('visible');

            if (open) {
                body.classList.remove('visible');
                body.innerHTML = '';
                head.setAttribute('aria-expanded', 'false');
                return;
            }
            // show loading
            body.classList.add('visible');
            body.innerHTML = `<div class="sql-data-hint" style="opacity:.8;">Loading columns…</div>`;
            head.setAttribute('aria-expanded', 'true');

            if (!row._columnsLoaded) {
                try {
                    const cols = await fetchColumnsAndFks(ctx.worker, ctx.sharedId, name);
                    row._columnsData = cols;
                    row._columnsLoaded = true;
                } catch (err) {
                    body.innerHTML = `<div style="color:red;">Failed to load columns.</div>`;
                    return;
                }
            }
            body.innerHTML = renderColumnsTable(row._columnsData);
        }

        // Mouse click on header only
        row.querySelector('.sql-acc-head').addEventListener('click', (e) => {
            e.stopPropagation();
            toggleAccordion();
        });

        // Keyboard: Enter/Space to toggle; ArrowUp/ArrowDown to move focus
        row.querySelector('.sql-acc-head').addEventListener('keydown', (e) => {
            const head = e.currentTarget;
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleAccordion();
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                // focus next header
                const next = row.nextElementSibling?.querySelector?.('.sql-acc-head');
                if (next) next.focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                // focus previous header
                const prev = row.previousElementSibling?.querySelector?.('.sql-acc-head');
                if (prev) prev.focus();
            }
        });

        frag.appendChild(row);

    });
    containerEl.appendChild(frag);
}


function fillTableDropdown(el, tables, views) {
    const tableSel = el.querySelector('#sql-data-table');
    const viewSel = el.querySelector('#sql-data-view');

    tableSel.innerHTML = `<option value="" selected disabled>Pick a table</option>`;
    viewSel.innerHTML = `<option value="" selected disabled>Pick a view</option>`;

    tables.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t; opt.textContent = t;
        tableSel.appendChild(opt);
    });

    views.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v; opt.textContent = v;
        viewSel.appendChild(opt);
    });
}

function q(el, sel) { return el.querySelector(sel); }

function renderColumnsTable(columns) {
    // columns: [{name,type,notnull,pk,fk: {table, from, to} | null}]
    const header = `
    <thead><tr>
      <th>Name</th><th>Type</th><th>Not null</th><th>PK</th><th>FK</th>
    </tr></thead>`;
    const rows = columns.map(col => {
        const fk = col.fk ? `${escapeHtml(col.fk.table)}.${escapeHtml(col.fk.to)}` : '';
        return `<tr>
      <td>${escapeHtml(col.name)}</td>
      <td>${escapeHtml(col.type || '')}</td>
      <td>${col.notnull ? '✓' : ''}</td>
      <td>${col.pk ? '✓' : ''}</td>
      <td>${fk}</td>
    </tr>`;
    }).join('');
    return `<table class="sql-columns">${header}<tbody>${rows}</tbody></table>`;
}


// ---------- Basic table renderer (copied from sql-editors.js) ----------
function escapeHtml(s) {
    return String(s)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
}
function renderTable(columns, rows, truncated) {
    const thead = `<thead><tr>${columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>`;
    const tbody = rows.map(r => `<tr>${r.map(v => `<td>${escapeHtml(v)}</td>`).join('')}</tr>`).join('');
    const note = truncated ? `<div class="sql-live-note">Results truncated…</div>` : '';
    return `<table class="sqljs-table">${thead}<tbody>${tbody}</tbody></table>${note}`;
}

// ---------- Main entry ----------
export function openSchemaOverlay(ctx) {
    const { worker, sharedId } = ctx || {};
    const el = ensureSchemaOverlay();
    showLoading(el, true);
    el.classList.add('visible');
    el.querySelector('.sql-schema-close')?.focus();

    // handle schema message
    const onMessage = (ev) => {
        const { id, type, payload } = ev.data || {};
        if (id !== sharedId) return;

        // 🟩 Handle normal schema load
        if (type === 'schema') {
            const { tables, views } = parseSchemaPayload(payload);
            const ctx2 = { worker, sharedId }; // pass to renderList for fetching details
            renderList(q(el, '.sql-schema-list.tables'), tables, 'table', ctx2);
            renderList(q(el, '.sql-schema-list.views'), views, 'view', ctx2);
            fillTableDropdown(el, tables, views);
            showLoading(el, false);
            return;
        }

        // 🟩 Handle exec result for preview
        if (type === 'result' && payload?.client === 'schema-preview') {
            const { columns, rows, truncated } = payload;
            const preview = el.querySelector('#sql-data-preview');
            if (!columns) {
                preview.innerHTML = `<div class="sql-data-hint">No results.</div>`;
            } else {
                preview.innerHTML = renderTable(columns, rows, truncated);
            }
        }

        // 🟩 Handle error messages
        if (type === 'error' && payload?.client === 'schema-preview') {
            const msg = payload.message || 'Error executing preview.';
            el.querySelector('#sql-data-preview').innerHTML = `<div style="color:red;">${escapeHtml(msg)}</div>`;
        }
    };

    worker.addEventListener('message', onMessage);
    const cleanup = () => worker.removeEventListener('message', onMessage);
    const onceClose = () => { el.removeEventListener('schema-overlay:closed', onceClose); cleanup(); };
    el.addEventListener('schema-overlay:closed', onceClose, { once: true });

    // 🟩 Wire the Preview button
    const btn = el.querySelector('#sql-data-preview-btn');
    const tableSel = el.querySelector('#sql-data-table');
    const viewSel = el.querySelector('#sql-data-view');

    btn.onclick = () => {
        const table = tableSel.value;
        const view = viewSel.value;
        const previewEl = el.querySelector('#sql-data-preview');

        const chosen = table || view;
        if (!chosen) {
            previewEl.innerHTML = `<div class="sql-data-hint">Please choose a table or view first.</div>`;
            return;
        }

        previewEl.innerHTML = `<div class="sql-data-hint">Loading preview…</div>`;
        const sql = `SELECT * FROM ${chosen} LIMIT 100;`;

        worker.postMessage({
            id: sharedId,
            type: 'exec',
            payload: { sql, limit: 100, client: 'schema-preview' }
        });
    };


    // request schema on open
    try { worker.postMessage({ id: sharedId, type: 'schema' }); } catch (e) { console.error(e); }
}

// ---------- Schema parsing ----------
function parseSchemaPayload(payload) {
    const res = Array.isArray(payload) ? payload[0] : null;
    if (!res || !Array.isArray(res.values)) return { tables: [], views: [] };
    const idxName = res.columns.indexOf('name');
    const idxType = res.columns.indexOf('type');
    const tables = [], views = [];
    res.values.forEach(row => {
        const name = row[idxName];
        const type = (row[idxType] || '').toLowerCase();
        if (type === 'table') tables.push(name);
        else if (type === 'view') views.push(name);
    });
    return { tables, views };
}

async function fetchColumnsAndFks(worker, sharedId, objName) {
    // Ask both pragmas; results will arrive asynchronously as 'result' messages.
    // We'll wrap them in a Promise that resolves when both arrive.
    const clientTagInfo = `schema-info-${objName}-${Math.random().toString(36).slice(2)}`;
    const clientTagFk = `schema-fk-${objName}-${Math.random().toString(36).slice(2)}`;

    return new Promise((resolve, reject) => {
        const result = { info: null, fks: [] };
        const onMessage = (ev) => {
            const { id, type, payload } = ev.data || {};
            if (id !== sharedId || type !== 'result') return;
            if (payload?.client === clientTagInfo) {
                // PRAGMA table_info → columns: cid,name,type,notnull,dflt_value,pk
                const r = payload;
                if (!r.columns) { result.info = []; }
                else {
                    const idx = {};
                    r.columns.forEach((c, i) => idx[c] = i);
                    result.info = (r.rows || r.values || []).map(row => ({
                        name: row[idx.name],
                        type: row[idx.type],
                        notnull: !!row[idx.notnull],
                        pk: !!row[idx.pk]
                    }));
                }
            }
            if (payload?.client === clientTagFk) {
                // PRAGMA foreign_key_list → id,seq,table,from,to,on_update,on_delete,match
                const r = payload;
                if (r.columns) {
                    const idx = {};
                    r.columns.forEach((c, i) => idx[c] = i);
                    result.fks = (r.rows || r.values || []).map(row => ({
                        table: row[idx.table],
                        from: row[idx.from],
                        to: row[idx.to]
                    }));
                }
            }
            if (result.info !== null && result.fks) {
                worker.removeEventListener('message', onMessage);
                // join FK info onto columns by 'from' column name
                const fkByFrom = new Map(result.fks.map(f => [f.from, f]));
                const cols = result.info.map(c => ({
                    ...c,
                    fk: fkByFrom.get(c.name) || null
                }));
                resolve(cols);
            }
        };
        worker.addEventListener('message', onMessage);

        try {
            worker.postMessage({
                id: sharedId,
                type: 'exec',
                payload: { sql: `PRAGMA table_info(${objName});`, client: clientTagInfo, limit: 500 }
            });
            worker.postMessage({
                id: sharedId,
                type: 'exec',
                payload: { sql: `PRAGMA foreign_key_list(${objName});`, client: clientTagFk, limit: 500 }
            });
        } catch (e) {
            worker.removeEventListener('message', onMessage);
            reject(e);
        }
    });
}
