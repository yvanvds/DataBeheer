// Figure out the correct _static base at runtime
const STATIC_BASE = window.__STATIC_BASE__ || '/_static';
const MONACO_BASE = STATIC_BASE + '/monaco';


function escapeHtml(s) {
  return String(s)
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;');
}

function renderTable(columns, rows, truncated) {
  const thead = `<thead><tr>${columns.map(c=>`<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>`;
  const tbody = rows.map(r => `<tr>${r.map(v => `<td>${escapeHtml(v)}</td>`).join('')}</tr>`).join('');
  const note  = truncated ? `<div class="sql-live-note">Results truncated…</div>` : '';
  return `<table class="sqljs-table">${thead}<tbody>${tbody}</tbody></table>${note}`;
}

async function createClassicWorker(staticBase) {
  const bootstrap = `
    try {
      self.__STATIC_BASE__ = ${JSON.stringify(STATIC_BASE)};
      importScripts(self.__STATIC_BASE__ + '/sqljs/sql-wasm.js',
                    self.__STATIC_BASE__ + '/sql-worker-core.js');
      postMessage({ id: null, type: 'debug', payload: { msg: 'bootstrap: importScripts OK' } });
    } catch (e) {
      postMessage({ id: null, type: 'debug', payload: { msg: 'bootstrap: importScripts FAILED', data: String(e) } });
    }
  `;
  const blob = new Blob([bootstrap], { type: 'application/javascript' });
  return new Worker(URL.createObjectURL(blob)); // classic worker, guaranteed
}

const worker = await createClassicWorker(STATIC_BASE);// classic worker
const listeners = new Map(); // id -> { outputEl }
worker.onmessage = (ev) => {
  const { id, type, payload } = ev.data || {};

  if (type === 'debug') {
    // Centralized debug logging from the worker:
    const { msg, data } = payload || {};
    console.debug('[sql-worker]', msg, data);
    return;
  }

  const L = listeners.get(id);
  if (!L) return;

  if (type === 'result') {
    const { columns, rows, truncated } = payload || {};
    if (!columns || !rows) L.outputEl.textContent = 'OK';
    else L.outputEl.innerHTML = renderTable(columns, rows, truncated);
  } else if (type === 'error') {
    L.outputEl.textContent = 'Error: ' + payload;
  } else if (type === 'schema') {
    // render or ignore for now
  }
};

function pickPageSeedUrl() {
  // Accept either .tag_sql-db or .tag-sql-db
  const sel = document.querySelector('.cell.tag_sql-db, .cell.tag-sql-db');
  if (!sel) return null;

  // Grab first <pre> or its text content
  const pre = sel.querySelector('pre');
  let url = (pre?.textContent || sel.textContent || '').trim();

  // Hide/remove the selector cell from the page
  sel.remove();

  // Basic sanity: must start with / or ./ or http
  if (!url || !/^(\.|\/|https?:)/.test(url)) return null;
  return url;
}

function loadMonaco() {
  return new Promise((resolve) => {
    // Monaco AMD loader (from loader.js)
    window.require.config({ paths: { 'vs': `${MONACO_BASE}/vs` } });
    window.require(['vs/editor/editor.main'], () => resolve(window.monaco));
  });
}

// Identify SQL code-cells in Jupyter Book output.
// We target both ipynb-rendered cells and plain markdown fences.
//
function findSqlBlocks() {
  const blocks = [];

  // Prefer cells explicitly tagged as sql-live (covers both underscore & dash)
  const taggedCells = document.querySelectorAll(
    '.cell.tag_sql-live, .cell.tag-sql-live'
  );

  taggedCells.forEach(cell => {
    // Find the first <pre> that contains the rendered code
    const pre = cell.querySelector('.cell_input pre, pre');
    if (!pre) return;

    const sql = pre.textContent || '';
    blocks.push({ cell, pre, initialSql: sql });
  });

  // Fallback: if you ever want auto-detection by language class too, keep this:
  if (blocks.length === 0) {
    const langCandidates = document.querySelectorAll(
      'pre > code.language-sql, pre > code.language-mssql, div.highlight-sql pre, div.highlight-mssql pre'
    );
    langCandidates.forEach(el => {
      const cell = el.closest('.cell') || el.closest('div.highlight') || el.closest('pre');
      if (!cell) return;
      const pre = cell.querySelector('pre') || el.closest('pre') || el;
      const sql = (el.textContent || pre?.textContent || '').trim();
      if (sql) blocks.push({ cell, pre, initialSql: sql });
    });
  }

  // Deduplicate by cell element
  const seen = new Set();
  return blocks.filter(({ cell }) => (seen.has(cell) ? false : (seen.add(cell), true)));
}

function wrapCell(cell, initialSql, preToHide) {
  if (preToHide) preToHide.style.display = 'none';

  // Remove entire input container (with copy button and highlight)
  const cellInput = cell.querySelector('.cell_input');
  if (cellInput) cellInput.remove();
  
  const wrap = document.createElement('div');
  wrap.className = 'sql-live-wrap';
  wrap.innerHTML = `
    <div class="sql-live-toolbar">
      <span class="title">Interactive SQL (Monaco)</span>
      <button class="sql-live-btn run">Run (no DB yet)</button>
      <button class="sql-live-btn reset">Reset</button>
      <span class="sql-live-note">DB wiring comes later</span>
    </div>
    <div class="sql-live-editor"></div>
    <div class="sql-live-output">Output will appear here.</div>
  `;


  cell.appendChild(wrap);

  return {
    editorEl: wrap.querySelector('.sql-live-editor'),
    outputEl: wrap.querySelector('.sql-live-output'),
    runBtn:   wrap.querySelector('.run'),
    resetBtn: wrap.querySelector('.reset'),
    wrap
  };
}

function initEditors(monaco, worker, listeners, seedBuf) {
  const blocks = findSqlBlocks();
  blocks.forEach(({ cell, pre, initialSql }) => {
    const ui = wrapCell(cell, initialSql, pre);

    const editor = monaco.editor.create(ui.editorEl, {
      value: initialSql || 'SELECT 1;',
      language: 'sql',
      automaticLayout: true,
      fontSize: 14,
      minimap: { enabled: false }
    });

    // Session id per editor
    const id = Math.random().toString(36).slice(2);
    listeners.set(id, { outputEl: ui.outputEl });

    // INIT: send seed buffer (transfer it so we don't copy)
    if (seedBuf) {
      const bufCopy = seedBuf.slice(0); // keep our local copy
      worker.postMessage({ id, type: 'init', payload: { seedBuf: bufCopy }}, [bufCopy]);
    } else {
      worker.postMessage({ id, type: 'init', payload: {} });
    }

    const run = () => {
      const sql = editor.getValue();
      worker.postMessage({ id, type: 'exec', payload: { sql, limit: 500 }});
    };
    ui.runBtn.addEventListener('click', run);
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, run);

    ui.resetBtn.addEventListener('click', () => {
      if (seedBuf) {
        const bufCopy = seedBuf.slice(0);
        worker.postMessage({ id, type: 'reset', payload: { seedBuf: bufCopy }}, [bufCopy]);
      } else {
        worker.postMessage({ id, type: 'reset', payload: {} });
      }
      ui.outputEl.textContent = 'Output will appear here.';
    });
  });
}



// Lazy init: wait for DOM ready (after JB finishes rendering)
function onReady(cb) {
  if (document.readyState === 'complete' || document.readyState === 'interactive') cb();
  else document.addEventListener('DOMContentLoaded', cb, { once: true });
}

onReady(async () => {
  try {
    const monaco = await loadMonaco();

    // 1) Resolve seed DB URL from the invisible selector cell (or null)
    const seedUrl = pickPageSeedUrl(); // e.g. "/_static/db/webshop.db"

    // 2) Fetch the DB once (optional)
    let seedBuf = null;
    if (seedUrl) {
      try {
        const res = await fetch(seedUrl);
        console.debug('[seed] fetch', seedUrl, res.status, res.statusText);
        if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
        seedBuf = await res.arrayBuffer();
        console.debug('[seed] bytes', seedBuf.byteLength);
      } catch (e) {
        console.warn('Could not fetch seed DB', seedUrl, e);
      }
    }

    // 3) Create one worker for the page (classic worker)
    const worker = await createClassicWorker(STATIC_BASE);

    // 4) Wire the worker listener map (if not already present)
    const listeners = new Map();
    worker.onmessage = (ev) => {
      const { id, type, payload } = ev.data || {};
      const L = listeners.get(id);
      if (!L) return;
      if (type === 'result') {
        const { columns, rows, truncated } = payload || {};
        if (!columns || !rows) L.outputEl.textContent = 'OK';
        else L.outputEl.innerHTML = renderTable(columns, rows, truncated);
      } else if (type === 'error') {
        L.outputEl.textContent = 'Error: ' + payload;
      } else if (type === 'schema') {
        // could render a schema browser later
      }
    };

    // 5) Init editors (pass seedBuf to worker.init + worker.reset)
    initEditors(monaco, worker, listeners, seedBuf);

  } catch (e) {
    console.error('Monaco/SQL init failed:', e);
  }
});

