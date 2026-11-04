// THE EDITOR CONTRACT. The page talks to an editor only through these members, so the editor behind them can change (the vendored
// CodeMirror 6 here, a plain textarea as the fallback, the native TextKit 2 editor in a Mac panel later) without touching the UI:
//   setText(text)  getText()  onChange(fn(text))  onSelection(fn({from,to,line,col}))  selection()  setSelection(from,to)
//   scrollTo(line)  decorate(ranges[{from,to}], cls)  replaceSelection(text, selectInserted)  undo()  redo()  lineCount()  focus()
(function () {
  "use strict";
  function plain(parent, initial) {
    const ta = document.createElement("textarea");
    ta.className = "plain"; ta.spellcheck = false; ta.value = initial || ""; parent.appendChild(ta);
    let changeFn = () => {}, selFn = () => {};
    const sel = () => { const a = ta.value.slice(0, ta.selectionStart).split("\n"); return { from: ta.selectionStart, to: ta.selectionEnd, line: a.length, col: a[a.length - 1].length + 1 }; };
    ta.addEventListener("input", () => { changeFn(ta.value); selFn(sel()); });
    for (const ev of ["keyup", "click", "select"]) ta.addEventListener(ev, () => selFn(sel()));
    return {
      kind: "textarea",
      setText(t) { ta.value = t; },
      getText: () => ta.value,
      onChange(fn) { changeFn = fn; }, onSelection(fn) { selFn = fn; },
      selection: sel,
      setSelection(a, b) { ta.focus(); ta.setSelectionRange(a, b == null ? a : b); selFn(sel()); },
      scrollTo(line) { const at = ta.value.split("\n").slice(0, line - 1).join("\n").length + (line > 1 ? 1 : 0); ta.setSelectionRange(at, at); ta.blur(); ta.focus(); ta.scrollTop = (line - 3) * 21; },
      decorate() { /* a textarea cannot mark a range: the preview side still highlights */ },
      replaceSelection(text, selectInserted) { ta.focus(); ta.setRangeText(text, ta.selectionStart, ta.selectionEnd, selectInserted ? "select" : "end"); ta.dispatchEvent(new Event("input")); },
      undo() { ta.focus(); document.execCommand("undo"); }, redo() { ta.focus(); document.execCommand("redo"); },
      lineCount: () => ta.value.split("\n").length,
      focus: () => ta.focus(),
    };
  }
  window.createEditor = function (kind, parent, initial) {
    parent.textContent = "";
    if (kind === "codemirror" && window.AppEditorCM) return window.AppEditorCM(parent, initial);
    return plain(parent, initial);
  };
})();
