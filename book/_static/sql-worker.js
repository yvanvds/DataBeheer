// _static/sql-worker.js  (classic worker)
importScripts('/_static/sqljs/sql-wasm.js');

let SQL; // sql.js module factory
const sessions = new Map(); // id -> { db }

async function ensureSQL() {
  if (!SQL) {
    SQL = await initSqlJs({
      locateFile: f => '/_static/sqljs/' + f
    });
  }
}

function truncate(values, limit=500) {
  const truncated = values.length > limit;
  return { values: truncated ? values.slice(0, limit) : values, truncated };
}

self.onmessage = async (ev) => {
  const { id, type, payload } = ev.data || {};
  try {
    if (type === 'init') {
      await ensureSQL();
      const seedBuf = payload?.seedBuf; // ArrayBuffer, optional
      const db = seedBuf
        ? new SQL.Database(new Uint8Array(seedBuf))
        : new SQL.Database();
      sessions.set(id, { db });
      self.postMessage({
        id, type: 'result',
        payload: { columns: ['status'], rows: [['ready']], truncated:false }
      });
    }

    else if (type === 'exec') {
      const s = sessions.get(id);
      if (!s || !s.db) throw new Error('No DB for this session.');
      const sql = payload?.sql || '';
      const limit = payload?.limit ?? 500;
      const results = s.db.exec(sql);
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
      const seedBuf = payload?.seedBuf; // optional
      const db = seedBuf
        ? new SQL.Database(new Uint8Array(seedBuf))
        : new SQL.Database();
      sessions.set(id, { db });
      self.postMessage({ id, type: 'result',
        payload: { columns: ['status'], rows: [['reset']], truncated:false }});
    }

    else if (type === 'schema') {
      const s = sessions.get(id);
      if (!s || !s.db) throw new Error('No DB for this session.');
      const tables = s.db.exec(`
        SELECT name, type FROM sqlite_master
        WHERE type IN ('table','view')
        ORDER BY type, name;
      `);
      self.postMessage({ id, type: 'schema', payload: tables });
    }

  } catch (e) {
    self.postMessage({ id, type: 'error', payload: String(e?.message || e) });
  }
};