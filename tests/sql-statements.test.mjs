// Unit-tests voor de statementgrenzen van de SQL-editor (issue #34):
// book/_static/sql-statements.js. Draaien met de ingebouwde testrunner van
// Node (geen extra pakketten):
//
//     node --test tests/sql-statements.test.mjs
//
// tests/test_sql_editor.py roept dit ook aan vanuit pytest.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { splitStatements, statementAt } from '../book/_static/sql-statements.js';

const texts = (text) => splitStatements(text).map(({ from, to }) => text.slice(from, to));

test('puntkomma\'s verdelen de tekst in statements, zonder witruimte eromheen', () => {
  assert.deepEqual(texts('SELECT 1;\n\n  SELECT 2;\n'), ['SELECT 1;', 'SELECT 2;']);
  assert.deepEqual(texts('SELECT 1; SELECT 2;'), ['SELECT 1;', 'SELECT 2;']);
});

test('het laatste statement mag zonder puntkomma eindigen', () => {
  assert.deepEqual(texts('SELECT 1;\nSELECT 2'), ['SELECT 1;', 'SELECT 2']);
  assert.deepEqual(texts('SELECT 1'), ['SELECT 1']);
});

test('puntkomma\'s in strings en quoted identifiers tellen niet', () => {
  assert.deepEqual(
    texts("SELECT ';' AS a; SELECT 'it''s; fine' AS b;"),
    ["SELECT ';' AS a;", "SELECT 'it''s; fine' AS b;"],
  );
  assert.deepEqual(
    texts('SELECT "kolom;" FROM t; SELECT `x;y`, [a;b] FROM t;'),
    ['SELECT "kolom;" FROM t;', 'SELECT `x;y`, [a;b] FROM t;'],
  );
  // Niet-afgesloten string: de rest hoort bij dat statement.
  assert.deepEqual(texts("SELECT 'open; SELECT 2;"), ["SELECT 'open; SELECT 2;"]);
});

test('puntkomma\'s in commentaar tellen niet', () => {
  assert.deepEqual(
    texts('SELECT 1; -- niet; hier\nSELECT 2; /* ook; niet */ SELECT 3;'),
    ['SELECT 1; -- niet; hier', 'SELECT 2; /* ook; niet */', 'SELECT 3;'],
  );
  assert.deepEqual(
    texts('/* a;\n b; */\nSELECT 1;\n-- x;\nSELECT 2;'),
    ['/* a;\n b; */\nSELECT 1;', '-- x;\nSELECT 2;'],
  );
});

test('leidend commentaar hoort bij het statement dat erop volgt', () => {
  assert.deepEqual(
    texts('-- opdracht 1\nSELECT 1;\n\n-- opdracht 2\nSELECT 2;'),
    ['-- opdracht 1\nSELECT 1;', '-- opdracht 2\nSELECT 2;'],
  );
});

test('stukken zonder code zijn geen statement', () => {
  assert.deepEqual(texts(''), []);
  assert.deepEqual(texts('   \n\n'), []);
  assert.deepEqual(texts('-- alleen commentaar\n\n/* meer */'), []);
  assert.deepEqual(texts('SELECT 1;;\n\n-- klaar\n'), ['SELECT 1;']);
  assert.deepEqual(texts(';;'), []);
});

test('meerregelige statements behouden hun regeleinden', () => {
  const sql = 'SELECT name,\n       unit_price\nFROM products\nWHERE unit_price > 100;\n\nSELECT 2;';
  assert.deepEqual(texts(sql), [
    'SELECT name,\n       unit_price\nFROM products\nWHERE unit_price > 100;',
    'SELECT 2;',
  ]);
});

test('statementAt: het statement waarin de cursor staat', () => {
  const text = 'SELECT 1;\n\nSELECT 2;\n\nSELECT 3';
  const statements = splitStatements(text);
  const at = (pos) => {
    const st = statementAt(statements, pos);
    return st && text.slice(st.from, st.to);
  };
  assert.equal(at(0), 'SELECT 1;');
  assert.equal(at(4), 'SELECT 1;');
  assert.equal(at(9), 'SELECT 1;');   // net na de puntkomma: nog statement 1
  assert.equal(at(10), 'SELECT 1;');  // op de lege regel erna: het vorige statement
  assert.equal(at(11), 'SELECT 2;');  // begin van statement 2
  assert.equal(at(15), 'SELECT 2;');
  assert.equal(at(22), 'SELECT 3');
  assert.equal(at(text.length), 'SELECT 3');
});

test('statementAt: vóór het eerste statement → het eerste; in leidend commentaar → dat statement', () => {
  const text = '\n\n-- intro\nSELECT 1;\n\n-- twee\nSELECT 2;';
  const statements = splitStatements(text);
  const at = (pos) => { const st = statementAt(statements, pos); return text.slice(st.from, st.to); };
  assert.equal(at(0), '-- intro\nSELECT 1;');
  assert.equal(at(text.indexOf('twee')), '-- twee\nSELECT 2;');
});

test('statementAt: zonder statements is er geen doel', () => {
  assert.equal(statementAt([], 0), null);
  assert.equal(statementAt(splitStatements('-- niets'), 3), null);
});
