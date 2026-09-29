// _static/overhoring-markdown.js
// Het bestand van "Download mijn antwoorden" op een overhoringpagina (issue #60).
//
// Pure functies zonder DOM, zodat ze in Node getest worden
// (tests/overhoring-markdown.test.mjs); overhoring.js importeert ze.
//
// De overhoring (`quiz`) is de JSON die _ext/overhoringen.py in de pagina
// zet: { id, title, doelen, questions: [{ heading, number, text, type,
// options?, placeholder? }] }, met de Markdown-bron van de doelen en van elke
// vraag. `answers` staat in dezelfde volgorde als de vragen:
//   - sql:  de query uit de editor (string);
//   - open: de tekst uit het tekstvak (string);
//   - mc:   de tekst van de gekozen optie, of null.
// Het resultaat is één Markdown-bestand met de doelen, elke vraag en het
// antwoord: de query als ```sql-blok, de open tekst als citaat, en bij
// meerkeuze alle opties met de gekozen optie aangevinkt.

const NO_ANSWER = '_(geen antwoord)_';
const NO_CHOICE = '_(geen keuze gemaakt)_';

// Bestandsnaam met de naam van de overhoring: `<naam>-antwoorden.md`.
export function answersFileName(id) {
  const name = String(id ?? '').trim().replace(/[^\w.-]+/g, '_');
  return `${name || 'overhoring'}-antwoorden.md`;
}

// Een codeblokomheining die langer is dan elke reeks backticks in de tekst,
// zodat een query met ``` het blok niet vroegtijdig afsluit.
export function fenceFor(text) {
  const longest = (String(text).match(/`+/g) || []).reduce((n, run) => Math.max(n, run.length), 0);
  return '`'.repeat(Math.max(3, longest + 1));
}

function sqlAnswer(sql) {
  const body = String(sql ?? '').replace(/\s+$/, '');
  const fence = fenceFor(body);
  return `${fence}sql\n${body}\n${fence}`;
}

function openAnswer(text) {
  const body = String(text ?? '').replace(/\s+$/, '').replace(/^\s*\n/, '');
  if (!body.trim()) return NO_ANSWER;
  // Als citaat: het antwoord van de leerling blijft zichtbaar gescheiden van
  // de vraag, ook als het zelf Markdown (#, -, ...) bevat.
  return body.split('\n').map(line => (line.trim() ? `> ${line}` : '>')).join('\n');
}

function mcAnswer(options, choice) {
  const lines = (options || []).map(option => `- [${option === choice ? 'x' : ' '}] ${option}`);
  if (!(options || []).includes(choice)) lines.push('', NO_CHOICE);
  return lines.join('\n');
}

export function formatAnswer(question, answer) {
  switch (question.type) {
    case 'sql': return sqlAnswer(answer);
    case 'open': return openAnswer(answer);
    case 'mc': return mcAnswer(question.options, answer);
    default: return NO_ANSWER;
  }
}

// `meta`: { page, downloadedAt } — informatief, bovenaan het bestand.
export function buildAnswersMarkdown(quiz, answers, meta = {}) {
  const lines = [`# ${quiz.title} — antwoorden`, ''];
  lines.push(`- Overhoring: ${quiz.id}`);
  if (meta.page) lines.push(`- Pagina: ${meta.page}`);
  if (meta.downloadedAt) lines.push(`- Gedownload: ${meta.downloadedAt}`);
  lines.push('', '## Doelen', '', quiz.doelen, '');
  quiz.questions.forEach((question, i) => {
    lines.push(`## ${question.heading}`, '', question.text, '');
    lines.push('**Antwoord:**', '', formatAnswer(question, answers[i]), '');
  });
  return lines.join('\n');
}
