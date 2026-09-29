// _static/overhoring.js
// Overhoringpagina's (issue #60): de open vragen en meerkeuzevragen, en de
// knop "Download mijn antwoorden".
//
// ES-module, alleen geladen op de pagina's in book/overhoringen/<naam>/
// (per pagina toegevoegd door _ext/overhoringen.py; _ext/sanitize_static_assets.py
// houdt het bestand van de andere pagina's weg). Het formaat van zo'n pagina
// staat in book/overhoringen/README.md:
//   - elke vraag is een kop "## Vraag n" met de vraagtekst, gevolgd door één
//     antwoordcel met tag `sql-live` (de SQL-editor uit sql-editors.js),
//     `overhoring-open` (tekstvak) of `overhoring-mc` (radioknoppen, één
//     optie per regel);
//   - de extensie zet de vragen als JSON in #overhoring-data (Markdown-bron
//     van de doelen en de vragen); de antwoordcellen staan in dezelfde
//     volgorde op de pagina en worden op volgorde gekoppeld.
//
// Antwoorden op open en meerkeuzevragen blijven per vraag bewaard in
// localStorage (zoals de editor dat per cel doet, #14), zodat herladen of
// een vastgelopen laptop het werk niet wist. De queries bewaart de editor
// zelf; de download leest ze via de publieke API
// window.sqlLive.editors[i].getValue() (beschikbaar na het event
// `sql-live:ready`).

import { answersFileName, buildAnswersMarkdown } from './overhoring-markdown.js';

const ANSWER_CELLS = '.cell.tag_sql-live, .cell.tag_overhoring-open, .cell.tag_overhoring-mc';

function cellType(cell) {
  if (cell.classList.contains('tag_sql-live')) return 'sql';
  if (cell.classList.contains('tag_overhoring-open')) return 'open';
  return 'mc';
}

// --- Opslag per vraag (net als de editor: elke toegang in try/catch) ---
function storageKey(index) {
  return `overhoring:${location.pathname}:${index}`;
}

function readSaved(index) {
  try {
    return window.localStorage.getItem(storageKey(index));
  } catch {
    return null; // opslag geblokkeerd — gewoon leeg beginnen
  }
}

function writeSaved(index, value) {
  try {
    if (value === null || value === '') window.localStorage.removeItem(storageKey(index));
    else window.localStorage.setItem(storageKey(index), value);
  } catch {
    /* opslag geblokkeerd of vol — het antwoord staat wel op de pagina */
  }
}

// Optietekst met `code` tussen backticks, zonder innerHTML.
function inlineText(text) {
  const fragment = document.createDocumentFragment();
  String(text).split('`').forEach((part, i) => {
    if (!part) return;
    if (i % 2 === 1) {
      const code = document.createElement('code');
      code.className = 'docutils literal notranslate';
      code.textContent = part;
      fragment.appendChild(code);
    } else {
      fragment.appendChild(document.createTextNode(part));
    }
  });
  return fragment;
}

function replaceCellInput(cell, element) {
  cell.querySelector('.cell_input')?.remove();
  cell.appendChild(element);
}

// --- Open vraag: een tekstvak ---
function mountOpen(cell, question, index) {
  const id = `overhoring-antwoord-${question.number}`;
  const wrap = document.createElement('div');
  wrap.className = 'overhoring-answer overhoring-open';
  const label = document.createElement('label');
  label.className = 'overhoring-answer__label';
  label.htmlFor = id;
  label.textContent = 'Jouw antwoord';
  const input = document.createElement('textarea');
  input.className = 'overhoring-open__input';
  input.id = id;
  input.rows = 6;
  input.placeholder = question.placeholder || '';
  input.value = readSaved(index) ?? '';
  input.addEventListener('input', () => writeSaved(index, input.value));
  wrap.append(label, input);
  replaceCellInput(cell, wrap);
  return () => input.value;
}

// --- Meerkeuzevraag: één antwoord, radioknoppen ---
function mountMc(cell, question, index) {
  const fieldset = document.createElement('fieldset');
  fieldset.className = 'overhoring-answer overhoring-mc';
  const legend = document.createElement('legend');
  legend.className = 'overhoring-answer__label';
  legend.textContent = 'Kies één antwoord';
  fieldset.appendChild(legend);
  // Bewaard als optietekst, niet als positie: een opgeschoven optie mag nooit
  // stilletjes een ander antwoord worden.
  const saved = readSaved(index);
  question.options.forEach((option, i) => {
    const label = document.createElement('label');
    label.className = 'overhoring-mc__option';
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = `overhoring-vraag-${question.number}`;
    radio.value = String(i);
    radio.checked = option === saved;
    radio.addEventListener('change', () => { if (radio.checked) writeSaved(index, option); });
    const text = document.createElement('span');
    text.appendChild(inlineText(option));
    label.append(radio, text);
    fieldset.appendChild(label);
  });
  replaceCellInput(cell, fieldset);
  return () => {
    const checked = fieldset.querySelector('input:checked');
    return checked ? question.options[Number(checked.value)] : null;
  };
}

// --- SQL-vraag: de editor uit sql-editors.js ---
function mountSql(sqlIndex) {
  return () => window.sqlLive.editors[sqlIndex].getValue();
}

// --- Download mijn antwoorden ---
function timestamp(date = new Date()) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function saveText(text, fileName) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function addSubmitBar(article, quiz, getters, hasSql) {
  const fileName = answersFileName(quiz.id);
  const bar = document.createElement('div');
  bar.className = 'overhoring-submit';
  const note = document.createElement('p');
  note.className = 'overhoring-submit__note';
  note.append('Klaar? Download je antwoorden en dien het bestand ');
  const code = document.createElement('code');
  code.textContent = fileName;
  note.append(code, ' in via Teams.');
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'overhoring-submit__button';
  button.textContent = 'Download mijn antwoorden';
  const status = document.createElement('p');
  status.className = 'overhoring-submit__status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.hidden = true;
  const report = (message, isError = false) => {
    status.textContent = message;
    status.classList.toggle('is-error', isError);
    status.hidden = false;
  };

  button.addEventListener('click', () => {
    if (hasSql && !window.sqlLive) {
      report('De SQL-editor wordt nog geladen — probeer zo meteen opnieuw.', true);
      return;
    }
    try {
      const answers = getters.map(get => get());
      const markdown = buildAnswersMarkdown(quiz, answers, {
        page: location.pathname,
        downloadedAt: timestamp(),
      });
      saveText(markdown, fileName);
      report(`Gedownload: ${fileName}. Dien dit bestand in via Teams.`);
    } catch (e) {
      console.error('Overhoring: antwoorden downloaden mislukt:', e);
      report(`Downloaden mislukt: ${e?.message || e}`, true);
    }
  });

  bar.append(note, button, status);
  article.appendChild(bar);
  return { button, report };
}

function init() {
  const data = document.getElementById('overhoring-data');
  const article = document.querySelector('article.bd-article');
  if (!data || !article) return;
  const quiz = JSON.parse(data.textContent);
  const cells = [...document.querySelectorAll(ANSWER_CELLS)];
  const types = cells.map(cellType);
  const expected = quiz.questions.map(q => q.type);

  let sqlIndex = 0;
  const getters = [];
  const mismatch = types.length !== expected.length || types.some((t, i) => t !== expected[i]);
  if (!mismatch) {
    quiz.questions.forEach((question, index) => {
      const cell = cells[index];
      if (question.type === 'sql') getters.push(mountSql(sqlIndex++));
      else if (question.type === 'open') getters.push(mountOpen(cell, question, index));
      else getters.push(mountMc(cell, question, index));
    });
  }

  const { button, report } = addSubmitBar(article, quiz, getters, sqlIndex > 0);
  if (mismatch) {
    // Zou de build al gemeld moeten hebben (_ext/overhoringen.py); hier
    // zichtbaar voor de leerling, zodat die de leraar kan roepen.
    console.error('Overhoring: antwoordcellen', types, 'passen niet bij de vragen', expected);
    button.disabled = true;
    report('Deze overhoring is niet goed opgebouwd: de antwoordvakken passen niet bij de vragen. Meld dit aan je leraar.', true);
  }
}

if (/complete|interactive/.test(document.readyState)) init();
else document.addEventListener('DOMContentLoaded', init, { once: true });
