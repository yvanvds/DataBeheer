// Unit-tests voor het .sql-bestandsformaat van de SQL-editor ("Download mijn
// queries" #30, "Upload mijn queries" #35): book/_static/sql-queries-file.js.
// Draaien met de ingebouwde testrunner van Node (geen extra pakketten):
//
//     node --test tests/sql-queries-file.test.mjs
//
// tests/test_sql_editor.py roept dit ook aan vanuit pytest.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildQueriesFile, parseQueriesFile, pageName } from '../book/_static/sql-queries-file.js';

const PAGE = '/DataBeheer/chapters/SQL/01_Starten_met_sql.html';

test('buildQueriesFile: het bestandsformaat van "Download mijn queries" (#30)', () => {
  const file = buildQueriesFile(PAGE, [
    { index: 0, sql: 'SELECT 1;' },
    { index: 1, sql: '  -- opdracht 2\nSELECT 2;\n\n' },
  ]);
  assert.equal(
    file,
    `-- Mijn queries — ${PAGE}\n\n` +
    '-- cel 1\nSELECT 1;\n\n' +
    '-- cel 2\n-- opdracht 2\nSELECT 2;\n',
  );
});

test('parseQueriesFile: bestandskop en cellen', () => {
  const parsed = parseQueriesFile(
    `-- Mijn queries — ${PAGE}\n\n-- cel 1\nSELECT 1;\n\n-- cel 2\nSELECT 2;\n`,
  );
  assert.equal(parsed.page, PAGE);
  assert.deepEqual(parsed.cells, [
    { index: 0, sql: 'SELECT 1;' },
    { index: 1, sql: 'SELECT 2;' },
  ]);
});

test('download → upload geeft dezelfde cellen terug (round-trip)', () => {
  const cells = [
    { index: 0, sql: '-- twee statements\nSELECT 1;\n\nSELECT 2;' },
    { index: 1, sql: "SELECT 'tekst -- cel 9 in een string';" },
    { index: 2, sql: '/* blok\n   commentaar */\nSELECT name,\n       unit_price\nFROM products;' },
  ];
  const parsed = parseQueriesFile(buildQueriesFile(PAGE, cells));
  assert.equal(parsed.page, PAGE);
  assert.deepEqual(parsed.cells, cells);
});

test('lege cellen overleven de round-trip als lege tekst', () => {
  const cells = [{ index: 0, sql: '' }, { index: 1, sql: 'SELECT 2;' }];
  assert.deepEqual(parseQueriesFile(buildQueriesFile(PAGE, cells)).cells, cells);
});

test('CRLF-regeleinden en een BOM (omweg via Kladblok) worden genormaliseerd', () => {
  const parsed = parseQueriesFile(
    '﻿-- Mijn queries — /a/b.html\r\n\r\n-- cel 1\r\nSELECT 1;\r\n\r\n-- cel 2\r\nSELECT 2;\r\n',
  );
  assert.equal(parsed.page, '/a/b.html');
  assert.deepEqual(parsed.cells, [{ index: 0, sql: 'SELECT 1;' }, { index: 1, sql: 'SELECT 2;' }]);
});

test('zonder celkoppen zijn er geen cellen; zonder bestandskop geen pagina', () => {
  assert.deepEqual(parseQueriesFile(''), { page: null, cells: [] });
  assert.deepEqual(parseQueriesFile('SELECT 1;\nSELECT 2;'), { page: null, cells: [] });
  assert.deepEqual(parseQueriesFile('-- cel 1\nSELECT 1;'), {
    page: null,
    cells: [{ index: 0, sql: 'SELECT 1;' }],
  });
});

test('celkoppen: gesorteerd op nummer, de laatste wint bij dubbels, "cel 0" telt niet', () => {
  const parsed = parseQueriesFile(
    '-- cel 3\nSELECT 3;\n-- cel 1\nSELECT 1;\n-- cel 0\nSELECT 0;\n-- cel 1\nSELECT 1b;\n-- cel 12 \nSELECT 12;',
  );
  assert.deepEqual(parsed.cells, [
    { index: 0, sql: 'SELECT 1b;' },
    { index: 2, sql: 'SELECT 3;' },
    { index: 11, sql: 'SELECT 12;' },
  ]);
});

test('alleen een regel die exact "-- cel N" is, geldt als celkop', () => {
  const parsed = parseQueriesFile('-- cel 1\n-- cel 2 is de volgende opdracht\nSELECT 1; -- cel 3\n');
  assert.deepEqual(parsed.cells, [
    { index: 0, sql: '-- cel 2 is de volgende opdracht\nSELECT 1; -- cel 3' },
  ]);
});

test('pageName: bestandsnaam zonder .html', () => {
  assert.equal(pageName('/DataBeheer/chapters/SQL/01_Starten_met_sql.html'), '01_Starten_met_sql');
  assert.equal(pageName('chapters/SQL/02_Joins.htm'), '02_Joins');
  assert.equal(pageName('/'), '');
});
