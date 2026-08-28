// _static/sql-statements.js
// Statementgrenzen in SQL-tekst (issue #34): Run voert de selectie uit, of
// anders het statement onder de cursor — daarvoor moet de editor weten waar
// elk statement begint en eindigt.
//
// Bewust een puur module zonder DOM of CodeMirror: sql-editors.js importeert
// het, en tests/sql-statements.test.mjs draait het rechtstreeks in Node.
//
// Regels:
//   - een puntkomma sluit een statement af, behalve in strings ('…'),
//     quoted identifiers ("…", `…`, […]) en commentaar (-- … en /* … */);
//   - een statement loopt van het eerste niet-witruimteteken na het vorige
//     statement tot en met zijn eigen puntkomma — leidend commentaar
//     ("-- opdracht 2") hoort dus bij het statement dat erop volgt;
//   - commentaar dat nog op de regel van de puntkomma staat ("SELECT 1; -- ok")
//     hoort wél nog bij dat statement, zodat de markering niet naar de
//     volgende regel overloopt;
//   - een stuk zonder code (alleen witruimte en/of commentaar, bv. een
//     afsluitende opmerking of een dubbele puntkomma) is geen statement.
//
// Beperking: puntkomma's in een CREATE TRIGGER-body gelden ook als grens.
// Zulke scripts draai je met "Run alles".

const WHITESPACE = /\s/;

/** Verdeel `text` in statements: een lijst van {from, to}-bereiken (to exclusief). */
export function splitStatements(text) {
  const statements = [];
  const n = text.length;
  let start = 0;       // begin van het huidige stuk (net na het vorige statement)
  let hasCode = false; // staat er in dit stuk iets anders dan witruimte/commentaar?

  const close = (end) => {
    if (hasCode) {
      let from = start;
      let to = end;
      while (from < to && WHITESPACE.test(text[from])) from++;
      while (to > from && WHITESPACE.test(text[to - 1])) to--;
      statements.push({ from, to });
    }
    start = end;
    hasCode = false;
  };

  let i = 0;
  while (i < n) {
    const ch = text[i];
    const next = text[i + 1];
    if (ch === '-' && next === '-') {                     // regelcommentaar
      i = lineCommentEnd(text, i);
    } else if (ch === '/' && next === '*') {              // blokcommentaar
      i = blockCommentEnd(text, i);
    } else if (ch === "'" || ch === '"' || ch === '`') {  // string of quoted identifier
      hasCode = true;
      i = skipQuoted(text, i, ch);
    } else if (ch === '[') {                              // [identifier]
      hasCode = true;
      const end = text.indexOf(']', i + 1);
      i = end === -1 ? n : end + 1;
    } else if (ch === ';') {
      const end = trailingCommentEnd(text, i + 1);
      close(end);
      i = end;
    } else {
      if (!WHITESPACE.test(ch)) hasCode = true;
      i++;
    }
  }
  close(n);
  return statements;
}

function lineCommentEnd(text, i) {
  const nl = text.indexOf('\n', i);
  return nl === -1 ? text.length : nl + 1;
}

function blockCommentEnd(text, i) {
  const end = text.indexOf('*/', i + 2);
  return end === -1 ? text.length : end + 2;
}

// Slaat een gequote string/identifier over; een verdubbelde quote ('') is
// een escape, geen einde. Niet afgesloten → de rest van de tekst hoort erbij.
function skipQuoted(text, i, quote) {
  let j = i + 1;
  while (j < text.length) {
    if (text[j] === quote) {
      if (text[j + 1] === quote) { j += 2; continue; }
      return j + 1;
    }
    j++;
  }
  return text.length;
}

// Commentaar dat na de puntkomma nog op dezelfde regel begint, hoort bij het
// statement dat net afgesloten werd. Geeft de positie na dat commentaar (of
// gewoon `pos` als er geen commentaar op de regel volgt).
function trailingCommentEnd(text, pos) {
  let j = pos;
  for (;;) {
    while (text[j] === ' ' || text[j] === '\t') j++;
    if (text[j] === '-' && text[j + 1] === '-') return lineCommentEnd(text, j);
    if (text[j] === '/' && text[j + 1] === '*') { j = blockCommentEnd(text, j); continue; }
    return j;
  }
}

/**
 * Het statement "onder de cursor" op positie `pos`, of null als er geen
 * statements zijn. Cursor in de witruimte tussen twee statements (bv. op de
 * lege regel na een puntkomma) → het statement ervóór, want dat is wat de
 * leerling net typte; vóór het eerste statement → het eerste.
 */
export function statementAt(statements, pos) {
  let previous = null;
  for (const st of statements) {
    if (pos < st.from) return previous ?? st;
    if (pos <= st.to) return st;
    previous = st;
  }
  return previous;
}
