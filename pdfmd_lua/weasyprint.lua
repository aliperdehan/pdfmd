-- pdfmd: math in a PDF made by WeasyPrint (v3.27.12). WeasyPrint does not draw MathML: Pandoc's default HTML math printed
-- each formula twice as flat text (`x2+abx^2 + \frac{a}{b}`). pdfmd gives Pandoc --math-method=plain for WeasyPrint
-- (simple formulas in Unicode, `αᵢ ≤ β`; the others as their TeX), and this filter says so once, with the way to
-- typeset them.
--
-- KaTeX (v3.28.11). With KaTeX (`pdfmd --install math:katex`) and node, pdfmd sets the variables `pdfmd-katex` (the
-- KaTeX folder), `pdfmd-katex-url` (the same as a file: URL) and `pdfmd-katex-node`, and this filter typesets the math:
-- every formula goes to KaTeX in one node call (katex.cjs, beside this file), and its HTML replaces the formula; the
-- page links KaTeX's stylesheet and fonts. A formula KaTeX cannot read stays plain text, with one WARN for all of them.
-- Pandoc's math stays plain, so a formula this filter does not reach prints as text, never as MathML.
--
-- Tables (v3.28.3). Pandoc's own page style is for a screen: a table is a full-width block that scrolls sideways, and
-- a word may break anywhere. WeasyPrint set the caption of a narrow table a syllable a line. While that style is in
-- (no --css, `document-css` not false), a style in `header-includes` makes a table a table again, centred as LaTeX
-- sets it, with its caption centred and broken between words. WeasyPrint has no max-content width, so a caption is as
-- wide as its table; a table is at least 4in wide (LaTeX's caption width) and wider as its text needs. A numbered
-- equation (the LaTeX filter's three-cell table) spans the line, its number at the margin, without a table's rules.
-- An --include-in-header replaces the style, as it replaces the document's own header-includes.

if not FORMAT:match("^html") then return {} end

local variables = PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.variables or {}

-- a template variable pdfmd set (-V), as a string
local function variable(name)
  local value = variables[name]
  return value ~= nil and tostring(value) or nil
end

local TABLE_STYLE = "<style>\n"
  .. "table { display: table; width: auto; min-width: 4in; overflow: visible; margin-left: auto; margin-right: auto; }\n"
  .. "table caption { overflow-wrap: normal; text-align: center; }\n"
  .. 'table[data-custom-style="PdfmdEquation"] { width: 100%; }\n'
  .. 'table[data-custom-style="PdfmdEquation"] tbody { border: none; }\n'
  .. "</style>"

local function Meta(meta)
  if variables.css or meta["document-css"] == false then return nil end
  local style = pandoc.MetaBlocks({pandoc.RawBlock("html", TABLE_STYLE)})
  local includes = meta["header-includes"]
  if includes == nil then
    meta["header-includes"] = pandoc.MetaList({style})
  elseif pandoc.utils.type(includes) == "List" then
    includes:insert(style)
    meta["header-includes"] = includes
  else
    meta["header-includes"] = pandoc.MetaList({includes, style})
  end
  return meta
end

-- what WeasyPrint gets wrong in KaTeX's own stylesheet: a column (\neq's slash over its "=") laid out as a flexbox
-- lost the "=", and \vec's arrow, an absolutely placed picture in a box of no width, was not drawn
local KATEX_FIXES = ".katex .katex-vbox { display: inline-block; }\n.katex .katex-overlay svg { position: static; }\n"

local plain_math = pandoc.WriterOptions({html_math_method = "plain"})

-- a formula as Pandoc's plain math writes it (Unicode where it can, else its TeX)
local function plain(el)
  local html
  local function attempt() html = pandoc.write(pandoc.Pandoc({pandoc.Plain({el})}), "html", plain_math) end
  if pandoc.log and pandoc.log.silence then pandoc.log.silence(attempt) else attempt() end
  return pandoc.RawInline("html", (html:gsub("%s+$", "")))
end

-- KaTeX's HTML for each formula (one node call), or nil and why when it could not run
local function katex(items)
  local here = (PANDOC_SCRIPT_FILE or ""):gsub("[^/\\]*$", "")
  local request = pandoc.json.encode({dir = variable("pdfmd-katex"), items = items})
  local ok, out = pcall(pandoc.pipe, variable("pdfmd-katex-node"), {here .. "katex.cjs"}, request)
  if not ok then return nil, tostring(out.output or out):gsub("%s+$", ""):sub(1, 300) end
  local decoded, answers = pcall(pandoc.json.decode, out, false)
  if not decoded or type(answers) ~= "table" or #answers ~= #items then return nil, "no answer from katex.cjs" end
  return answers
end

-- Pandoc writes the page's title (the PDF's Title) and its authors' names from the title and the authors as plain
-- text, in which raw HTML is nothing: a formula there, once typeset, vanished from them ("Energy  here"). They are set
-- first, from the formula's TeX, as Pandoc sets them without this filter.
local function keep_plain_names(meta)
  local function has_math(value)
    local found = false
    pandoc.Pandoc({}, pandoc.Meta({value = value})):walk({Math = function() found = true end})
    return found
  end
  if meta.title ~= nil and meta.pagetitle == nil and has_math(meta.title) then
    meta.pagetitle = pandoc.MetaString(pandoc.utils.stringify(meta.title))
  end
  if meta.author ~= nil and meta["author-meta"] == nil and has_math(meta.author) then
    local names = {}
    local authors = pandoc.utils.type(meta.author) == "List" and meta.author or {meta.author}
    for _, author in ipairs(authors) do names[#names + 1] = pandoc.MetaString(pandoc.utils.stringify(author)) end
    meta["author-meta"] = pandoc.MetaList(names)
  end
  return meta
end

local function typeset(doc)
  doc.meta = keep_plain_names(doc.meta)
  local items, index = {}, {}
  local function key(el) return el.mathtype .. "\0" .. el.text end
  doc:walk({Math = function(el)
    if index[key(el)] == nil then
      items[#items + 1] = {tex = el.text, display = el.mathtype == "DisplayMath"}
      index[key(el)] = #items
    end
  end})
  if #items == 0 then return nil end
  local answers, reason = katex(items)
  local count, failed, first = 0, 0, nil
  doc = doc:walk({Math = function(el)
    count = count + 1
    local answer = answers and answers[index[key(el)]]
    if answer and answer.html then return pandoc.RawInline("html", answer.html) end
    failed = failed + 1
    if answer and first == nil then
      -- KaTeX underlines the place of the error with combining low lines
      local why = (answer.error or ""):gsub("\204\178", ""):gsub("^KaTeX parse error: ", "")
      first = string.format("`%s`: %s", el.text:gsub("%s+", " "):sub(1, 60), why:gsub(" at position %d+:.*$", ""))
    end
    return plain(el)
  end})
  if not answers then
    io.stderr:write(string.format("WARN  weasyprint: KaTeX could not run (%s); %d formula%s %s printed as text\n",
      reason, count, count == 1 and "" or "s", count == 1 and "is" or "are"))
  elseif failed > 0 then
    io.stderr:write(string.format("WARN  weasyprint: KaTeX could not typeset %d of %d formulas, printed as text; the "
      .. "first: %s\n", failed, count, first or "?"))
  end
  if failed < count then
    local url = variable("pdfmd-katex-url")
    doc.blocks:insert(1, pandoc.RawBlock("html", '<link rel="stylesheet" href="' .. url .. '/katex.min.css">\n'
      .. "<style>\n" .. KATEX_FIXES .. "</style>"))
  end
  return doc
end

local function Pandoc(doc)
  if variable("pdfmd-katex") and variable("pdfmd-katex-node") then return typeset(doc) end
  local count = 0
  doc:walk({Math = function() count = count + 1 end})
  if count > 0 then
    io.stderr:write(string.format("WARN  weasyprint: WeasyPrint does not typeset math; %d formula%s %s printed as text "
      .. "(simple ones in Unicode, the others as TeX). Typst or a LaTeX engine typesets %s: -e typst; or "
      .. "`pdfmd --install math:katex` for WeasyPrint itself\n", count,
      count == 1 and "" or "s", count == 1 and "is" or "are", count == 1 and "it" or "them"))
  end
  return nil
end

return {{Meta = Meta, Pandoc = Pandoc}}
