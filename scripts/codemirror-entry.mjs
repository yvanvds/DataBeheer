// Bron voor de gevendorde CodeMirror-bundel (issue #17).
// Bouwen: `npm run build:editor` → book/_static/codemirror/codemirror.js
// (ES-module, geminificeerd, ~zelfstandig — geen CDN's, werkt op GitHub Pages).
//
// We exporteren alleen wat book/_static/sql-editors.js echt gebruikt; zo
// blijft de bundel klein (belangrijk voor de trage leerling-laptops). Enige
// uitzondering: CompletionContext, dat tests/sql-autocomplete.test.mjs nodig
// heeft om de completionbron van deze bundel aan te roepen (issue #53).

import { SQLDialect, SQLite } from "@codemirror/lang-sql";

export { EditorState, Compartment, StateField } from "@codemirror/state";
export {
  EditorView,
  Decoration,
  keymap,
  lineNumbers,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
} from "@codemirror/view";
export { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
export {
  indentOnInput,
  bracketMatching,
  syntaxHighlighting,
  HighlightStyle,
} from "@codemirror/language";
export {
  autocompletion,
  completionKeymap,
  closeBrackets,
  closeBracketsKeymap,
} from "@codemirror/autocomplete";
export { CompletionContext } from "@codemirror/autocomplete";  // alleen voor de tests
export { sql } from "@codemirror/lang-sql";
export { tags } from "@lezer/highlight";

// Het SQL-dialect van de editor (issue #53).
//
// lang-sql zet een naam tussen aanhalingstekens zodra die niet aan
// /^[a-z_][a-z_\d]*$/ voldoet. Dat is standaard hoofdlettergevoelig, dus
// autocomplete vulde elke AdventureWorks-naam aan als `Product`.`Name`
// (backtick: het eerste teken van identifierQuotes van SQLite) — SQL die niet
// in de cursus staat en op AZERTY nauwelijks te typen is.
//
// Met caseInsensitiveIdentifiers komen Product, ProductID en Name er zonder
// quotes in, terwijl een naam die ze écht nodig heeft (bv. "Order Details")
// ze wel behoudt. De rest van de spec blijft die van SQLite.
export const SQLiteCI = SQLDialect.define({
  ...SQLite.spec,
  caseInsensitiveIdentifiers: true,
});
