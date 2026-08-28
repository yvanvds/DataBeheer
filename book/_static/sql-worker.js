// _static/sql-worker.js  (classic worker, gestart door sql-editors.js)
//
// Draait sql.js (SQLite in WebAssembly) buiten de UI-thread. Eén sessie per
// pagina (zelfde id voor alle editors), zodat CREATE/INSERT in de ene cel
// zichtbaar is in de andere. Protocol:
//   → {id, type:'init'|'reset', payload:{seedBuf?, savedBuf?}}
//        ← {id, type:'ready', payload:{restored, savedRejected}}
//   → {id, type:'exec', payload:{sql, limit?, client}} ← {id, type:'result',
//        payload:{client, results:[{columns, rows, truncated}]}}
//        en, als de databank door de exec veranderde (#41):
//        ← {id, type:'snapshot', payload:{bytes:Uint8Array}}
//   → {id, type:'export', payload:{client}} ← {id, type:'export',
//        payload:{client, bytes:Uint8Array}}
//   → {id, type:'schema'}   ← {id, type:'schema', payload:<db.exec-output>}
//   → {id, type:'catalog'}  ← {id, type:'catalog', payload:{schema:{tabel:[kolommen]}}}
// Fouten: {id, type:'error', payload:{client?, message}}.
//
// Bewaren van de paginadatabank (#41): 'init' krijgt naast de seed ook de
// laatst bewaarde kopie (savedBuf, uit IndexedDB op de UI-thread) en opent
// die als ze bruikbaar is; `restored` in 'ready' zegt welke van de twee het
// werd. Na elke exec die de databank wijzigde, stuurt de worker een
// 'snapshot' met het volledige databasebestand (db.export()). De
// wijzigingsdetectie leest het schema-cookie (PRAGMA schema_version,
// verandert bij elke DDL) en total_changes() (rijen gewijzigd door
// INSERT/UPDATE/DELETE op deze verbinding): bij louter SELECT-werk — het
// hele SQL-deel — wordt er dus nooit geëxporteerd, en dus ook nooit een
// verouderde kopie van de seed bewaard. Ook na een fout wordt gecontroleerd:
// in een script kunnen de statements vóór de fout al uitgevoerd zijn.
//
// Let op: db.export() sluit in sql.js de verbinding en opent ze opnieuw, dus
// verbindingsinstellingen gaan daarbij verloren. PRAGMA foreign_keys wordt
// na een export teruggezet, omdat de ERD-lessen erop steunen. Tijdelijke
// tabellen en een open transactie over cellen heen overleven een export niet.
const WORKER_BASE = self.location.pathname.replace(/\/[^\/]*$/, ''); // bv. /DataBeheer/_static
importScripts(WORKER_BASE + '/sqljs/sql-wasm.js');

let SQL; // sql.js module factory
const sessions = new Map(); // id -> { db, stamp }

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

function scalar(db, sql) {
  const res = db.exec(sql);
  return res.length ? res[0].values[0][0] : null;
}

// Vingerafdruk van de databankinhoud: schema-cookie + rijwijzigingen op deze
// verbinding. Verandert hij niet, dan is er niets te bewaren.
function changeStamp(db) {
  return scalar(db, 'PRAGMA schema_version;') + ':' + scalar(db, 'SELECT total_changes();');
}

// Het databasebestand als bytes. sql.js sluit en heropent daarbij de
// verbinding: foreign_keys terugzetten, en de stamp opnieuw nemen
// (total_changes() begint op de nieuwe verbinding weer bij 0).
function exportImage(session) {
  const foreignKeys = scalar(session.db, 'PRAGMA foreign_keys;');
  const bytes = session.db.export();
  if (foreignKeys) session.db.exec('PRAGMA foreign_keys = ON;');
  session.stamp = changeStamp(session.db);
  return bytes;
}

function postBytes(message, bytes) {
  try {
    self.postMessage(message, [bytes.buffer]); // zonder kopie
  } catch {
    self.postMessage(message); // buffer niet overdraagbaar — dan maar gekopieerd
  }
}

function openDatabase(id, payload) {
  const old = sessions.get(id);
  if (old?.db) { try { old.db.close(); } catch {} }

  let db = null;
  let restored = false;
  let savedRejected = false;
  if (payload?.savedBuf) {
    try {
      db = new SQL.Database(new Uint8Array(payload.savedBuf));
      db.exec('SELECT count(*) FROM sqlite_master;'); // onbruikbaar bestand? dan gooit dit
      restored = true;
    } catch {
      try { db?.close(); } catch {}
      db = null;
      savedRejected = true; // bv. een afgebroken opslag — terug naar de seed
    }
  }
  if (!db) {
    db = payload?.seedBuf
      ? new SQL.Database(new Uint8Array(payload.seedBuf))
      : new SQL.Database(); // pagina zonder sql-db-cel: lege startdatabank
  }
  sessions.set(id, { db, stamp: changeStamp(db) });
  return { restored, savedRejected };
}

function requireSession(id) {
  const s = sessions.get(id);
  if (!s || !s.db) throw new Error('Geen database voor deze sessie.');
  return s;
}

function snapshotIfChanged(id, session) {
  let stamp;
  try { stamp = changeStamp(session.db); } catch { return; }
  if (stamp === session.stamp) return;
  const bytes = exportImage(session);
  postBytes({ id, type: 'snapshot', payload: { bytes } }, bytes);
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
      const { restored, savedRejected } = openDatabase(id, payload);
      self.postMessage({ id, type: 'ready', payload: { restored, savedRejected } });
    }

    else if (type === 'exec') {
      const session = requireSession(id);
      const db = session.db;
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
        snapshotIfChanged(id, session); // statements vóór de fout kunnen al gelopen zijn
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
      snapshotIfChanged(id, session);
    }

    else if (type === 'export') {
      const bytes = exportImage(requireSession(id));
      postBytes({ id, type: 'export', payload: { client, bytes } }, bytes);
    }

    else if (type === 'schema') {
      const db = requireSession(id).db;
      const tables = db.exec(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name;"
      );
      self.postMessage({ id, type: 'schema', payload: tables });
    }

    else if (type === 'catalog') {
      const db = requireSession(id).db;
      self.postMessage({ id, type: 'catalog', payload: { schema: buildCatalog(db) } });
    }

  } catch (e) {
    self.postMessage({
      id, type: 'error',
      payload: { client, message: String(e?.message || e) }
    });
  }
};
