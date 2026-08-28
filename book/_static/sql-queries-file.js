// _static/sql-queries-file.js
// Het .sql-bestandsformaat van "Download mijn queries" (#30) en de
// tegenhanger "Upload mijn queries" (#35): één bestand per pagina, met een
// bestandskop met het paginapad en een commentaarkop per cel:
//
//     -- Mijn queries — /DataBeheer/chapters/SQL/01_Starten_met_sql.html
//
//     -- cel 1
//     SELECT …;
//
//     -- cel 2
//     …
//
// Bewust een puur module zonder DOM: sql-editors.js gebruikt het voor de
// download én de upload (één definitie, dus download → upload geeft dezelfde
// cellen terug), en tests/sql-queries-file.test.mjs draait het rechtstreeks
// in Node.
//
// Beperking: een regel die exact "-- cel N" is, geldt altijd als celkop —
// ook als een leerling die zelf in een cel typte.

const FILE_HEADER = '-- Mijn queries — ';
const CELL_HEADER = /^-- cel (\d+)\s*$/;

/** De paginanaam uit een pad: "/x/chapters/SQL/01_Starten.html" → "01_Starten". */
export function pageName(path) {
  return (String(path).split('/').pop() || '').replace(/\.html?$/i, '');
}

/**
 * Bouw het bestand voor pagina `pagePath` uit `cells`: een lijst van
 * {index (0-based), sql}. De celinhoud wordt getrimd.
 */
export function buildQueriesFile(pagePath, cells) {
  const parts = cells.map(c => `-- cel ${c.index + 1}\n${String(c.sql).trim()}\n`);
  return `${FILE_HEADER}${pagePath}\n\n${parts.join('\n')}`;
}

/**
 * Lees een bestand terug: { page, cells }. `page` is het paginapad uit de
 * bestandskop (null als die ontbreekt); `cells` is een lijst van
 * {index (0-based), sql}, gesorteerd op index. De celinhoud wordt getrimd
 * zoals bij het bouwen; regeleinden worden genormaliseerd (CRLF na een omweg
 * via Kladblok) en een BOM wordt genegeerd. Tekst vóór de eerste celkop
 * (behalve de bestandskop) telt niet mee; bij een dubbele celkop wint de
 * laatste.
 */
export function parseQueriesFile(text) {
  const lines = String(text).replace(/^﻿/, '').replace(/\r\n?/g, '\n').split('\n');
  let page = null;
  let current = null;
  const byIndex = new Map();
  for (const line of lines) {
    const m = CELL_HEADER.exec(line);
    if (m) {
      current = { index: Number(m[1]) - 1, lines: [] };
      if (current.index >= 0) byIndex.set(current.index, current);
      continue;
    }
    if (current) current.lines.push(line);
    else if (page === null && line.startsWith(FILE_HEADER)) page = line.slice(FILE_HEADER.length).trim();
  }
  const cells = [...byIndex.values()]
    .sort((a, b) => a.index - b.index)
    .map(c => ({ index: c.index, sql: c.lines.join('\n').trim() }));
  return { page, cells };
}
