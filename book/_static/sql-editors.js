// _static/sql-editors.js
// Interactieve SQL-cellen op CodeMirror 6 + sql.js (issue #17).
//
// Dit bestand is een ES-module: _ext/sanitize_static_assets.py zorgt dat het
// met type="module" op elke pagina staat. Het importeert de gevendorde
// CodeMirror-bundel (_static/codemirror/codemirror.js — bron:
// scripts/codemirror-entry.mjs, bouwen met `npm run build:editor`).
//
// Werking per pagina:
//   - een cel met tag `sql-db` bevat het pad naar de seed-database; ontbreekt
//     die cel, dan start de pagina met een lege databank (CREATE TABLE-lessen
//     die van nul beginnen) — verder werkt alles hetzelfde;
//   - elke cel met tag `sql-live` wordt een editor (expliciete tag — er is
//     bewust géén fallback meer die alle ```sql-blokken omzet);
//   - alle editors delen één sql.js-database in een worker, met een watchdog
//     die runaway queries stopt en de database opnieuw laadt;
//   - schema-aware autocomplete via @codemirror/lang-sql, na elke geslaagde
//     Run ververst (CREATE TABLE-lessen);
//   - leerlingqueries worden per cel bewaard in localStorage (#14): bij het
//     heropenen van de pagina staat het eigen werk er weer, en de knop
//     "Startcode" zet de originele opgave terug;
//   - de databank zelf wordt per pagina bewaard in IndexedDB (#41): na elke
//     Run die de databank wijzigt, stuurt de worker een snapshot
//     (db.export()) die hier wordt weggeschreven; bij het heropenen van de
//     pagina wordt die kopie geopend in plaats van de seed, en "Reset db" gaat
//     terug naar de seed (opslag in sql-db-store.js);
//   - onder de laatste cel staat de balk "Mijn werk": "Download mijn queries"
//     (#30) exporteert alle celinhoud van de pagina als één .sql-bestand,
//     "Upload mijn queries" (#35) zet zo'n bestand weer terug (bestandsformaat
//     in sql-queries-file.js) en "Download mijn databank" (#41) biedt de
//     databank aan als .db-bestand (SQLite-bestand, te openen in elk
//     SQLite-programma en in te dienen via Teams);
//   - Run voert de selectie uit, of anders het statement onder de cursor
//     (subtiel gemarkeerd); "Run alles" (Mod-Shift-Enter) voert de hele cel
//     uit (#34, statementgrenzen in sql-statements.js).

import {
  EditorState, Compartment, StateField,
  EditorView, Decoration, keymap, lineNumbers, drawSelection,
  highlightActiveLine, highlightActiveLineGutter,
  defaultKeymap, history, historyKeymap, indentWithTab,
  indentOnInput, bracketMatching, syntaxHighlighting, HighlightStyle,
  autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap,
  sql, SQLite, tags,
} from './codemirror/codemirror.js';
import { splitStatements, statementAt } from './sql-statements.js';
import { buildQueriesFile, parseQueriesFile, pageName } from './sql-queries-file.js';
import { readSavedDb, writeSavedDb, deleteSavedDb } from './sql-db-store.js';

// --- Config ---
const STATIC_BASE = new URL('.', import.meta.url).href.replace(/\/$/, '');
const SHARED_ID = 'db:' + location.pathname; // één in-memory database per pagina
const RUN_LIMIT = 500;                       // max. rijen per resultaat
const RUN_TIMEOUT_MS = 10000;                // watchdog voor runaway queries

const OUTPUT_PLACEHOLDER = 'De resultaten verschijnen hier.';

const clients = new Map();    // clientId -> output-<div>
const cells = [];             // interne administratie per editorcel
const editorsApi = [];        // publieke API per cel (window.sqlLive.editors)
const watchdogs = new Map();  // clientId -> { timer, outputEl }
let worker = null;
let seedBuf = null;           // ArrayBuffer van de seed-database (voor reset/reseed)
let dbReady = false;
let signalReady = null;

// Bewaarde databank (#41). savedBuf is de laatste snapshot van de worker
// (Uint8Array): het herstelpunt na een herlaad (uit IndexedDB) én na een
// watchdog-herstart (in het geheugen, ook als IndexedDB niet kan). dbSaved
// zegt of die snapshot ook echt in IndexedDB staat. storeGen maakt een
// snapshot die nog onderweg is ongeldig zodra "Reset db" wordt geklikt.
let savedBuf = null;
let dbSaved = false;
let storeGen = 0;
let storageWarned = false;
const ownDbBadges = [];       // "eigen databank"-label per celtoolbar
let reportWork = () => {};    // statusregel in de balk "Mijn werk"

// --- Utils ---
function resolveStatic(url) {
  return url && url.startsWith('/_static/')
    ? STATIC_BASE + url.slice('/_static'.length)
    : url;
}

function onReady(cb) {
  if (/complete|interactive/.test(document.readyState)) cb();
  else document.addEventListener('DOMContentLoaded', cb, { once: true });
}

// --- Opslag van leerlingqueries (#14) ---
// Sleutel per editor: `sql:{pad}:{index}`, met de index uit de volgorde van
// findSqlBlocks(). Bewust géén hash van de startcode in de sleutel: een
// typo-fix in een opgave mag het bewaarde leerlingwerk niet wissen. De weg
// terug naar de opgave is de knop "Startcode"; zolang de celinhoud afwijkt
// van de startcode toont de toolbar "eigen versie".
// localStorage kan geblokkeerd zijn (private browsing) of vol zitten: elke
// toegang zit in try/catch en de editor werkt dan gewoon zonder opslag.
const SAVE_DEBOUNCE_MS = 500;

function storageKey(index) {
  return `sql:${location.pathname}:${index}`;
}

function readSaved(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // opslag geblokkeerd — start gewoon met de startcode
  }
}

function writeSaved(key, value, initialDoc) {
  try {
    if (value === initialDoc) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* opslag geblokkeerd of vol — geen opslag, wel een werkende editor */
  }
}

// --- Render-helpers (ook gebruikt door sql-overlay.js) ---
export function escapeHtml(s) {
  return String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

function renderValue(v) {
  // NULL gestileerd tonen — niet als de tekst "null" (verwarrend in de les
  // over NULL versus de tekstwaarde 'null').
  if (v === null || v === undefined) return '<td><span class="sql-null">NULL</span></td>';
  return `<td>${escapeHtml(v)}</td>`;
}

export function renderTable({ columns, rows, truncated }) {
  const thead = `<thead><tr>${columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>`;
  const tbody = rows.map(r => `<tr>${r.map(renderValue).join('')}</tr>`).join('');
  const note = truncated
    ? `<div class="sql-live-note">Afgekapt: alleen de eerste ${rows.length} rijen worden getoond.</div>`
    : '';
  return `<table class="sqljs-table">${thead}<tbody>${tbody}</tbody></table>${note}`;
}

export function renderResults(results) {
  // Elk statement met resultaatrijen krijgt zijn eigen tabel (niet enkel het eerste).
  if (!results || !results.length) {
    return '<div class="sql-live-note">OK — uitgevoerd, geen resultaatrijen.</div>';
  }
  return results.map(renderTable).join('');
}

// --- Seed-cel (cel met tag `sql-db`) ---
function pickPageSeedUrl() {
  const sel = document.querySelector('.cell.tag_sql-db, .cell.tag-sql-db');
  if (!sel) return null;

  const pre = sel.querySelector('pre');
  const url = (pre?.textContent || sel.textContent || '').trim();
  sel.remove();
  if (!url || !/^(\.|\/|https?:)/.test(url)) return null;
  return url;
}

// --- Interactieve cellen: alleen expliciet getagd met `sql-live` ---
function findSqlBlocks() {
  const blocks = [];
  document.querySelectorAll('.cell.tag_sql-live, .cell.tag-sql-live').forEach(cell => {
    const pre = cell.querySelector('.cell_input pre, pre');
    if (!pre) return;
    blocks.push({ cell, initialSql: (pre.textContent || '').trim() });
  });
  return blocks;
}

function wrapCell(cell) {
  const cellInput = cell.querySelector('.cell_input');
  if (cellInput) cellInput.remove();

  const wrap = document.createElement('div');
  wrap.className = 'sql-live-wrap';
  wrap.innerHTML = `
    <div class="sql-live-toolbar">
      <span class="title">Interactieve SQL</span>
      <span class="sql-live-own" hidden title="Deze cel toont jouw bewaarde versie, niet de originele startcode">eigen versie</span>
      <span class="sql-live-own-db" hidden title="De databank bevat jouw wijzigingen (van nu of van een vorig bezoek) en blijft in deze browser bewaard. Reset db zet de startgegevens terug">eigen databank</span>
      <button class="sql-live-btn run" title="Voert je selectie uit, of anders het statement waar de cursor staat (Ctrl/Cmd+Enter)">Run</button>
      <button class="sql-live-btn runall" title="Voert alle statements in deze cel uit (Ctrl/Cmd+Shift+Enter)">Run alles</button>
      <button class="sql-live-btn startcode" title="Zet de originele startcode van deze cel terug">Startcode</button>
      <button class="sql-live-btn reset" title="Zet de databank terug naar de startgegevens (je query blijft staan)">Reset db</button>
      <button class="sql-live-btn schema">Schema</button>
      <span class="sql-live-note">Ctrl/Cmd+Enter: statement bij de cursor · +Shift: alles</span>
    </div>
    <div class="sql-live-editor"></div>
    <div class="sql-live-output">${OUTPUT_PLACEHOLDER}</div>
  `;
  cell.appendChild(wrap);
  return {
    editorEl: wrap.querySelector('.sql-live-editor'),
    outputEl: wrap.querySelector('.sql-live-output'),
    ownEl: wrap.querySelector('.sql-live-own'),
    ownDbEl: wrap.querySelector('.sql-live-own-db'),
    runBtn: wrap.querySelector('.run'),
    runAllBtn: wrap.querySelector('.runall'),
    startBtn: wrap.querySelector('.startcode'),
    resetBtn: wrap.querySelector('.reset'),
    schemaBtn: wrap.querySelector('.schema'),
  };
}

// --- CodeMirror in de Plink-huisstijl ---
// De kleuren komen uit de `--sql-*`-tokens in sql-editors.css; die schakelen
// zelf mee met de themaknop van het boek (html[data-theme]), dus één thema
// volstaat voor light én dark.
const plinkTheme = EditorView.theme({
  '&': {
    height: '100%',
    backgroundColor: 'var(--sql-surface)',
    color: 'var(--sql-text)',
    fontSize: '0.875rem',
  },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { fontFamily: 'var(--sql-font-mono)', lineHeight: '1.55' },
  '.cm-content': { caretColor: 'var(--sql-accent)' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--sql-accent)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground, .cm-content ::selection': {
    backgroundColor: 'var(--sql-selection)',
  },
  '.cm-activeLine': { backgroundColor: 'var(--sql-active-line)' },
  '.cm-gutters': {
    backgroundColor: 'var(--sql-surface)',
    color: 'var(--sql-text-caption)',
    borderRight: '1px solid var(--sql-border)',
  },
  '.cm-activeLineGutter': {
    backgroundColor: 'var(--sql-active-line)',
    color: 'var(--sql-text)',
  },
  '.cm-tooltip': {
    backgroundColor: 'var(--sql-surface-raised)',
    color: 'var(--sql-text)',
    border: '1px solid var(--sql-border-strong)',
    borderRadius: 'var(--sql-radius)',
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul': {
    fontFamily: 'var(--sql-font-mono)',
    fontSize: '0.8125rem',
  },
  '.cm-tooltip-autocomplete ul li[aria-selected]': {
    backgroundColor: 'var(--sql-accent)',
    color: 'var(--sql-on-accent)',
  },
  '.cm-completionMatchedText': { textDecoration: 'none', fontWeight: '700' },
});

// Syntaxkleuren via CSS-klassen (gestyled in sql-editors.css met Plink-tokens).
const plinkHighlight = HighlightStyle.define([
  { tag: tags.keyword, class: 'sql-tok-keyword' },
  { tag: [tags.bool, tags.null], class: 'sql-tok-keyword' },
  { tag: [tags.operator, tags.number, tags.typeName], class: 'sql-tok-plain' },
  { tag: [tags.string, tags.special(tags.string)], class: 'sql-tok-string' },
  { tag: tags.comment, class: 'sql-tok-comment' },
]);

// --- Schema-aware autocomplete ---
let currentSchema = {};

function makeSqlLang(schema) {
  return sql({ dialect: SQLite, schema, upperCaseKeywords: true });
}

function applySchema(schema) {
  currentSchema = schema || {};
  cells.forEach(({ view, langCompartment }) => {
    view.dispatch({ effects: langCompartment.reconfigure(makeSqlLang(currentSchema)) });
  });
}

function refreshCatalog() {
  if (!worker) return;
  worker.postMessage({ id: SHARED_ID, type: 'catalog' });
}

// --- Worker + watchdog ---
// Wat de worker moet openen: de seed (als de pagina er een heeft) en, tenzij
// we bewust naar de seed terug willen, de bewaarde databank. Kopieën, want
// de originelen blijven hier als herstelpunt.
function dbPayload({ withSaved }) {
  const payload = {};
  if (seedBuf) payload.seedBuf = seedBuf.slice(0);
  if (withSaved && savedBuf) payload.savedBuf = savedBuf.slice(0);
  return payload;
}

// Belooft `restored`: true als de worker de bewaarde databank opende.
function startWorker() {
  worker = new Worker(`${STATIC_BASE}/sql-worker.js`);
  worker.onmessage = onWorkerMessage;
  const ready = new Promise(resolve => { signalReady = resolve; });
  worker.postMessage({ id: SHARED_ID, type: 'init', payload: dbPayload({ withSaved: true }) });
  return ready;
}

function armWatchdog(client, outputEl) {
  clearWatchdog(client);
  watchdogs.set(client, {
    timer: setTimeout(onRunTimeout, RUN_TIMEOUT_MS),
    outputEl,
  });
}

function clearWatchdog(client) {
  const w = watchdogs.get(client);
  if (w) {
    clearTimeout(w.timer);
    watchdogs.delete(client);
  }
}

async function onRunTimeout() {
  // Runaway query (bv. een cartesisch product): de worker zit vast in exec.
  // Termineer hem en seed de database opnieuw, met een duidelijke melding in
  // elke cel die nog op een resultaat wachtte.
  const waiting = [...watchdogs.values()].map(w => w.outputEl);
  watchdogs.forEach(w => clearTimeout(w.timer));
  watchdogs.clear();
  try { worker?.terminate(); } catch { /* al gestopt */ }
  worker = null;
  dbReady = false;
  waiting.forEach(el => {
    el.innerHTML =
      '<div class="sql-live-error">De query duurde te lang en werd gestopt. De database wordt opnieuw geladen…</div>';
  });
  try {
    const restored = await startWorker(); // laatste snapshot (#41), anders de seed
    const state = restored ? 'de gegevens van je laatste geslaagde Run' : 'de startgegevens';
    waiting.forEach(el => {
      el.innerHTML =
        '<div class="sql-live-error">De query duurde te lang en werd gestopt. ' +
        `De database is opnieuw geladen met ${state} — controleer je query ` +
        '(bv. de JOIN-voorwaarden) en probeer opnieuw.</div>';
    });
  } catch (e) {
    console.error('SQL-editor: database opnieuw laden mislukt:', e);
  }
}

function onWorkerMessage(ev) {
  const { id, type, payload } = ev.data || {};
  if (id !== SHARED_ID) return;

  if (type === 'ready') {
    dbReady = true;
    const restored = !!payload?.restored;
    if (payload?.savedRejected) discardSavedDb(); // onbruikbare kopie: terug naar de seed
    if (restored) setOwnDb(true);
    if (signalReady) { signalReady(restored); signalReady = null; }
    refreshCatalog();
    return;
  }

  if (type === 'snapshot') {
    // Zolang een reset onderweg is (dbReady false) hoort een snapshot nog bij
    // de databank van vóór de reset: negeren, de reset wint.
    if (dbReady) persistSnapshot(payload?.bytes);
    return;
  }

  if (type === 'catalog') {
    applySchema(payload?.schema);
    return;
  }

  if (type === 'error') {
    const { client, message } = payload || {};
    const out = clients.get(client);
    if (!out) return; // bv. berichten van het schema-overlay
    clearWatchdog(client);
    out.innerHTML = `<div class="sql-live-error">Fout: ${escapeHtml(message || 'onbekende fout')}</div>`;
    return;
  }

  if (type === 'result') {
    const { client, results } = payload || {};
    const out = clients.get(client);
    if (!out) return; // bv. previews van het schema-overlay
    clearWatchdog(client);
    out.innerHTML = renderResults(results);
    refreshCatalog(); // nieuwe tabellen (CREATE TABLE) meteen in de autocomplete
  }
}

// --- Run-doel: selectie, anders het statement onder de cursor (#34) ---
// Zoals in echte SQL-tools: Run voert de selectie uit als die er is, anders
// het statement waarin de cursor staat (grenzen: sql-statements.js). "Run
// alles" voert de hele cel uit — DDL-scripts (CREATE TABLE …; INSERT …;)
// hebben dat nodig. Het statement dat Run zou uitvoeren krijgt een subtiele
// markering per regel (.sql-run-line, gestyled in sql-editors.css), maar
// alleen als de cel meer dan één statement bevat: bij één statement loopt
// sowieso alles en is de markering ruis. Bij een selectie is de selectie
// zelf de markering.
const runLine = Decoration.line({ class: 'sql-run-line' });

function runTargetState(state, statements) {
  const sel = state.selection.main;
  const target = sel.empty ? statementAt(statements, sel.head) : null;
  const marks = [];
  if (target && statements.length > 1) {
    const last = state.doc.lineAt(target.to).number;
    for (let line = state.doc.lineAt(target.from); ; line = state.doc.line(line.number + 1)) {
      marks.push(runLine.range(line.from));
      if (line.number >= last) break;
    }
  }
  return { statements, target, decorations: Decoration.set(marks) };
}

// Statementgrenzen en markering volgen elke wijziging van tekst of cursor.
const runTargetField = StateField.define({
  create: state => runTargetState(state, splitStatements(state.doc.toString())),
  update(value, tr) {
    if (!tr.docChanged && !tr.selection) return value;
    const statements = tr.docChanged ? splitStatements(tr.state.doc.toString()) : value.statements;
    return runTargetState(tr.state, statements);
  },
  provide: f => EditorView.decorations.from(f, v => v.decorations),
});

// De SQL die Run uitvoert: de selectie, anders het statement onder de cursor;
// bevat de cel geen statement (leeg, alleen commentaar), dan de hele cel.
function runTargetSql(state) {
  const sel = state.selection.main;
  if (!sel.empty) return state.sliceDoc(sel.from, sel.to);
  const { target } = state.field(runTargetField);
  return target ? state.sliceDoc(target.from, target.to) : state.doc.toString();
}

// --- Acties per cel ---
function runQuery(rec, sqlText) {
  if (!worker || !dbReady) {
    rec.outputEl.innerHTML =
      '<div class="sql-live-note">De database wordt nog geladen — probeer zo meteen opnieuw.</div>';
    return;
  }
  rec.outputEl.innerHTML = '<div class="sql-live-note">Bezig…</div>';
  armWatchdog(rec.client, rec.outputEl);
  worker.postMessage({
    id: SHARED_ID,
    type: 'exec',
    payload: { sql: sqlText, limit: RUN_LIMIT, client: rec.client },
  });
}

function resetDatabase() {
  if (!worker) return;
  dbReady = false;
  clients.forEach(el => { el.textContent = OUTPUT_PLACEHOLDER; });
  discardSavedDb(); // terug naar de seed: ook de bewaarde kopie weg (#41)
  worker.postMessage({ id: SHARED_ID, type: 'reset', payload: dbPayload({ withSaved: false }) });
}

// --- Bewaarde databank (#41) ---
// De worker stuurt na elke Run die de databank wijzigde een snapshot (het
// volledige SQLite-bestand). Die gaat naar IndexedDB (sql-db-store.js) en
// blijft in het geheugen als herstelpunt voor de watchdog. Het label "eigen
// databank" in elke celtoolbar verschijnt zodra de databank eigen wijzigingen
// bevat — ook als de opslag ze niet kon bewaren; dat melden we dan één keer
// in de balk "Mijn werk", met de download als uitweg.
function setOwnDb(flag) {
  ownDbBadges.forEach(el => { el.hidden = !flag; });
}

async function persistSnapshot(bytes) {
  if (!(bytes instanceof Uint8Array)) return;
  const gen = storeGen;
  savedBuf = bytes;
  setOwnDb(true);
  const ok = await writeSavedDb(SHARED_ID, bytes);
  if (gen !== storeGen) return; // intussen gereset: deze snapshot telt niet meer
  dbSaved = ok;
  if (!ok && !storageWarned) {
    storageWarned = true;
    reportWork(
      'Je databank kon in deze browser niet bewaard worden (opslag geblokkeerd of vol): ' +
      'na een herlaad staan de startgegevens er weer. Download je databank om ze niet te verliezen.',
    );
  }
}

function discardSavedDb() {
  storeGen++;
  savedBuf = null;
  setOwnDb(false);
  deleteSavedDb(SHARED_ID).then(() => { dbSaved = false; });
}

async function openSchema() {
  const mod = await import(`${STATIC_BASE}/sql-overlay.js`);
  mod.openSchemaOverlay({ worker, sharedId: SHARED_ID });
}

// --- Mijn werk: download (#30) en upload (#35) van het eigen werk ---
// Eén balk per pagina, onder de laatste interactieve cel. "Download mijn
// queries" exporteert de actuele inhoud van alle cellen als één .sql-bestand
// met een commentaarkop per cel ("-- cel 3"; formaat in sql-queries-file.js).
// Handig indienformaat, en de aangeraden uitweg voor wie op meerdere
// toestellen werkt: de opslag uit #14 is per browser/toestel. De export leest
// rechtstreeks uit de editors (niet uit localStorage), dus hij werkt ook als
// opslag geblokkeerd is.
function exportFileName() {
  const page = pageName(location.pathname).replace(/[^\w.-]+/g, '_');
  return `queries-${page || 'pagina'}.sql`;
}

function buildSqlExport() {
  return buildQueriesFile(
    location.pathname,
    editorsApi.map(ed => ({ index: ed.index, sql: ed.getValue() })),
  );
}

function saveBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadQueries() {
  saveBlob(new Blob([buildSqlExport()], { type: 'application/sql' }), exportFileName());
}

// "Download mijn databank" (#41): het actuele SQLite-bestand uit de worker
// (db.export()), als .db-bestand — te openen in elk SQLite-programma en in te
// dienen via Teams. De export leest de live databank, niet de bewaarde kopie,
// dus hij werkt ook als IndexedDB geblokkeerd is.
function databaseFileName() {
  const page = pageName(location.pathname).replace(/[^\w.-]+/g, '_');
  return `databank-${page || 'pagina'}.db`;
}

function requestExport() {
  return new Promise((resolve, reject) => {
    const w = worker;
    const client = 'export';
    const timer = setTimeout(() => { cleanup(); reject(new Error('de database antwoordt niet')); }, RUN_TIMEOUT_MS);
    const onMessage = (ev) => {
      const { id, type, payload } = ev.data || {};
      if (id !== SHARED_ID || payload?.client !== client) return;
      if (type === 'export') { cleanup(); resolve(payload.bytes); }
      else if (type === 'error') { cleanup(); reject(new Error(payload.message || 'onbekende fout')); }
    };
    const cleanup = () => { clearTimeout(timer); w.removeEventListener('message', onMessage); };
    w.addEventListener('message', onMessage);
    w.postMessage({ id: SHARED_ID, type: 'export', payload: { client } });
  });
}

async function downloadDatabase(report) {
  if (!worker || !dbReady) {
    report('De database wordt nog geladen — probeer zo meteen opnieuw.');
    return;
  }
  try {
    const bytes = await requestExport();
    saveBlob(new Blob([bytes], { type: 'application/vnd.sqlite3' }), databaseFileName());
  } catch (e) {
    report(`Databank downloaden mislukt: ${e?.message || e}`);
  }
}

// "Upload mijn queries" is de tegenhanger: het leest zo'n bestand en zet de
// inhoud per cel terug via setValue(), waarna de gewone opslag (#14) hem
// meteen bewaart — of niet, als opslag geblokkeerd is; het werk staat dan toch
// live in de editors. Cellen met eigen werk (≠ startcode) worden pas
// overschreven na bevestiging, net als een bestand van een andere pagina.
// Komt het bestand van een oudere versie van de pagina (ander celaantal), dan
// wordt teruggezet wat matcht en gemeld wat niet kon.
function listCells(indexes) {
  const nums = indexes.map(i => i + 1);
  if (nums.length === 1) return `cel ${nums[0]}`;
  return `cellen ${nums.slice(0, -1).join(', ')} en ${nums[nums.length - 1]}`;
}

function planImport(parsed) {
  const restore = [];   // { editor, sql } — cellen die op deze pagina bestaan
  const missing = [];   // indexen uit het bestand zonder cel op deze pagina
  const overwrite = []; // indexen met eigen werk dat door het bestand verandert
  for (const { index, sql } of parsed.cells) {
    const editor = editorsApi[index];
    if (!editor) { missing.push(index); continue; }
    const current = editor.getValue();
    if (current !== sql && current !== editor.initialValue) overwrite.push(index);
    restore.push({ editor, sql });
  }
  return { restore, missing, overwrite };
}

function importQueries(text, report) {
  const parsed = parseQueriesFile(text);
  const { restore, missing, overwrite } = planImport(parsed);
  if (!restore.length && !missing.length) {
    report('Geen cellen gevonden in dit bestand. Kies een bestand dat je met "Download mijn queries" bewaarde.');
    return;
  }

  const warnings = [];
  if (parsed.page && pageName(parsed.page) !== pageName(location.pathname)) {
    warnings.push(`Dit bestand komt van een andere pagina (${pageName(parsed.page)}).`);
  }
  if (overwrite.length) {
    const which = listCells(overwrite);
    warnings.push(
      `${which[0].toUpperCase()}${which.slice(1)} van deze pagina ` +
      `${overwrite.length === 1 ? 'bevat' : 'bevatten'} eigen werk dat door het bestand overschreven wordt.`,
    );
  }
  if (warnings.length && !window.confirm(`${warnings.join('\n')}\n\nToch terugzetten?`)) {
    report('Upload geannuleerd — er is niets gewijzigd.');
    return;
  }

  restore.forEach(({ editor, sql }) => {
    if (editor.getValue() !== sql) editor.setValue(sql);
    cells[editor.index].flush?.(); // meteen bewaren (#14), niet pas na de debounce
  });

  const notes = [];
  if (restore.length) notes.push(`Teruggezet: ${listCells(restore.map(r => r.editor.index))}.`);
  if (missing.length) {
    const count = editorsApi.length;
    notes.push(
      `Niet teruggezet: ${listCells(missing)} — deze pagina heeft ${count} ${count === 1 ? 'cel' : 'cellen'}; ` +
      'het bestand komt wellicht van een oudere versie van de pagina.',
    );
  }
  report(notes.join(' '));
}

function addMyWorkBar(lastCell) {
  const bar = document.createElement('div');
  bar.className = 'sql-download-bar';
  bar.innerHTML = `
    <span class="title">Mijn werk</span>
    <span class="sql-live-note">Je queries en je databank worden per browser bewaard. Download ze als bestand om ze in te dienen of mee te nemen naar een ander toestel; met Upload zet je je queries hier weer terug.</span>
    <span class="actions">
      <button class="sql-live-btn download" title="Bewaart de inhoud van alle cellen op deze pagina als één .sql-bestand">Download mijn queries</button>
      <button class="sql-live-btn upload" title="Zet de cellen van deze pagina terug uit een bestand van &quot;Download mijn queries&quot;">Upload mijn queries</button>
      <button class="sql-live-btn download-db" title="Bewaart de databank van deze pagina, met al je wijzigingen, als .db-bestand (SQLite)">Download mijn databank</button>
      <input class="sql-upload-input" type="file" accept=".sql,.txt,text/plain,application/sql" hidden>
    </span>
    <span class="sql-live-note sql-upload-status" role="status" aria-live="polite" hidden></span>
  `;
  const input = bar.querySelector('.sql-upload-input');
  const status = bar.querySelector('.sql-upload-status');
  const report = (message) => { status.textContent = message; status.hidden = false; };
  reportWork = report;

  bar.querySelector('.download').addEventListener('click', downloadQueries);
  bar.querySelector('.download-db').addEventListener('click', () => downloadDatabase(report));
  bar.querySelector('.upload').addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    const file = input.files?.[0];
    input.value = ''; // hetzelfde bestand mag meteen opnieuw gekozen worden
    if (!file) return;
    try {
      importQueries(await file.text(), report);
    } catch (e) {
      report(`Bestand lezen mislukt: ${e?.message || e}`);
    }
  });
  lastCell.after(bar);
}

// --- Editors opzetten ---
function editorExtensions(langCompartment, run, runAll, onDocChange) {
  return [
    lineNumbers(),
    highlightActiveLineGutter(),
    history(),
    drawSelection(),
    indentOnInput(),
    bracketMatching(),
    closeBrackets(),
    autocompletion(),
    highlightActiveLine(),
    runTargetField,
    plinkTheme,
    syntaxHighlighting(plinkHighlight),
    keymap.of([
      { key: 'Mod-Enter', run: () => { run(); return true; } },
      { key: 'Mod-Shift-Enter', run: () => { runAll(); return true; } },
      ...closeBracketsKeymap,
      ...defaultKeymap,
      ...historyKeymap,
      ...completionKeymap,
      indentWithTab,
    ]),
    langCompartment.of(makeSqlLang(currentSchema)),
    EditorView.updateListener.of(u => { if (u.docChanged) onDocChange(); }),
  ];
}

function initEditors(blocks) {
  blocks.forEach(({ cell, initialSql }, index) => {
    const ui = wrapCell(cell);
    const initialDoc = initialSql || 'SELECT 1;';
    const key = storageKey(index);
    const saved = readSaved(key);
    const doc = saved ?? initialDoc; // bewaard leerlingwerk wint van de startcode (#14)
    const client = 'cell-' + index;
    clients.set(client, ui.outputEl);

    const langCompartment = new Compartment();
    const changeListeners = [];
    const rec = { client, outputEl: ui.outputEl, langCompartment, view: null, flush: null };

    // Opslag (#14): debounced bij typen, meteen bij Run en bij het verlaten
    // van de pagina. Gelijk aan de startcode = niets te bewaren (sleutel weg),
    // en dan verdwijnt ook de indicator "eigen versie".
    let saveTimer = null;
    const syncStorage = () => {
      if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
      const value = view.state.doc.toString();
      writeSaved(key, value, initialDoc);
      ui.ownEl.hidden = value === initialDoc;
    };
    const scheduleSync = () => {
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(syncStorage, SAVE_DEBOUNCE_MS);
    };
    // Opslag eerst wegschrijven (#14), ook bij een gedeeltelijke Run (#34).
    const run = () => { syncStorage(); runQuery(rec, runTargetSql(view.state)); };
    const runAll = () => { syncStorage(); runQuery(rec, view.state.doc.toString()); };

    const view = new EditorView({
      state: EditorState.create({
        doc,
        extensions: editorExtensions(
          langCompartment,
          run,
          runAll,
          () => {
            scheduleSync();
            const value = view.state.doc.toString();
            changeListeners.forEach(cb => { try { cb(value); } catch { /* listener-fout negeren */ } });
          },
        ),
      }),
      parent: ui.editorEl,
    });
    rec.view = view;
    rec.flush = syncStorage;
    cells.push(rec);
    ui.ownEl.hidden = doc === initialDoc;
    ownDbBadges.push(ui.ownDbEl);

    ui.runBtn.addEventListener('click', run);
    ui.runAllBtn.addEventListener('click', runAll);
    ui.startBtn.addEventListener('click', () => {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: initialDoc },
      });
      syncStorage(); // verwijdert de bewaarde versie en verbergt "eigen versie"
      view.focus();
    });
    ui.resetBtn.addEventListener('click', resetDatabase);
    ui.schemaBtn.addEventListener('click', openSchema);

    // Publieke API per cel (#14) — dezelfde sleutel als in localStorage.
    editorsApi.push({
      key,
      index,
      initialValue: initialDoc,
      getValue: () => view.state.doc.toString(),
      setValue: (text) => view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: String(text) },
      }),
      onChange: (cb) => { changeListeners.push(cb); },
    });
  });

  // Balk "Mijn werk" (download #30, upload #35) onder de laatste interactieve cel.
  addMyWorkBar(blocks[blocks.length - 1].cell);

  // Nog niet weggeschreven wijzigingen (debounce) alsnog bewaren bij het
  // verlaten of verbergen van de pagina.
  window.addEventListener('pagehide', () => {
    cells.forEach(c => { try { c.flush?.(); } catch { /* opslag mag nooit blokkeren */ } });
  });
}

// --- Boot ---
onReady(async () => {
  const seedUrlRaw = pickPageSeedUrl(); // verwijdert de sql-db-cel van de pagina
  const blocks = findSqlBlocks();
  if (!blocks.length) return; // geen interactieve cellen op deze pagina

  try {
    const seedUrl = resolveStatic(seedUrlRaw); // bv. "/_static/db/webshop.db"
    const fetchSeed = async () => {
      const res = await fetch(seedUrl);
      if (!res.ok) throw new Error(`database laden mislukt: ${res.status} (${seedUrl})`);
      return res.arrayBuffer();
    };
    // Seed en bewaarde databank (#41) tegelijk ophalen; readSavedDb gooit
    // nooit (geblokkeerde opslag → null → de seed).
    [seedBuf, savedBuf] = await Promise.all([
      seedUrl ? fetchSeed() : null,
      readSavedDb(SHARED_ID),
    ]);
    dbSaved = savedBuf !== null;

    initEditors(blocks);
    window.sqlLive = {
      editors: editorsApi,
      staticBase: STATIC_BASE,
      get dbReady() { return dbReady; }, // o.a. voor de e2e-tests (tests/test_sql_editor.py)
      get dbSaved() { return dbSaved; }, // kopie van de databank staat in IndexedDB (#41)
    };
    document.dispatchEvent(new CustomEvent('sql-live:ready', { detail: window.sqlLive }));

    await startWorker();
  } catch (e) {
    console.error('SQL-editor init mislukt:', e);
  }
});
