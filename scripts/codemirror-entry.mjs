// Bron voor de gevendorde CodeMirror-bundel (issue #17).
// Bouwen: `npm run build:editor` → book/_static/codemirror/codemirror.js
// (ES-module, geminificeerd, ~zelfstandig — geen CDN's, werkt op GitHub Pages).
//
// We exporteren alleen wat book/_static/sql-editors.js echt gebruikt; zo
// blijft de bundel klein (belangrijk voor de trage leerling-laptops).

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
export { sql, SQLite } from "@codemirror/lang-sql";
export { tags } from "@lezer/highlight";
