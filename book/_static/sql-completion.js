

// _static/sql-completion.js
// Centralized completion for Monaco + SQLite using node-sql-parser and live schema via worker.

/* Public API ---------------------------------------------------------------
   initSqlCompletion({ monaco, worker, sharedId, staticBase, getEditors })
   - monaco: the monaco global
   - worker: your sql-worker instance (already created in sql-editors.js)
   - sharedId: the shared message id your worker uses on this page
   - staticBase: base path for static assets (e.g., `${window.BASE_URL || ''}/_static`)
   - getEditors: () => Array<monaco.editor.IStandaloneCodeEditor>  (so we can re-scan aliases per-editor)

   Usage from sql-editors.js (after editor is created):mysql
     import { initSqlCompletion } from '/_static/sql-completion.js';
     initSqlCompletion({ monaco, worker, sharedId: SHARED_ID, staticBase: STATIC_BASE, getEditors: () => [editor] });
---------------------------------------------------------------------------*/
export async function initSqlCompletion({ monaco, worker, sharedId, getEditors }) {
    // Use either window.require or window.requirejs
    const r = window.requirejs || window.require;

    r.config({
        paths: {
            // drop the .js extension in paths
            nodeSqlParser: 'https://unpkg.com/node-sql-parser/umd/sqlite.umd'
        },
        shim: {
            nodeSqlParser: { exports: 'NodeSQLParser' }, // UMD exposes window.NodeSQLParser
            sqljs: { exports: 'initSqlJs' }
        }
    });

    let parser = null;
    // Load and use
    r(['nodeSqlParser'], function (NodeSQLParser) {
        parser = new NodeSQLParser.Parser();
    });

    // 2) build schema once
    const Catalog = await ensureSchemaCatalog(worker, sharedId);

    // Register once (idempotent)
    if (initSqlCompletion._registered) return;
    initSqlCompletion._registered = true;

    monaco.languages.registerCompletionItemProvider('sql', {
        triggerCharacters: ['.'],   // ensure immediate popup after dot
        provideCompletionItems: (model, position) => {
            const fullText = model.getValue();

            // Build context once (gets aliasMap, zone, etc.)
            const { stmtText, stmtOffset } = sliceStatementAtCursor(fullText, position);
            const parsed = tryAstify(parser, stmtText);
            const ctx = analyzeContext({
                model, position, stmtText, stmtOffset, fullText, parsed, catalog: Catalog
            });

            // -------- ZONE-AGNOSTIC DOT HANDLER (early exit) --------
            const beforeText = model.getValueInRange({
                startLineNumber: 1, startColumn: 1,
                endLineNumber: position.lineNumber, endColumn: position.column
            });

            // optional: support db.table.
            const twoPart = /([A-Za-z_]\w*)\.([A-Za-z_]\w*)\.\s*$/.exec(beforeText);
            let tableName = null;
            if (twoPart) {
                tableName = twoPart[2];
            } else {
                const dot1 = /(?:"([^"]+)"|`([^`]+)`|\[([^\]]+)\]|([A-Za-z_]\w*))\.\s*$/.exec(beforeText);
                if (dot1) {
                    const ident = dot1[1] || dot1[2] || dot1[3] || dot1[4];
                    tableName = ctx.aliasMap.get(ident) || ident;     // alias → table or raw table
                }
            }

            if (tableName) {
                const cols = Catalog.columnsByTable.get(tableName) || [];
                const word = model.getWordUntilPosition(position);   // the piece after the dot
                const range = new monaco.Range(
                    position.lineNumber,
                    position.column - word.word.length,
                    position.lineNumber,
                    position.column
                );
                const suggestions = cols.map(c => ({
                    label: c.name,
                    kind: monaco.languages.CompletionItemKind.Field,
                    insertText: c.name,
                    detail: `${tableName}.${c.name}`,
                    sortText: '0',
                    range
                }));
                return { suggestions };
            }
            // --------------------------------------------------------
            // Build suggestions from context
            const suggestions = buildSuggestions({ monaco, ctx, catalog: Catalog });

            // Attach a minimal range at the cursor (Monaco will replace prefix as needed)
            const word = model.getWordUntilPosition(position);
            const range = new monaco.Range(
                position.lineNumber,
                word.startColumn,    // replace from start of the current word
                position.lineNumber,
                position.column      // …to the cursor
            );
            return { suggestions: suggestions.map(s => ({ ...s, range })) };

        }
    });

    // Optional: when schema may change at runtime (DDL in exercises), expose a refresh:
    initSqlCompletion.refreshCatalog = () => ensureSchemaCatalog(worker, sharedId, true);
}


/* -------------------------------------------------------------------------
   2) Live schema catalog: tables, views, columnsByTable (via PRAGMA)
---------------------------------------------------------------------------*/
const SchemaCache = {
    ready: false,
    tables: [],
    views: [],
    columnsByTable: new Map(), // table -> [{name,type,notnull,pk}]
};

async function ensureSchemaCatalog(worker, sharedId, force = false) {
    if (SchemaCache.ready && !force) return SchemaCache;

    // Step A: list tables+views (reusing your worker "schema" message)
    const { tables, views } = await new Promise((resolve, reject) => {
        const onMsg = (ev) => {
            const { id, type, payload } = ev.data || {};
            if (id !== sharedId || type !== 'schema') return;
            worker.removeEventListener('message', onMsg);
            try {
                const res = Array.isArray(payload) ? payload[0] : null;
                const nameIdx = res?.columns.indexOf('name');
                const typeIdx = res?.columns.indexOf('type');
                const t = [], v = [];
                (res?.values || []).forEach(row => {
                    const nm = row[nameIdx];
                    const tp = String(row[typeIdx] || '').toLowerCase();
                    if (tp === 'table') t.push(nm);
                    else if (tp === 'view') v.push(nm);
                });
                resolve({ tables: t, views: v });
            } catch (e) { reject(e); }
        };
        worker.addEventListener('message', onMsg);
        worker.postMessage({ id: sharedId, type: 'schema' });
    });

    SchemaCache.tables = tables;
    SchemaCache.views = views;
    SchemaCache.columnsByTable.clear();

    // Step B: PRAGMA table_info for each object
    const fetchCols = (obj) => new Promise((resolve) => {
        const client = `cat-info-${obj}-${Math.random().toString(36).slice(2)}`;
        const onMsg = (ev) => {
            const { id, type, payload } = ev.data || {};
            if (id !== sharedId || type !== 'result' || payload?.client !== client) return;
            worker.removeEventListener('message', onMsg);
            const idx = {};
            (payload.columns || []).forEach((c, i) => (idx[c] = i));
            const cols = (payload.rows || payload.values || []).map(r => ({
                name: r[idx.name], type: r[idx.type], notnull: !!r[idx.notnull], pk: !!r[idx.pk]
            }));
            resolve({ obj, cols });
        };
        worker.addEventListener('message', onMsg);
        worker.postMessage({
            id: sharedId,
            type: 'exec',
            payload: { sql: `PRAGMA table_info(${obj});`, client, limit: 1000 }
        });
    });

    const allObjs = [...tables, ...views];
    const batches = await Promise.all(allObjs.map(fetchCols));
    batches.forEach(({ obj, cols }) => SchemaCache.columnsByTable.set(obj, cols));

    SchemaCache.ready = true;
    return SchemaCache;
}

/* -------------------------------------------------------------------------
   3) Statement slicing around the cursor (robust for teaching use)
---------------------------------------------------------------------------*/
function sliceStatementAtCursor(fullText, position) {
    const lines = fullText.split('\n');
    const cursorIdx = toIndex(lines, position);
    // naive split on semicolons; pick the segment containing the cursor
    let start = 0, end = fullText.length;
    {
        const before = fullText.lastIndexOf(';', cursorIdx - 1);
        const after = fullText.indexOf(';', cursorIdx);
        start = before >= 0 ? before + 1 : 0;
        end = after >= 0 ? after : fullText.length;
    }
    const stmtText = fullText.slice(start, end);
    return { stmtText, stmtOffset: start };
}

function toIndex(lines, pos) {
    let idx = 0;
    for (let i = 0; i < pos.lineNumber - 1; i++) idx += lines[i].length + 1;
    return idx + (pos.column - 1);
}

/* -------------------------------------------------------------------------
   4) Parser wrapper that tolerates partial SQL
---------------------------------------------------------------------------*/
function tryAstify(Parser, sql) {
    const s = (sql || '').trim();
    if (!s) return null;

    try {
        // node-sql-parser: use sqlite dialect; returns AST or array.
        // We prefer astify (if available) because it keeps structure uniform.
        const ast = (Parser.astify ? Parser.astify(s, { database: 'sqlite' }) : Parser.parse(s));
        return ast;
    } catch {
        // Make a few minimal patches to help partials parse; if it still fails, return null.
        try {
            const patched = patchPartialSql(s);
            if (!patched) return null;
            const ast = (Parser.astify ? Parser.astify(patched, { database: 'sqlite' }) : Parser.parse(patched));
            return ast;
        } catch {
            return null;
        }
    }
}

function patchPartialSql(s) {
    // Very light touch: if user is mid-SELECT without FROM, add dummy tail
    if (/^\s*select\b/i.test(s) && !/\bfrom\b/i.test(s)) return s + ' FROM _x_';
    // Mid-FROM without table: add placeholder
    if (/\bfrom\s*$/i.test(s)) return s + ' _x_';
    // Mid-JOIN without table
    if (/\bjoin\s*$/i.test(s)) return s + ' _x_ ON 1=1';
    return null;
}

/* -------------------------------------------------------------------------
   5) AST-driven context analysis
---------------------------------------------------------------------------*/
function analyzeContext({ model, position, stmtText, stmtOffset, fullText, parsed, catalog }) {
    const beforeText = model.getValueInRange({
        startLineNumber: 1, startColumn: 1,
        endLineNumber: position.lineNumber, endColumn: position.column
    });

    // Dot access detection: tableOrAlias.<cursor>
    const dotMatch = /([A-Za-z_][\w]*)\.\s*$/.exec(beforeText);
    const dotBase = dotMatch ? dotMatch[1] : null;

    // Token just before cursor (basic)
    const prevChar = beforeText.replace(/\s+$/, '').slice(-1);
    const afterComma = prevChar === ',';

    // Determine active SELECT block and its tables/aliases from AST.
    const aliasMap = new Map(); // alias -> table
    const usedTables = new Set(); // referenced table names

    // High-level clause “zone” for suggestions (coarse; AST-first)
    let zone = 'UNKNOWN'; // SELECT | FROM | JOIN | ON | WHERE | GROUP_BY | HAVING | ORDER_BY

    // If we have AST for this statement, collect FROM/JOIN, aliases, etc.
    if (parsed) {
        const selects = asArray(parsed).filter(n => n && (n.type === 'select' || n.type === 'statement' || n.SelectStatement));
        // Walk basic SELECT forms the parser emits for sqlite
        selects.forEach(sel => {
            collectTablesAndAliases(sel, aliasMap, usedTables);
        });

        // Estimate zone with a light textual pass but bounded to known clauses.
        zone = estimateZone(stmtText);
    } else {
        // No AST (very broken partial) → very conservative zone estimate
        zone = estimateZone(stmtText);
    }

    // If no used tables yet (e.g., typing early), fall back to all tables
    const candidateTables = usedTables.size ? [...usedTables] : catalog.tables;

    // --- NEW: detect "after comma in SELECT list" ---------------------------
    const absIdx = toIndex(fullText.split('\n'), position);    // you already have toIndex(...)
    const relIdx = Math.max(0, absIdx - stmtOffset);

    // restrict to the SELECT list segment (before FROM/GROUP/ORDER/…)
    const up = stmtText.toUpperCase();
    const selIdx = up.indexOf('SELECT');
    let listStart = selIdx >= 0 ? selIdx + 'SELECT'.length : 0;

    // end of SELECT list = first of FROM/GROUP BY/ORDER BY/HAVING/LIMIT or stmt end
    const clauseEnds = [
        up.indexOf(' FROM ', listStart),
        up.indexOf(' GROUP BY ', listStart),
        up.indexOf(' ORDER BY ', listStart),
        up.indexOf(' HAVING ', listStart),
        up.indexOf(' LIMIT ', listStart)
    ].filter(i => i >= 0);
    const listEnd = clauseEnds.length ? Math.min(...clauseEnds) : stmtText.length;

    const inSelectList = relIdx >= listStart && relIdx <= listEnd;
    const selectToCursor = inSelectList ? stmtText.slice(listStart, relIdx) : '';
    const afterCommaInSelect = inSelectList && /,\s*$/.test(selectToCursor);
    // -----------------------------------------------------------------------

    return {
        dotBase,
        afterComma,
        afterCommaInSelect,
        zone,
        aliasMap,
        candidateTables
    };
}

function asArray(ast) {
    if (!ast) return [];
    return Array.isArray(ast) ? ast : [ast];
}

function collectTablesAndAliases(sel, aliasMap, usedTables) {
    // node-sql-parser variants exist; we handle common shapes
    const from = sel.from || sel.FromClause || sel.fromClause;
    if (!from) return;

    const entries = Array.isArray(from) ? from : [from];

    entries.forEach(entry => {
        // table reference
        const table = entry.table || entry.Table || entry.name;
        if (typeof table === 'string') usedTables.add(table);
        if (table && table.name) usedTables.add(table.name);

        // alias
        const alias = entry.as || entry.alias || entry.tableAlias;
        const baseName = (typeof table === 'string') ? table : (table?.name);
        if (alias && baseName) aliasMap.set(String(alias), String(baseName));

        // JOINs
        if (entry.join) {
            const joins = Array.isArray(entry.join) ? entry.join : [entry.join];
            joins.forEach(j => {
                const jt = j.table || j.name || j.right;
                const jName = typeof jt === 'string' ? jt : (jt?.name);
                if (jName) usedTables.add(jName);
                const jAlias = j.as || j.alias;
                if (jAlias && jName) aliasMap.set(String(jAlias), String(jName));
            });
        }
    });
}

function estimateZone(stmtText) {
    const up = stmtText.toUpperCase();
    // Pick the last occurring clause keyword as the current "zone"
    const marks = [
        { k: ' SELECT ', z: 'SELECT' },
        { k: ' FROM ', z: 'FROM' },
        { k: ' JOIN ', z: 'JOIN' },
        { k: ' ON ', z: 'ON' },
        { k: ' WHERE ', z: 'WHERE' },
        { k: ' GROUP BY ', z: 'GROUP_BY' },
        { k: ' HAVING ', z: 'HAVING' },
        { k: ' ORDER BY ', z: 'ORDER_BY' },
    ];
    let best = { idx: -1, z: 'UNKNOWN' };
    marks.forEach(m => {
        const i = up.lastIndexOf(m.k);
        if (i > best.idx) best = { idx: i, z: m.z };
    });
    // Handle edge starts
    if (best.idx < 0 && /^\s*SELECT\b/i.test(stmtText)) return 'SELECT';
    return best.z;
}

/* -------------------------------------------------------------------------
   6) Build Monaco suggestions from context
---------------------------------------------------------------------------*/
function buildSuggestions({ monaco, ctx, catalog }) {
    const items = [];
    const { dotBase, afterCommaInSelect, zone, aliasMap, candidateTables } = ctx;

    const toKeyword = (label) => ({ label, kind: monaco.languages.CompletionItemKind.Keyword, insertText: label + ' ', sortText: '5' });
    const toFunc = (label) => ({ label, kind: monaco.languages.CompletionItemKind.Function, insertText: `${label}(`, sortText: '2' });
    const toTable = (label) => ({ label, kind: monaco.languages.CompletionItemKind.Field, insertText: label, detail: 'table/view', sortText: '1' });
    const toCol = (t, c) => ({ label: c.name, kind: monaco.languages.CompletionItemKind.Field, insertText: c.name, detail: `${t}.${c.name}`, sortText: '0' });

    // 1) tableOrAlias.<col> takes precedence
    if (dotBase) {
        const table = aliasMap.get(dotBase) || dotBase;
        const cols = (catalog.columnsByTable.get(table) || []).map(c => toCol(table, c));
        return cols;
    }

    console.log('buildSuggestions for zone:', zone);

    // 3) Clause-aware suggestions
    if (zone === 'SELECT') {
        if (afterCommaInSelect) {
            // You’re typing the next projection → show columns first
            candidateTables.forEach(t => (catalog.columnsByTable.get(t) || []).forEach(c => items.push(toCol(t, c))));
            // still useful: functions and snippets
            ["ABS", "AVG", "COUNT", "LOWER", "MAX", "MIN", "RANDOM", "ROUND", "SUM", "UPPER", "LENGTH", "COALESCE", "IFNULL", "DATE", "DATETIME", "STRFTIME"]
                .forEach(f => items.push(toFunc(f)));
            items.push({ label: '*', kind: monaco.languages.CompletionItemKind.Snippet, insertText: '*', sortText: '6' });
        } else {
            // You’ve likely finished a projection → suggest FROM prominently
            items.push(toKeyword('FROM'));
            // keep helpful extras too (columns and functions), but FROM sorts above via sortText
            candidateTables.forEach(t => (catalog.columnsByTable.get(t) || []).forEach(c => items.push(toCol(t, c))));
            ["ABS", "AVG", "COUNT", "LOWER", "MAX", "MIN", "RANDOM", "ROUND", "SUM", "UPPER", "LENGTH", "COALESCE", "IFNULL", "DATE", "DATETIME", "STRFTIME"]
                .forEach(f => items.push(toFunc(f)));
            items.push({ label: '*', kind: monaco.languages.CompletionItemKind.Snippet, insertText: '*', sortText: '6' });
        }
    }
    else if (zone === 'FROM' || zone === 'JOIN') {
        [...catalog.tables, ...catalog.views].forEach(t => items.push(toTable(t)));
        // “next” clauses from FROM/JOIN:
        if (zone === 'JOIN') {
            items.push(toKeyword('ON'));
        }
        items.push(toKeyword('WHERE'), toKeyword('JOIN'), toKeyword('GROUP BY'),
            toKeyword('ORDER BY'), toKeyword('LIMIT'));
    }
    else if (zone === 'WHERE' || zone === 'HAVING') {
        candidateTables.forEach(t => (catalog.columnsByTable.get(t) || []).forEach(c => items.push(toCol(t, c))));
        KW.operators.forEach(k => items.push(toKeyword(k)));
        if (zone === 'WHERE') items.push(toKeyword('GROUP BY'), toKeyword('ORDER BY'), toKeyword('LIMIT'));
    }
    else if (zone === 'GROUP_BY') {
        candidateTables.forEach(t => (catalog.columnsByTable.get(t) || []).forEach(c => items.push(toCol(t, c))));
    }
    else if (zone === 'ORDER_BY') {
        candidateTables.forEach(t => (catalog.columnsByTable.get(t) || []).forEach(c => items.push(toCol(t, c))));
        items.push(toKeyword('ASC'), toKeyword('DESC'));
        items.push(toKeyword('HAVING'), toKeyword('ORDER BY'), toKeyword('LIMIT'));
    } else {
        // Fallback: only high-signal starters
        ['SELECT', 'WITH'].forEach(k => items.push(toKeyword(k)));
    }

    // 4) Handy snippets (general)
    // items.push(
    //     {
    //         label: 'SELECT * FROM … WHERE …;',
    //         kind: monaco.languages.CompletionItemKind.Snippet,
    //         insertText: 'SELECT *\nFROM ${1:table}\nWHERE ${2:condition};',
    //         insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
    //         sortText: '9'
    //     },
    //     {
    //         label: 'SELECT agg FROM … GROUP BY …;',
    //         kind: monaco.languages.CompletionItemKind.Snippet,
    //         insertText: 'SELECT ${1:col}, ${2:COUNT(*)}\nFROM ${3:table}\nGROUP BY ${1:col};',
    //         insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
    //         sortText: '9'
    //     },
    //     {
    //         label: 'JOIN template',
    //         kind: monaco.languages.CompletionItemKind.Snippet,
    //         insertText: 'SELECT ${1:t1.*}, ${2:t2.*}\nFROM ${3:table1} ${4:t1}\nJOIN ${5:table2} ${6:t2} ON ${4:t1}.${7:id} = ${6:t2}.${8:ref_id};',
    //         insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
    //         sortText: '9'
    //     }
    // );

    return items;
}
