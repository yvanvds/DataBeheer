// _static/sql-editors.js
// --- Config ---
const STATIC_BASE = window.__STATIC_BASE__ || '/_static';
const MONACO_BASE = `${STATIC_BASE}/monaco`;
const SHARED_ID   = 'db:' + location.pathname; // one in-memory DB per page
const clients     = new Map();                  // clientId -> output <div>
let worker = null;

// --- Utils ---
function resolveStatic(url) {
  return url && url.startsWith('/_static/')
    ? STATIC_BASE + url.slice('/_static'.length)
    : url;
}

function escapeHtml(s) {
  return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
}
function renderTable(columns, rows, truncated) {
  const thead = `<thead><tr>${columns.map(c=>`<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>`;
  const tbody = rows.map(r => `<tr>${r.map(v => `<td>${escapeHtml(v)}</td>`).join('')}</tr>`).join('');
  const note  = truncated ? `<div class="sql-live-note">Results truncated…</div>` : '';
  return `<table class="sqljs-table">${thead}<tbody>${tbody}</tbody></table>${note}`;
}
function onReady(cb){ 
  if(/complete|interactive/.test(document.readyState)) cb(); 
  else document.addEventListener('DOMContentLoaded', cb, {once:true}); 
}

// --- Page-level seed selector (cell tagged `sql-db`) ---
function pickPageSeedUrl() {
  const sel = document.querySelector('.cell.tag_sql-db, .cell.tag-sql-db');
  console.log('pickPageSeedUrl: found selector cell:', sel);
  if (!sel) return null;

  const pre = sel.querySelector('pre');
  const url = (pre?.textContent || sel.textContent || '').trim();
  sel.remove();
  if (!url || !/^(\.|\/|https?:)/.test(url)) return null;
  return url;
}

// --- Monaco loader ---
function loadMonaco() {
  console.log('Loading monaco from', MONACO_BASE);

  return new Promise((resolve) => {
    window.require.config({ baseUrl: MONACO_BASE, paths: { 'vs': `${MONACO_BASE}/vs` } });
    window.require(['vs/editor/editor.main'], () => resolve(window.monaco));
  });
}

// --- Find + wrap SQL cells ---
function findSqlBlocks() {
  const blocks = [];
  document.querySelectorAll('.cell.tag_sql-live, .cell.tag-sql-live').forEach(cell => {
    const pre = cell.querySelector('.cell_input pre, pre'); if (!pre) return;
    blocks.push({ cell, pre, initialSql: pre.textContent || '' });
  });
  console.log('findSqlBlocks: found tagged sql-live cells:', blocks.length);
  
  // Fallback (optional) by language class
  if (blocks.length === 0) {
    document.querySelectorAll('pre > code.language-sql, pre > code.language-mssql, div.highlight-sql pre, div.highlight-mssql pre')
      .forEach(el => {
        const cell = el.closest('.cell') || el.closest('div.highlight') || el.closest('pre');
        const pre  = cell?.querySelector('pre') || el.closest('pre') || el;
        const sql  = (el.textContent || pre?.textContent || '').trim();
        if (cell && sql) blocks.push({ cell, pre, initialSql: sql });
      });
  }

  const seen = new Set();
  return blocks.filter(({cell}) => (seen.has(cell) ? false : (seen.add(cell), true)));
}

function wrapCell(cell, initialSql, preToHide) {
  if (preToHide) preToHide.style.display = 'none';
  const cellInput = cell.querySelector('.cell_input'); if (cellInput) cellInput.remove();

  const wrap = document.createElement('div');
  wrap.className = 'sql-live-wrap';
  wrap.innerHTML = `
    <div class="sql-live-toolbar">
      <span class="title">Interactive SQL (Monaco)</span>
      <button class="sql-live-btn run">Run</button>
      <button class="sql-live-btn reset">Reset</button>
      <span class="sql-live-note">Ctrl/Cmd+Enter to run</span>
    </div>
    <div class="sql-live-editor"></div>
    <div class="sql-live-output">Output will appear here.</div>
  `;
  cell.appendChild(wrap);
  return {
    editorEl: wrap.querySelector('.sql-live-editor'),
    outputEl: wrap.querySelector('.sql-live-output'),
    runBtn  : wrap.querySelector('.run'),
    resetBtn: wrap.querySelector('.reset'),
  };
}

// --- Wire editors to the SINGLE shared DB session ---
function initEditors(monaco, seedBuf) {
  console.log('initEditors: setting up SQL editors');
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

    const client = Math.random().toString(36).slice(2);
    clients.set(client, ui.outputEl);

    const run = () => worker.postMessage({
      id: SHARED_ID,
      type: 'exec',
      payload: { sql: editor.getValue(), limit: 500, client }
    });
    ui.runBtn.addEventListener('click', run);
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, run);

    ui.resetBtn.addEventListener('click', () => {
      worker.postMessage({
        id: SHARED_ID,
        type: 'reset',
        payload: seedBuf ? { seedBuf: seedBuf.slice(0) } : {}
      });
      clients.forEach(el => el.textContent = 'Output will appear here.');
    });
  });
}

// --- Boot ---
onReady(async () => {
  try {
    const monaco = await loadMonaco();

    const seedUrlRaw = pickPageSeedUrl(); // e.g. "/_static/db/webshop.db"
    const seedUrl = seedUrlRaw?.startsWith('/_static/')
  ? STATIC_BASE + seedUrlRaw.slice('/_static'.length)
  : seedUrlRaw;
    console.log('SQL editor seed DB URL:', seedUrl);

    let seedBuf = null;
    if (seedUrl) {
      const res = await fetch(seedUrl);
      console.debug('[seed] fetch', seedUrl, res.status, res.statusText);
      if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
      seedBuf = await res.arrayBuffer();
      console.debug('[seed] bytes', seedBuf.byteLength);
    }

    // single worker for the page
    worker = new Worker(`${STATIC_BASE}/sql-worker.js`);

    // route results by `client`
    worker.onmessage = (ev) => {
      const { type, payload } = ev.data || {};
      if (type === 'error') {
        const { client, message } = payload || {};
        const out = clients.get(client);
        if (out) out.textContent = 'Error: ' + (message || 'Unknown error');
        return;
      }

      if (type !== 'result') return; // keep it simple; errors still show via console if thrown
      const { client, columns, rows, truncated } = payload || {};
      const out = clients.get(client);
      if (!out) return;
      out.innerHTML = columns ? renderTable(columns, rows, truncated) : 'OK';
    };

    // init the shared DB once
    worker.postMessage({
      id: SHARED_ID,
      type: 'init',
      payload: seedBuf ? { seedBuf: seedBuf.slice(0) } : {}
    });

    // create editors
    initEditors(monaco, seedBuf);

  } catch (e) {
    console.error('Monaco/SQL init failed:', e);
  }
});
