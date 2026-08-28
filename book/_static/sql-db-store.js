// _static/sql-db-store.js
// Opslag van de paginadatabank in IndexedDB (#41). Eén databank "sql-live"
// met één object store "databases"; sleutel = de pagina-id van de editor
// (`db:{pad}`), waarde = { bytes: Uint8Array (het SQLite-bestand), savedAt }.
//
// localStorage is hier ongeschikt: het bewaart alleen strings, met een limiet
// van enkele MB per site, terwijl één seed al 2,7 MB kan zijn (AdventureWorks).
// IndexedDB bewaart binaire data en heeft ruimte zat.
//
// Alle functies zijn tolerant: opslag kan geblokkeerd zijn (strenge
// privacy-instellingen, sommige privévensters), vol zitten of ontbreken. Ze
// gooien nooit en geven dan null/false terug; de editor werkt dan gewoon
// zonder bewaarde databank (zoals bij localStorage in #14).
//
// De bewerkingen lopen in volgorde van aanroep (één wachtrij), zodat een
// snapshot die nog onderweg is nooit een latere "Reset db" overschrijft.

const DB_NAME = 'sql-live';
const STORE = 'databases';
const VERSION = 1;

let queue = Promise.resolve();

function enqueue(task) {
  const run = () => task();
  queue = queue.then(run, run);
  return queue;
}

function openStore() {
  return new Promise((resolve, reject) => {
    let req;
    try {
      req = indexedDB.open(DB_NAME, VERSION); // gooit zelf bij geblokkeerde opslag
    } catch (e) {
      reject(e);
      return;
    }
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error('IndexedDB openen mislukt'));
    req.onblocked = () => reject(new Error('IndexedDB geblokkeerd door een ander tabblad'));
  });
}

function withStore(mode, action) {
  return enqueue(async () => {
    const db = await openStore();
    try {
      return await new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, mode);
        const request = action(tx.objectStore(STORE));
        tx.oncomplete = () => resolve(request.result);
        tx.onerror = () => reject(tx.error || new Error('IndexedDB-transactie mislukt'));
        tx.onabort = () => reject(tx.error || new Error('IndexedDB-transactie afgebroken'));
      });
    } finally {
      db.close();
    }
  });
}

/** De bewaarde databank voor `key` als Uint8Array, of null als er geen (bruikbare) is. */
export async function readSavedDb(key) {
  try {
    const record = await withStore('readonly', store => store.get(key));
    return record?.bytes instanceof Uint8Array ? record.bytes : null;
  } catch {
    return null;
  }
}

/** Bewaar `bytes` (Uint8Array) onder `key`. Geeft true als het lukte. */
export async function writeSavedDb(key, bytes) {
  try {
    await withStore('readwrite', store => store.put({ bytes, savedAt: Date.now() }, key));
    return true;
  } catch {
    return false;
  }
}

/** Verwijder de bewaarde databank voor `key`. Geeft true als het lukte (ook als er niets stond). */
export async function deleteSavedDb(key) {
  try {
    await withStore('readwrite', store => store.delete(key));
    return true;
  } catch {
    return false;
  }
}
