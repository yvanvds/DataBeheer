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
// Heeft de pagina antwoordvakken (cellen met tag `sql-answer`, #79), dan
// volgen na de cellen de antwoorden, elk met een kop met de vraag erin: zo
// leest de leraar het bestand zonder de pagina ernaast. Bij het teruglezen
// telt alleen het nummer; de vraag in de kop is uitleg:
//
//     -- antwoord 1: Welke query leverde het doorslaggevende bewijs?
//     De query in stap 6, want …
//
// Een bestand zonder antwoorden (van elke andere pagina, en elk bestand van
// vóór #79) ziet er dus precies zo uit als vroeger en leest ook zo terug.
//
// Bewust een puur module zonder DOM: sql-editors.js gebruikt het voor de
// download én de upload (één definitie, dus download → upload geeft dezelfde
// cellen en antwoorden terug), en tests/sql-queries-file.test.mjs draait het
// rechtstreeks in Node.
//
// Beperking: een regel die exact "-- cel N" of "-- antwoord N" is, of die met
// "-- antwoord N:" begint, geldt altijd als kop — ook als een leerling die
// zelf in een cel of een antwoord typte.

const FILE_HEADER = '-- Mijn queries — ';
const CELL_HEADER = /^-- cel (\d+)\s*$/;
const ANSWER_HEADER = /^-- antwoord (\d+)(?::.*|\s*)$/;

/** De paginanaam uit een pad: "/x/chapters/SQL/01_Starten.html" → "01_Starten". */
export function pageName(path) {
  return (String(path).split('/').pop() || '').replace(/\.html?$/i, '');
}

/** De kop van een antwoord, met de vraag op één regel zodat ze de kop niet breekt. */
function answerHeader(index, question) {
  const oneLine = String(question ?? '').replace(/\s+/g, ' ').trim();
  return `-- antwoord ${index + 1}${oneLine ? `: ${oneLine}` : ''}`;
}

/**
 * Bouw het bestand voor pagina `pagePath` uit `cells`: een lijst van
 * {index (0-based), sql}, en uit `answers`: een lijst van
 * {index (0-based), question, text} (#79; leeg op de meeste pagina's). De
 * celinhoud en de antwoorden worden getrimd.
 */
export function buildQueriesFile(pagePath, cells, answers = []) {
  const parts = [
    ...cells.map(c => `-- cel ${c.index + 1}\n${String(c.sql).trim()}\n`),
    ...answers.map(a => `${answerHeader(a.index, a.question)}\n${String(a.text ?? '').trim()}\n`),
  ];
  return `${FILE_HEADER}${pagePath}\n\n${parts.join('\n')}`;
}

function sortedSections(byIndex, key) {
  return [...byIndex.values()]
    .sort((a, b) => a.index - b.index)
    .map(s => ({ index: s.index, [key]: s.lines.join('\n').trim() }));
}

/**
 * Lees een bestand terug: { page, cells, answers }. `page` is het paginapad
 * uit de bestandskop (null als die ontbreekt); `cells` is een lijst van
 * {index (0-based), sql} en `answers` een lijst van {index (0-based), text},
 * elk gesorteerd op index. De inhoud wordt getrimd zoals bij het bouwen;
 * regeleinden worden genormaliseerd (CRLF na een omweg via Kladblok) en een
 * BOM wordt genegeerd. Tekst vóór de eerste kop (behalve de bestandskop)
 * telt niet mee; bij een dubbele kop wint de laatste.
 */
export function parseQueriesFile(text) {
  const lines = String(text).replace(/^﻿/, '').replace(/\r\n?/g, '\n').split('\n');
  let page = null;
  let current = null;
  const cellsByIndex = new Map();
  const answersByIndex = new Map();
  for (const line of lines) {
    const cell = CELL_HEADER.exec(line);
    const m = cell || ANSWER_HEADER.exec(line);
    if (m) {
      current = { index: Number(m[1]) - 1, lines: [] };
      if (current.index >= 0) (cell ? cellsByIndex : answersByIndex).set(current.index, current);
      continue;
    }
    if (current) current.lines.push(line);
    else if (page === null && line.startsWith(FILE_HEADER)) page = line.slice(FILE_HEADER.length).trim();
  }
  return {
    page,
    cells: sortedSections(cellsByIndex, 'sql'),
    answers: sortedSections(answersByIndex, 'text'),
  };
}
