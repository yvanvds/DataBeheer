// Unit-tests voor de autocomplete van de SQL-editor (issue #53): namen met
// hoofdletters — de hele AdventureWorks-databank — moeten gewoon aangevuld
// worden, niet tussen backticks (`Product`.`Name`). Het dialect zit in de
// gevendorde bundel (bron: scripts/codemirror-entry.mjs); deze test gebruikt
// precies het exemplaar dat book/_static/sql-editors.js ook gebruikt, zodat
// een vergeten `npm run build:editor` hier opvalt. Draaien met de ingebouwde
// testrunner van Node (geen extra pakketten):
//
//     node --test tests/sql-autocomplete.test.mjs
//
// tests/test_sql_editor.py roept dit ook aan vanuit pytest.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  EditorState, CompletionContext, sql, SQLiteCI,
} from '../book/_static/codemirror/codemirror.js';

// Zoals buildCatalog() in book/_static/sql-worker.js het schema doorgeeft:
// {tabel: [kolommen]}. Een greep uit adventureworks.db en webshop.db, plus een
// naam die aanhalingstekens écht nodig heeft.
const SCHEMA = {
  Product: ['ProductID', 'Name', 'ListPrice', 'ProductCategoryID', 'rowguid'],
  SalesOrderHeader: ['SalesOrderID', 'OrderDate', 'CustomerID'],
  products: ['product_id', 'name', 'prijs'],
  'Order Details': ['Qty'],
};

// De voorstellen die de editor op `pos` (einde van de tekst) zou tonen, als
// {label: apply}. `apply` is wat er werkelijk in de cel terechtkomt; is het
// undefined, dan wordt het label zelf ingevoegd — precies wat we willen.
async function completions(doc) {
  const state = EditorState.create({
    doc,
    extensions: [sql({ dialect: SQLiteCI, schema: SCHEMA, upperCaseKeywords: true })],
  });
  const pos = doc.length;
  const applies = {};
  for (const source of state.languageDataAt('autocomplete', pos)) {
    const result = await source(new CompletionContext(state, pos, true));
    for (const option of result ? result.options : []) applies[option.label] = option.apply;
  }
  return applies;
}

test('de bundel levert het dialect van de editor (anders: npm run build:editor)', () => {
  assert.ok(SQLiteCI, 'SQLiteCI ontbreekt in book/_static/codemirror/codemirror.js');
  assert.equal(SQLiteCI.spec.caseInsensitiveIdentifiers, true);
});

test('tabelnamen met hoofdletters worden aangevuld zonder aanhalingstekens', async () => {
  const applies = await completions('SELECT * FROM ');
  assert.equal(applies.Product, undefined);
  assert.equal(applies.SalesOrderHeader, undefined);
});

test('kolomnamen met hoofdletters worden aangevuld zonder aanhalingstekens', async () => {
  const applies = await completions('SELECT Product.');
  for (const column of SCHEMA.Product) assert.equal(applies[column], undefined, column);
});

test('een naam die aanhalingstekens nodig heeft, krijgt ze nog altijd', async () => {
  const applies = await completions('SELECT * FROM ');
  assert.equal(applies['Order Details'], '`Order Details`');
});

test('de webshopnamen in kleine letters blijven zoals ze waren', async () => {
  const tables = await completions('SELECT * FROM ');
  assert.equal(tables.products, undefined);
  const columns = await completions('SELECT products.');
  for (const column of SCHEMA.products) assert.equal(columns[column], undefined, column);
});

test('sleutelwoorden blijven in hoofdletters voorgesteld', async () => {
  const applies = await completions('SEL');
  assert.ok('SELECT' in applies, 'geen SELECT tussen de voorstellen');
  assert.ok(!('select' in applies), 'select in kleine letters tussen de voorstellen');
});
