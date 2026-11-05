// The CodeMirror 6 implementation of the editor contract (see ../../js/editor.js). Built by ./build.sh into codemirror.js.
import {EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection, Decoration, ViewPlugin} from "@codemirror/view"
import {EditorState, StateField, StateEffect} from "@codemirror/state"
import {defaultKeymap, history, historyKeymap, undo, redo} from "@codemirror/commands"
import {markdown} from "@codemirror/lang-markdown"
import {searchKeymap} from "@codemirror/search"
import {foldGutter, foldKeymap} from "@codemirror/language"
import Engine from "../../syntax/engine.js"

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
// The colours of the text come from the syntax table (../../syntax/syntaxes.json, read by syntax/engine.js): a mark with the class `syn-ROLE` on every
// run the table's rules colour, in the part of the text that is shown. The page's CSS gives each role its colour (the Mac app reads the same table).
const setSyntax = StateEffect.define()
const syntaxState = StateField.define({
  create: () => ({compiled: null, name: "markdown"}),
  update(value, tr) { for (const e of tr.effects) if (e.is(setSyntax)) return e.value; return value },
})
// What the whole text decides: where a front matter ends and which lines open or close a fence (parity). Recomputed when the text or the syntax changes.
function regionsOf(state) {
  const {compiled, name} = state.field(syntaxState)
  if (!compiled) return {front: 0, fences: []}
  const syntax = compiled.syntaxes[name], fm = syntax.frontMatter
  const front = fm ? Engine.frontMatterEnd(compiled, name, state.doc.sliceString(0, fm.open.length + fm.scan)) : 0
  const fences = []
  if (syntax.fence) { let at = 0; for (const line of state.doc.iterLines()) { if (at >= front && Engine.isFenceLine(compiled, name, line)) fences.push(at); at += line.length + 1 } }
  return {front, fences}
}
const regions = StateField.define({
  create: regionsOf,
  update(value, tr) { return tr.docChanged || tr.effects.some(e => e.is(setSyntax)) ? regionsOf(tr.state) : value },
})
function colourMarks(view) {
  const state = view.state, {compiled, name} = state.field(syntaxState)
  if (!compiled) return Decoration.none
  const syntax = compiled.syntaxes[name], {front, fences} = state.field(regions), doc = state.doc, marks = []
  const add = (from, to, role) => marks.push(Decoration.mark({class: "syn-" + role}).range(from, to))
  const body = (syntaxName, from, to) => { if (to > from) for (const [a, b, role] of Engine.paint(compiled, syntaxName, doc.sliceString(from, to))) add(from + a, from + b, role) }
  let lastTo = -1
  for (const range of view.visibleRanges) {
    const lo = Math.max(doc.lineAt(range.from).from, lastTo), hi = doc.lineAt(range.to).to
    if (hi <= lo) continue
    lastTo = hi
    let cursor = lo
    if (lo < front) { body(syntax.frontMatter.syntax, lo, Math.min(hi, front)); cursor = Math.min(hi, front) }
    let i = 0
    while (i < fences.length && fences[i] < cursor) i++              // the fences before the part shown decide whether it starts inside code
    let inCode = i % 2 === 1
    for (; i < fences.length && fences[i] < hi; i++) {
      if (inCode) add(cursor, fences[i], syntax.fences.role); else body(name, cursor, fences[i])
      const end = Math.min(doc.length, doc.lineAt(fences[i]).to + 1)
      add(fences[i], end, syntax.fences.role)
      inCode = !inCode; cursor = end
    }
    if (cursor < hi) { if (inCode) add(cursor, hi, syntax.fences.role); else body(name, cursor, hi) }
  }
  return Decoration.set(marks, true)
}
const colours = ViewPlugin.fromClass(class {
  constructor(view) { this.decorations = colourMarks(view) }
  update(u) { if (u.docChanged || u.viewportChanged || u.transactions.some(tr => tr.effects.some(e => e.is(setSyntax)))) this.decorations = colourMarks(u.view) }
}, {decorations: v => v.decorations})

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
        markdown(), syntaxState, regions, colours, look, marks,
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
    setSyntax(table, name) { view.dispatch({effects: setSyntax.of({compiled: table ? Engine.compile(table) : null, name: name || "markdown"})}) },
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
