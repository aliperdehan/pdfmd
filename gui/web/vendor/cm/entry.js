// The CodeMirror 6 implementation of the editor contract (see ../../js/editor.js). Built by ./build.sh into codemirror.js.
import {EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, Decoration} from "@codemirror/view"
import {EditorState, StateField, StateEffect} from "@codemirror/state"
import {defaultKeymap, history, historyKeymap, undo, redo} from "@codemirror/commands"
import {markdown} from "@codemirror/lang-markdown"
import {searchKeymap} from "@codemirror/search"
import {syntaxHighlighting, HighlightStyle, foldGutter, foldKeymap} from "@codemirror/language"
import {tags as t} from "@lezer/highlight"

// colours come from the page's CSS variables, so one theme (light and dark) serves the whole window
const look = EditorView.theme({
  "&": {height: "100%", color: "var(--ed-fg)", backgroundColor: "var(--ed-bg)"},
  ".cm-scroller": {fontFamily: "var(--mono)", fontSize: "var(--ed-size)", lineHeight: "1.55"},
  ".cm-content": {caretColor: "var(--ed-fg)", padding: "10px 0"},
  ".cm-gutters": {backgroundColor: "var(--ed-bg)", color: "var(--ed-dim)", border: "none"},
  ".cm-activeLine": {backgroundColor: "var(--ed-line)"},
  ".cm-activeLineGutter": {backgroundColor: "var(--ed-line)", color: "var(--ed-fg)"},
  "&.cm-focused": {outline: "none"},
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {backgroundColor: "var(--ed-sel) !important"},
  ".cm-cursor": {borderLeftColor: "var(--ed-fg)"},
  ".cm-mirror": {backgroundColor: "var(--ed-mirror)", borderRadius: "2px"},
})
const colours = HighlightStyle.define([
  {tag: t.heading, color: "var(--ed-head)", fontWeight: "600"},
  {tag: t.strong, fontWeight: "700"},
  {tag: t.emphasis, fontStyle: "italic"},
  {tag: [t.link, t.url], color: "var(--ed-link)"},
  {tag: t.monospace, color: "var(--ed-code)"},
  {tag: t.quote, color: "var(--ed-dim)"},
  {tag: [t.processingInstruction, t.meta, t.contentSeparator], color: "var(--ed-dim)"},
  {tag: t.comment, color: "var(--ed-dim)", fontStyle: "italic"},
])

// decorate(ranges, cls): marks ranges with a class (the source side of "this part of the source is that part of the preview")
const setMarks = StateEffect.define()
const marks = StateField.define({
  create: () => Decoration.none,
  update(value, tr) {
    value = value.map(tr.changes)
    for (const e of tr.effects) if (e.is(setMarks)) {
      const doc = tr.state.doc.length
      value = Decoration.set(e.value.ranges.filter(r => r.from < r.to && r.to <= doc).map(r => Decoration.mark({class: e.value.cls}).range(r.from, r.to)), true)
    }
    return value
  },
  provide: f => EditorView.decorations.from(f),
})

window.AppEditorCM = function (parent, initial) {
  let changeFn = () => {}, selectionFn = () => {}, silent = false
  const view = new EditorView({
    parent,
    state: EditorState.create({
      doc: initial || "",
      extensions: [
        lineNumbers(), foldGutter(), history(), drawSelection(), highlightActiveLine(), EditorView.lineWrapping,
        markdown(), syntaxHighlighting(colours), look, marks,
        keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap, ...foldKeymap]),
        EditorView.updateListener.of(u => {
          if (u.docChanged && !silent) changeFn(u.state.doc.toString())
          if (u.selectionSet || u.docChanged) selectionFn(selection())
        }),
      ],
    }),
  })
  function selection() {
    const s = view.state.selection.main, line = view.state.doc.lineAt(s.head)
    return {from: s.from, to: s.to, line: line.number, col: s.head - line.from + 1}
  }
  return {
    kind: "codemirror",
    setText(text) { silent = true; view.dispatch({changes: {from: 0, to: view.state.doc.length, insert: text}}); silent = false },
    getText: () => view.state.doc.toString(),
    onChange(fn) { changeFn = fn },
    onSelection(fn) { selectionFn = fn },
    selection,
    setSelection(from, to) { view.dispatch({selection: {anchor: from, head: to == null ? from : to}, scrollIntoView: true}) },
    scrollTo(line) { const l = view.state.doc.line(Math.max(1, Math.min(line, view.state.doc.lines))); view.dispatch({selection: {anchor: l.from}, effects: EditorView.scrollIntoView(l.from, {y: "start", yMargin: 20})}) },
    decorate(ranges, cls) { view.dispatch({effects: setMarks.of({ranges, cls: cls || "cm-mirror"})}) },
    replaceSelection(text, selectInserted) {
      const s = view.state.selection.main
      view.dispatch({changes: {from: s.from, to: s.to, insert: text}, selection: selectInserted ? {anchor: s.from, head: s.from + text.length} : {anchor: s.from + text.length}, scrollIntoView: true})
      view.focus()
    },
    replaceRange(from, to, text, selFrom, selTo) {
      const a = selFrom == null ? from + text.length : selFrom
      view.dispatch({changes: {from, to, insert: text}, selection: {anchor: a, head: selTo == null ? a : selTo}, scrollIntoView: true})
      view.focus()
    },
    undo: () => undo(view), redo: () => redo(view),
    lineCount: () => view.state.doc.lines,
    focus: () => view.focus(),
  }
}
