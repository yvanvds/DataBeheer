// _static/sql-worker.js  (classic worker, gestart door sql-editors.js)
//
// Draait sql.js (SQLite in WebAssembly) buiten de UI-thread. Eén sessie per
// pagina (zelfde id voor alle editors), zodat CREATE/INSERT in de ene cel
// zichtbaar is in de andere. Protocol:
//   → {id, type:'init'|'reset', payload:{seedBuf?}}   ← {id, type:'ready'}
//   → {id, type:'exec', payload:{sql, limit?, client}} ← {id, type:'result',
//        payload:{client, results:[{columns, rows, truncated}]}}
//   → {id, type:'schema'}   ← {id, type:'schema', payload:<db.exec-output>}
//   → {id, type:'catalog'}  ← {id, type:'catalog', payload:{schema:{tabel:[kolommen]}}}
// Fouten: {id, type:'error', payload:{client?, message}}.
const WORKER_BASE = self.location.pathname.replace(/\/[^\/]*$/, ''); // bv. /DataBeheer/_static
importScripts(WORKER_BASE + '/sqljs/sql-wasm.js');

let SQL; // sql.js module factory
const sessions = new Map(); // id -> { db }

async function ensureSQL() {
  if (!SQL) {
    SQL = await initSqlJs({
      locateFile: f => WORKER_BASE + '/sqljs/' + f
    });
  }
}

function quoteIdent(name) {
  return '"' + String(name).replaceAll('"', '""') + '"';
}

function openDatabase(id, seedBuf) {
  const old = sessions.get(id);
  if (old?.db) { try { old.db.close(); } catch {} }
  const db = seedBuf
    ? new SQL.Database(new Uint8Array(seedBuf))
    : new SQL.Database();
  sessions.set(id, { db });
  return db;
}

function requireDb(id) {
  const s = sessions.get(id);
  if (!s || !s.db) throw new Error('Geen database voor deze sessie.');
  return s.db;
}

// Volledige catalogus {tabel: [kolommen]} voor schema-aware autocomplete.
function buildCatalog(db) {
  const schema = {};
  const master = db.exec(
    "SELECT name FROM sqlite_master WHERE type IN ('table','view') " +
    "AND name NOT LIKE 'sqlite_%' ORDER BY name;"
  );
  const names = master.length ? master[0].values.map(r => r[0]) : [];
  for (const name of names) {
    try {
      const info = db.exec(`PRAGMA table_info(${quoteIdent(name)});`);
      schema[name] = info.length ? info[0].values.map(r => r[1]) : [];
    } catch {
      schema[name] = [];
    }
  }
  return schema;
}

self.onmessage = async (ev) => {
  const { id, type, payload } = ev.data || {};
  const client = payload?.client;

  try {
    if (type === 'init' || type === 'reset') {
      await ensureSQL();
      openDatabase(id, payload?.seedBuf);
      self.postMessage({ id, type: 'ready' });
    }

    else if (type === 'exec') {
      const db = requireDb(id);
      const sql = payload?.sql || '';
      const limit = payload?.limit ?? 500;

      let raw;
      try {
        raw = db.exec(sql);
      } catch (e) {
        self.postMessage({
          id, type: 'error',
          payload: { client, message: String(e?.message || e) }
        });
        return;
      }

      // Alle statements met rijen (niet enkel het eerste), elk apart afgekapt.
      const results = raw.map(r => {
        const truncated = r.values.length > limit;
        return {
          columns: r.columns,
          rows: truncated ? r.values.slice(0, limit) : r.values,
          truncated
        };
      });
      self.postMessage({ id, type: 'result', payload: { client, results } });
    }

    else if (type === 'schema') {
      const db = requireDb(id);
      const tables = db.exec(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name;"
      );
      self.postMessage({ id, type: 'schema', payload: tables });
    }

    else if (type === 'catalog') {
      const db = requireDb(id);
      self.postMessage({ id, type: 'catalog', payload: { schema: buildCatalog(db) } });
    }

  } catch (e) {
    self.postMessage({
      id, type: 'error',
      payload: { client, message: String(e?.message || e) }
    });
  }
};
