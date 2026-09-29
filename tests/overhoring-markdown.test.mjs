// Unit-tests voor het bestand van "Download mijn antwoorden" op een
// overhoringpagina (issue #60): book/_static/overhoring-markdown.js.
// Draaien met de ingebouwde testrunner van Node (geen extra pakketten):
//
//     node --test tests/overhoring-markdown.test.mjs
//
// tests/test_overhoringen.py roept dit ook aan vanuit pytest.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  answersFileName, fenceFor, formatAnswer, buildAnswersMarkdown,
} from '../book/_static/overhoring-markdown.js';

// Zoals _ext/overhoringen.py de overhoring in de pagina zet.
const QUIZ = {
  id: 'sql-h1-h2',
  title: 'SQL: starten en filteren',
  doelen: '- Je kan filteren met `WHERE`.\n- Je kan uitleggen wat een query doet.',
  questions: [
    { heading: 'Vraag 1', number: 1, type: 'sql', text: 'Toon alle klanten uit Gent.' },
    { heading: 'Vraag 2', number: 2, type: 'open', text: 'Leg uit:\n\n```sql\nSELECT DISTINCT city FROM customers;\n```', placeholder: 'Schrijf hier.' },
    { heading: 'Vraag 3 — NULL', number: 3, type: 'mc', text: 'Welke voorwaarde?', options: ['`email = NULL`', '`email IS NULL`', "`email = ''`"] },
  ],
};

test('answersFileName: <naam>-antwoorden.md', () => {
  assert.equal(answersFileName('sql-h1-h2'), 'sql-h1-h2-antwoorden.md');
  assert.equal(answersFileName('sql-h1-h2-groep-b'), 'sql-h1-h2-groep-b-antwoorden.md');
  assert.equal(answersFileName('rare naam/met tekens'), 'rare_naam_met_tekens-antwoorden.md');
  assert.equal(answersFileName(''), 'overhoring-antwoorden.md');
});

test('fenceFor: langer dan elke reeks backticks in de tekst', () => {
  assert.equal(fenceFor('SELECT 1;'), '```');
  assert.equal(fenceFor('SELECT `naam` FROM t;'), '```');
  assert.equal(fenceFor('-- ``` in commentaar'), '````');
  assert.equal(fenceFor('-- ````` vijf'), '``````');
});

test('formatAnswer sql: de query als ```sql-blok, witruimte achteraan weg', () => {
  const sql = "SELECT *\nFROM customers\nWHERE city = 'Gent';\n\n  ";
  assert.equal(formatAnswer(QUIZ.questions[0], sql), "```sql\nSELECT *\nFROM customers\nWHERE city = 'Gent';\n```");
  // Een query met ``` sluit het blok niet af.
  assert.equal(formatAnswer(QUIZ.questions[0], '-- ```\nSELECT 1;'), '````sql\n-- ```\nSELECT 1;\n````');
});

test('formatAnswer open: als citaat, of "geen antwoord"', () => {
  const q = QUIZ.questions[1];
  assert.equal(formatAnswer(q, 'Eén regel.'), '> Eén regel.');
  assert.equal(formatAnswer(q, '# Kop\n\n- punt\n'), '> # Kop\n>\n> - punt');
  assert.equal(formatAnswer(q, ''), '_(geen antwoord)_');
  assert.equal(formatAnswer(q, '   \n  '), '_(geen antwoord)_');
  assert.equal(formatAnswer(q, undefined), '_(geen antwoord)_');
});

test('formatAnswer mc: alle opties, de gekozen aangevinkt', () => {
  const q = QUIZ.questions[2];
  assert.equal(
    formatAnswer(q, '`email IS NULL`'),
    "- [ ] `email = NULL`\n- [x] `email IS NULL`\n- [ ] `email = ''`",
  );
  assert.equal(
    formatAnswer(q, null),
    "- [ ] `email = NULL`\n- [ ] `email IS NULL`\n- [ ] `email = ''`\n\n_(geen keuze gemaakt)_",
  );
});

test('buildAnswersMarkdown: doelen, elke vraag met haar antwoord, in volgorde', () => {
  const md = buildAnswersMarkdown(
    QUIZ,
    ["SELECT * FROM customers WHERE city = 'Gent';", 'Het toont elke stad één keer.', '`email IS NULL`'],
    { page: '/DataBeheer/overhoringen/sql-h1-h2/overhoring.html', downloadedAt: '2026-10-01 10:15' },
  );
  assert.equal(
    md,
    [
      '# SQL: starten en filteren — antwoorden',
      '',
      '- Overhoring: sql-h1-h2',
      '- Pagina: /DataBeheer/overhoringen/sql-h1-h2/overhoring.html',
      '- Gedownload: 2026-10-01 10:15',
      '',
      '## Doelen',
      '',
      '- Je kan filteren met `WHERE`.',
      '- Je kan uitleggen wat een query doet.',
      '',
      '## Vraag 1',
      '',
      'Toon alle klanten uit Gent.',
      '',
      '**Antwoord:**',
      '',
      '```sql',
      "SELECT * FROM customers WHERE city = 'Gent';",
      '```',
      '',
      '## Vraag 2',
      '',
      'Leg uit:',
      '',
      '```sql',
      'SELECT DISTINCT city FROM customers;',
      '```',
      '',
      '**Antwoord:**',
      '',
      '> Het toont elke stad één keer.',
      '',
      '## Vraag 3 — NULL',
      '',
      'Welke voorwaarde?',
      '',
      '**Antwoord:**',
      '',
      '- [ ] `email = NULL`',
      '- [x] `email IS NULL`',
      "- [ ] `email = ''`",
      '',
    ].join('\n'),
  );
});

test('buildAnswersMarkdown: zonder antwoorden staat elke vraag er toch', () => {
  const md = buildAnswersMarkdown(QUIZ, ['', '', null]);
  for (const q of QUIZ.questions) assert.ok(md.includes(`## ${q.heading}\n\n${q.text}\n`), q.heading);
  assert.ok(md.includes('```sql\n\n```'));
  assert.ok(md.includes('_(geen antwoord)_'));
  assert.ok(md.includes('_(geen keuze gemaakt)_'));
  assert.ok(!md.includes('- Pagina:'));
});
