// _static/sql-editors.js
const MONACO_BASE = '/_static/monaco';

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

function initEditors(monaco) {
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

    const run = () => {
      const sql = editor.getValue();
      ui.outputEl.textContent = 'SQL captured (not executed):\n\n' + sql;
    };
    ui.runBtn.addEventListener('click', run);

    ui.resetBtn.addEventListener('click', () => {
      editor.setValue(initialSql || 'SELECT 1;');
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
    initEditors(monaco);
  } catch (e) {
    console.error('Monaco init failed:', e);
  }
});
