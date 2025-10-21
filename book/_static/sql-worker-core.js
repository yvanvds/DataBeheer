// _static/sql-worker-core.js  (core logic; assumes initSqlJs is already available)
let SQL; // sql.js module factory
const sessions = new Map(); // id -> { db }
const DEBUG = true;
const STATIC_BASE = self.__STATIC_BASE__ || '/_static';

function dbg(msg, data) {
  if (!DEBUG) return;
  self.postMessage({ id: null, type: 'debug', payload: { msg, data } });
}

async function ensureSQL() {
  if (!SQL) {
    dbg('ensureSQL: loading sql.js …', null);
    // initSqlJs is provided by sql-wasm.js, already importScript’ed by the bootstrap.
    SQL = await initSqlJs({
      locateFile: f => STATIC_BASE + '/sqljs/' + f
    });
    dbg('ensureSQL: sql.js loaded', { hasModule: !!SQL });
  }
}

function truncate(values, limit=500) {
  const truncated = values.length > limit;
  return { values: truncated ? values.slice(0, limit) : values, truncated };
}

function inspectSeed(seedBuf) {
  if (!seedBuf) return { present:false };
  const byteLength = seedBuf.byteLength || 0;
  const head = new Uint8Array(seedBuf, 0, Math.min(16, byteLength));
  const magic = Array.from(head).map(b => String.fromCharCode(b)).join('');
  const looksSqlite = magic.startsWith('SQLite format 3');
  return { present:true, byteLength, headHex: [...head].map(b=>b.toString(16).padStart(2,'0')).join(' '), magic, looksSqlite };
}

self.onmessage = async (ev) => {
  const { id, type, payload } = ev.data || {};
  try {
    if (type === 'init') {
      await ensureSQL();
      const seedBuf = payload?.seedBuf;
      const info = inspectSeed(seedBuf);
      dbg('init: seed info', info);

      let db;
      try {
        db = seedBuf
          ? new SQL.Database(new Uint8Array(seedBuf))
          : new SQL.Database();
        dbg('init: database created', { usedSeed: !!seedBuf });
      } catch (e) {
        dbg('init: ERROR creating database', { error: String(e) });
        throw e;
      }

      sessions.set(id, { db });
      self.postMessage({ id, type: 'result',
        payload: { columns: ['status'], rows: [['ready']], truncated:false }});

      try {
        const r = db.exec(`SELECT count(*) AS n
                           FROM sqlite_master
                           WHERE type IN ('table','view');`);
        const n = r?.[0]?.values?.[0]?.[0] ?? 0;
        dbg('init: sqlite_master count', { tables_and_views: n });
      } catch (e) {
        dbg('init: sqlite_master probe failed', { error: String(e) });
      }
    }

    else if (type === 'exec') {
      const s = sessions.get(id);
      if (!s || !s.db) throw new Error('No DB for this session.');
      const sql = payload?.sql || '';
      const limit = payload?.limit ?? 500;
      dbg('exec: received SQL', { len: sql.length, preview: sql.slice(0, 120) });

      let results;
      try {
        results = s.db.exec(sql);
      } catch (e) {
        dbg('exec: ERROR executing SQL', { error: String(e) });
        throw e;
      }

      if (!results.length) {
        self.postMessage({ id, type: 'result',
          payload: { columns: ['status'], rows: [['OK']], truncated:false }});
      } else {
        const r = results[0];
        const { values, truncated } = truncate(r.values, limit);
        self.postMessage({ id, type: 'result',
          payload: { columns: r.columns, rows: values, truncated }});
      }
    }

    else if (type === 'reset') {
      const s = sessions.get(id);
      if (s?.db) { try { s.db.close(); } catch {} }
      await ensureSQL();
      const seedBuf = payload?.seedBuf;
      const info = inspectSeed(seedBuf);
      dbg('reset: seed info', info);

      let db;
      try {
        db = seedBuf
          ? new SQL.Database(new Uint8Array(seedBuf))
          : new SQL.Database();
        dbg('reset: database recreated', { usedSeed: !!seedBuf });
      } catch (e) {
        dbg('reset: ERROR creating database', { error: String(e) });
        throw e;
      }

      sessions.set(id, { db });
      self.postMessage({ id, type: 'result',
        payload: { columns: ['status'], rows: [['reset']], truncated:false }});
    }

    else if (type === 'schema') {
      const s = sessions.get(id);
      if (!s || !s.db) throw new Error('No DB for this session.');
      let tables;
      try {
        tables = s.db.exec(`
          SELECT name, type FROM sqlite_master
          WHERE type IN ('table','view')
          ORDER BY type, name;
        `);
        dbg('schema: listed items', { count: tables?.[0]?.values?.length || 0 });
      } catch (e) {
        dbg('schema: ERROR listing', { error: String(e) });
        throw e;
      }
      self.postMessage({ id, type: 'schema', payload: tables });
    }

    else {
      dbg('unknown message type', { type });
    }

  } catch (e) {
    self.postMessage({ id, type: 'error', payload: String(e?.message || e) });
  }
};
