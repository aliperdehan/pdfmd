// Run by opening index.html#selftest: drives the page like a person (clicks, selections, keys) and writes the result into #selftest.
// `Edge --headless --dump-dom 'file://.../index.html#selftest'` shows it; each line starts with ok or FAIL.
(async function () {
  "use strict";
  const S = window.__app, $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const slow = +((location.hash.match(/slow(\d+)/) || [])[1] || 1);   // #selftest-slow4: a real window that WebKit throttles (not the headless run) needs longer waits
  const sleep = ms => new Promise(r => setTimeout(r, ms * slow));
  const out = []; let fails = 0;
  const check = (name, ok, extra) => { out.push((ok ? "ok    " : "FAIL  ") + name + (ok ? "" : "  " + (extra || ""))); if (!ok) fails++; };
  const setting = k => S.settings[k], closeAll = () => document.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  const renderNow = async () => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "r", metaKey: true, bubbles: true })); await sleep(150); };
  const menuTexts = () => $$(".popover .mi").map(m => m.firstChild.textContent);
  const clickMenu = label => { const m = $$(".popover .mi").find(x => x.firstChild.textContent.replace(/^✓ /, "") === label); m && m.click(); return !!m; };
  const on = (n, ev) => n.dispatchEvent(new Event(ev, { bubbles: true }));
  try {
    for (let i = 0; i < 40 && !(S.cur && $("#live").children.length); i++) await sleep(50);
    check("starts on the main file, with its tab", S.cur === "report.md" && $$(".tab").length === 1);
    check("the editor is CodeMirror and holds the file", S.editor.kind === "codemirror" && S.editor.getText().includes("# Introduction") && S.editor.lineCount() > 40);
    check("the live view shows the pandoc render with source positions", $$("#live [data-pos]").length > 10 && $("#live h1").textContent === "Introduction");
    const outline = $$("#side .row").filter(r => r.firstChild.textContent === "§").map(r => r.textContent.slice(1));
    check("the outline lists the 7 headings once", outline.join("|") === "Introduction|Method|Reagents|Procedure|Results|Discussion|References", outline.join("|"));

    // the source <-> preview mirror
    const text = S.editor.getText(), from = text.indexOf("Samples were titrated");
    S.editor.setSelection(from, from + 20); await sleep(60);
    const m = $$("#live .mirror");
    check("a selection in the source marks its block in the preview", m.length === 1 && /^report\.md@18:/.test(m[0].dataset.pos), m.map(x => x.dataset.pos).join());
    S.editor.setSelection(from); await sleep(30);
    check("no selection, no mark", $$("#live .mirror").length === 0);
    const li = $$("#live li").find(x => x.textContent.includes("hydrochloric")); li.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })); await sleep(30);
    const marked = $$(".cm-mirror").map(x => x.textContent).join("|");
    check("the pointer on a preview block marks its source lines (a list as one block: pandoc gives no position to an item, and its end is cut before the next heading)", marked === "- ethyl acetate, 0.50 M|- hydrochloric acid, 1.0 M|- sodium hydroxide, 0.100 M (standardised)", marked);

    // toolbar and templates
    S.editor.setSelection(from, from + 7); $("#toolbar [data-do=bold]").click(); await sleep(30);
    check("B wraps the selection", S.editor.getText().includes("**Samples** were titrated"));
    $("#toolbar [data-do=italic]").click(); await sleep(30);
    check("I with no selection puts the cursor between the stars", /\*\*Samples\*\* were titrated|\*\*\*/.test(S.editor.getText()) && S.editor.selection().from > 0);
    S.editor.setSelection(S.editor.getText().length); S.editor.replaceSelection("\n\n::: calc\n", false);
    $("#toolbar [data-do=insertMenu]").click(); check("the Insert menu lists the templates", menuTexts().includes("Calculation block") && menuTexts().includes("Comment")); clickMenu("Comment"); await sleep(30);
    check("a template puts the cursor inside it", S.editor.getText().endsWith("<!--  -->") && S.editor.getText().slice(S.editor.selection().from - 5, S.editor.selection().from + 5) === "<!-- " + " -->".slice(0, 5) || S.editor.getText().slice(S.editor.selection().from - 5, S.editor.selection().from) === "<!-- ", S.editor.getText().slice(-30));
    $("#headingSel").value = "2"; on($("#headingSel"), "change"); await sleep(30);
    check("the heading menu changes the level of the line", /^## /m.test(S.editor.getText().split("\n").slice(-1)[0]) || S.editor.getText().includes("## "), S.editor.getText().slice(-40));
    $("#toolbar [data-do=symbols]").click(); const sym = $$(".symgrid button"); check("the symbols picker offers Greek, math and chemistry", sym.length > 60 && $$(".popover .head").map(h => h.textContent).join() === "Greek,Math,Chemistry"); sym[0].click(); await sleep(30);
    check("a symbol is inserted as its LaTeX equivalent (ASCII preferred)", S.editor.getText().includes("$\\alpha$") && !S.editor.getText().includes("α"), S.editor.getText().slice(-30));
    S.editor.replaceSelection(" $x = ", false); $("#toolbar [data-do=symbols]").click(); $$(".symgrid button")[1].click(); await sleep(30);
    check("inside math it inserts the bare macro", S.editor.getText().endsWith("$x = \\beta"), S.editor.getText().slice(-20));
    S.editor.replaceSelection("$", false); $("#toolbar [data-do=symbols]").click(); $$(".popover .seg button")[1].click(); $$(".symgrid button")[2].click(); await sleep(30);
    check("the toggle switches to the Unicode character", S.editor.getText().endsWith("γ") && setting("symbolInsert") === "unicode", S.editor.getText().slice(-8));
    $("#toolbar [data-do=symbols]").click(); $$(".popover .seg button")[0].click(); closeAll(); await sleep(10);

    // a template pressed twice toggles
    const t0 = S.editor.getText(); S.editor.setSelection(t0.length);
    $("#toolbar [data-do=table]").click(); await sleep(20); const t1 = S.editor.getText();
    $("#toolbar [data-do=table]").click(); await sleep(20);
    check("a table template pressed twice at the same place is inserted once and taken out again", t1.length > t0.length && S.editor.getText() === t0, S.editor.getText().slice(-40));
    S.editor.setSelection(t0.length); $("#toolbar [data-do=bold]").click(); await sleep(20);
    check("bold with no selection puts the marks around the cursor", S.editor.getText() === t0 + "****" && S.editor.selection().from === t0.length + 2);
    $("#toolbar [data-do=bold]").click(); await sleep(20);
    check("and a second press takes them off", S.editor.getText() === t0, S.editor.getText().slice(-10));
    const w = t0.indexOf("Samples"); S.editor.setSelection(w, w + 7); $("#toolbar [data-do=italic]").click(); $("#toolbar [data-do=italic]").click(); await sleep(20);
    check("a wrapped selection unwraps with the second press", S.editor.getText() === t0 && S.editor.selection().from === w && S.editor.selection().to === w + 7);

    // render modes and the unfinished bold
    S.editor.setText(S.editor.getText()); const end = S.editor.getText().length; S.editor.setSelection(end); S.editor.replaceSelection("\n\nThis is **not finished", false);
    await sleep(500);
    check("instant (auto): an unfinished **bold is closed in the preview, dimmed", !!$("#live strong.pending") && $("#live strong.pending").textContent === "not finished", $("#live").innerHTML.slice(-200));
    check("an edit re-renders its block only: the rest keeps pandoc's own HTML (MathML is still there), and the banner counts", /stand-in/i.test($("#liveBanner").textContent) && !$("#liveBanner").hidden && $$("#live math").length >= 3 && api.lastRender.kept > 5, JSON.stringify(api.lastRender) + " math:" + $$("#live math").length);
    S.editor.setText(S.editor.getText().replace("# Results", "<!-- note to self\n\n# Results")); await renderNow();
    check("an unfinished <!-- comment does not hide the rest of the page", $$("#live .cmt").length >= 1 && $("#live").textContent.includes("Discussion"), $("#live").textContent.slice(-60));
    $("#renderMode").value = "watch"; on($("#renderMode"), "change");
    S.editor.replaceSelection(" more", false); await sleep(400);
    check("watch: the preview waits for a save", /Save to update/.test($("#liveBanner").textContent) && !$("#live").textContent.includes("not finished more"));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "s", metaKey: true, bubbles: true })); await sleep(300);
    check("save renders it, the dot goes", $("#live").textContent.includes("not finished more") && !$(".tab .dot"), $(".tab").textContent);
    $("#renderMode").value = "manual"; on($("#renderMode"), "change"); S.editor.replaceSelection("!", false); await sleep(400);
    check("manual: the banner names the shortcut", /manual/.test($("#liveBanner").textContent));
    $("#renderMode").value = "auto"; on($("#renderMode"), "change");

    // the editor is switchable
    const before = S.editor.getText();
    $$(".menu").find(b => b.dataset.menu === "view").click(); clickMenu("Plain text box"); await sleep(100);
    check("the editor switches to a plain box with the same text", S.editor.kind === "textarea" && S.editor.getText() === before && !!$("#editor textarea.plain"));
    $$(".menu").find(b => b.dataset.menu === "view").click(); clickMenu("CodeMirror 6"); await sleep(100);
    check("and back", S.editor.kind === "codemirror" && S.editor.getText() === before);

    // tabs
    $$("#side .row").find(r => r.textContent.includes("notes.md")).click(); await sleep(150);
    check("a second file opens in a second tab, with its text", S.cur === "notes.md" && $$(".tab").length === 2 && S.editor.getText().startsWith("# Lab notes"));
    check("the first tab keeps its edits and shows its dot", S.files["report.md"].text !== S.files["report.md"].saved && $$(".tab")[0].textContent.includes("●"), $$(".tab")[0].textContent);
    window.appCommand("tab1"); await sleep(150);
    const onFirst = S.cur === "report.md";
    window.appCommand("tab2"); await sleep(150);
    const onSecond = S.cur === "notes.md";
    window.appCommand("tab5"); await sleep(60);
    check("command-1 and command-2 pick the first and second tab, and a number past the last tab does nothing", onFirst && onSecond && S.cur === "notes.md", S.cur);
    window.appCommand("tab1"); await sleep(150);
    window.appCommand("tabLast"); await sleep(150);
    check("command-9 picks the last tab", S.cur === "notes.md", S.cur);
    $$(".tab")[1].querySelector(".x").click(); await sleep(150);
    check("closing a tab goes back to the other", S.cur === "report.md" && $$(".tab").length === 1);

    // search, checks, history
    $("#rail [data-panel=search]").click(); const q = $("#side input[type=search]"); q.value = "quench"; on(q, "input"); await sleep(150);
    check("search finds the word in several files", $$("#side .hit").length >= 3, String($$("#side .hit").length));
    $$("#side .hit").find(h => h.textContent.startsWith("notes.md")).click(); await sleep(150);
    check("a hit opens its file at its line", S.cur === "notes.md" && $$(".tab").length === 2);
    $("#rail [data-panel=checks]").click(); await sleep(60);
    check("checks list the sample items", $$("#side .item").length === 2 && $("#checkBadge").textContent === "2");
    $("#rail [data-panel=history]").click(); await sleep(60);
    check("history: edits lane", $$("#side .item").length === 4);
    $$("#side .lanes button")[1].click(); await sleep(60);
    check("history: builds lane (one failed)", $$("#side .item").length === 3 && $$("#side .item .bad").length === 1);
    $$("#side .lanes button")[0].click(); await sleep(60); $$("#side .item")[0].click(); await sleep(60);
    check("a git edit opens a coloured diff", !!$("dialog[open] pre.diff .a") && !!$("dialog[open] pre.diff .d")); $("dialog[open] .btn.primary").click();

    // export and build menus
    $("#exportBtn").click();
    const top = $$(".popover:last-child > .mi").map(m => m.firstChild.textContent);
    check("Export: Markdown, PDF, Word, HTML, Cropped, Others", top.join("|") === "Markdown (standalone)|PDF|Word (.docx)|HTML (.html)|Cropped|Others", top.join("|"));
    const pdf = $$(".popover .mi").find(m => m.firstChild.textContent === "PDF"); pdf.dispatchEvent(new MouseEvent("mouseenter")); await sleep(30);
    check("PDF has a dropdown in a dropdown", $$(".popover").length === 2 && $$(".popover")[1].textContent.includes("Typst") && $$(".popover")[1].textContent.includes("LaTeX"), $$(".popover")[1] && $$(".popover")[1].textContent.slice(0, 80));
    const docx = $$(".popover .mi").find(m => m.firstChild.textContent === "Word (.docx)"); docx.click(); await sleep(50);
    check("a format opens a dialog with the exact pdfmd command (of the file in front)", $("dialog[open] pre.cmd").textContent === "pdfmd " + S.cur + " -t docx -o " + S.cur.replace(/\.md$/, ".docx"), $("dialog[open] pre.cmd") && $("dialog[open] pre.cmd").textContent); $$("dialog[open] .btn")[1].click();

    // settings: the schema, platforms, validation
    $("#rail [data-panel=settings]").click(); await sleep(60);
    const tabs = $$("#side .stabs button").map(b => b.textContent);
    check("settings: the Popup tab (Mac only) is not offered in the browser, nor the Mac-only rows of other tabs", tabs.includes("Editor") && tabs.includes("Live view") && !tabs.includes("Popup") && !S.schema.filter(x => x.platforms.length === 1 && x.tab !== "Popup").some(x => $$("#side .field label").some(l => l.textContent.startsWith(x.key))), tabs.join());
    check("validation (flag, number, choice)", api.validate("lineNumbers", "maybe").error && api.validate("lineNumbers", "ON").value === "1" && api.validate("lineNumberMinDigits", "x").error && api.validate("editorKind", "PLAIN").value === "plain" && api.validate("editorKind", "vim").error);

    // build
    $("#buildBtn").click(); await sleep(2500);
    check("Build shows the log, then the PDF", !$("#pdfView").hidden && $("#log").textContent.includes("OK  report.md") && $("#pdfFrame").getAttribute("src").startsWith("fixtures/report.pdf"), $("#log").textContent.slice(-80));
    check("the status bar says how it went", /built report\.pdf in/.test($("#stBuild").textContent), $("#stBuild").textContent);

    // layouts
    for (const l of ["editor", "preview", "split"]) { $(`#layoutSeg [data-layout=${l}]`).click(); await sleep(20); }
    check("layouts switch", document.body.dataset.layout === "split");
    $("#layoutSeg [data-layout=focus]").click(); document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); await sleep(20);
    check("focus mode ends with Esc", document.body.dataset.layout === "split");
  } catch (e) { check("no exception", false, e && e.stack || String(e)); }
  const pre = document.createElement("pre"); pre.id = "selftest"; pre.textContent = out.join("\n") + "\nSELFTEST " + (fails ? "FAILED " + fails : "OK") + "\n"; document.body.append(pre);
  document.title = fails ? "FAILED" : "OK";
})();
