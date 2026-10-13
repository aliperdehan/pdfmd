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
-- MathJax (v3.28.46). With MathJax (`pdfmd --install math:mathjax`) and node, pdfmd sets `pdfmd-mathjax` (its folder),
-- `pdfmd-mathjax-font` (the math font that goes with the body font) and `pdfmd-mathjax-node`, and MathJax is asked first,
-- in one node call (mathjax.cjs): its HTML and stylesheet replace the formula. What MathJax cannot read goes to KaTeX in a
-- second call when KaTeX is there (a NOTE says how many), and what neither reads stays plain text, with one WARN.
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

-- KaTeX sets its formulas at 1.21em; pdfmd gives the size that matches the body font's x-height (`pdfmd-katex-scale`,
-- in em of the body: x-height / 0.442) when it knows the font. Placed with the page's own style, so a --css file or
-- `document-css: false` keeps it: it is about the formulas, not the page.
local function katex_style()
  local scale = tonumber(variable("pdfmd-katex-scale") or "")
  if variable("pdfmd-katex") == nil or scale == nil then return "" end
  return string.format("<style>\nhtml .katex { font-size: %sem; }\n</style>\n", tostring(scale))
end

local function Meta(meta)
  local extra = katex_style()
  local css = not (variables.css or meta["document-css"] == false)
  if not css and extra == "" then return nil end
  local style = pandoc.MetaBlocks({pandoc.RawBlock("html", (css and TABLE_STYLE or "") .. (css and "\n" or "") .. extra)})
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

-- What WeasyPrint gets wrong in MathJax's CHTML. Every glyph is an inline-block `mjx-c` of no width and no content height,
-- whose font stack starts with a font of zero ascent and descent, so that its baseline is the box's bottom. WeasyPrint
-- takes the line's metrics from the font that draws the glyph (0.262em of ascent over descent in STIX Two Math), so each
-- box stood that much too tall above its baseline and everything MathJax stacks (an accent, a limit, a fraction's
-- denominator, a root, an \underset) sat 0.3em too far apart: a hat floated 3pt over its letter at 11pt. A negative top
-- margin takes the excess off (0.29em, the excess plus 0.03em, matches Chromium to 0.3pt on the 36 shapes tried in STIX Two
-- Math; the other MathJax fonts want their own excess plus 0.03em, and are not offered yet: a tall delimiter built from
-- pieces breaks in them). WeasyPrint draws no `clip-path`, which cuts a stretchy bar, arrow or brace to its width, so an
-- overflow does (an \overline ran past its letter); the bar of \underline sits inside a box of its own that wants 0.2em.
local MATHJAX_FIXES = "mjx-c { margin-top: -0.29em; }\n"
  .. "mjx-stretchy-h > mjx-ext { overflow: hidden; }\n"
  .. "mjx-under > mjx-mo > mjx-box { margin-top: -0.2em; }\n"

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

-- MathJax's answer for each formula and its stylesheet (one node call), or nil and why when it could not run
local function mathjax(items)
  local here = (PANDOC_SCRIPT_FILE or ""):gsub("[^/\\]*$", "")
  local request = pandoc.json.encode({dir = variable("pdfmd-mathjax"), font = variable("pdfmd-mathjax-font"), items = items})
  local ok, out = pcall(pandoc.pipe, variable("pdfmd-mathjax-node"), {here .. "mathjax.cjs"}, request)
  if not ok then return nil, tostring(out.output or out):gsub("%s+$", ""):sub(1, 300) end
  local decoded, result = pcall(pandoc.json.decode, out, false)
  if not decoded or type(result) ~= "table" or type(result.answers) ~= "table" or #result.answers ~= #items then
    return nil, "no answer from mathjax.cjs"
  end
  return result
end

-- the size that gives MathJax's formulas the body font's x-height, when the font is not the one made for the body
-- (`pdfmd-body-xheight` is set only then): the body's x-height over the math font's, kept within 0.85 and 1.4
local function mathjax_size_style(xheight)
  local body = tonumber(variable("pdfmd-body-xheight") or "")
  if body == nil or xheight == nil or xheight <= 0 then return "" end
  local scale = math.min(1.4, math.max(0.85, body / xheight))
  return string.format('mjx-container[jax="CHTML"] mjx-math { font-size: %d%%; }\n', math.floor(scale * 100 + 0.5))
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

-- `tex`: why, for the first formula that failed, as a message shows it
local function first_failure(el_text, why)
  return string.format("`%s`: %s", el_text:gsub("%s+", " "):sub(1, 60), why)
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
  local have_mathjax = variable("pdfmd-mathjax") ~= nil and variable("pdfmd-mathjax-node") ~= nil
  local have_katex = variable("pdfmd-katex") ~= nil and variable("pdfmd-katex-node") ~= nil
  local html, texts = {}, {}                 -- by formula: its HTML; its TeX and the error of the first to fail
  local engines, first = {}, {}
  local jax_css, jax_xheight, jax_reason, jax_failed = nil, nil, nil, 0
  -- MathJax first
  if have_mathjax then
    local result, reason = mathjax(items)
    if result then
      jax_css, jax_xheight = result.css, tonumber(result.xheight)
      for number, answer in ipairs(result.answers) do
        if answer.html then
          html[number], engines[number] = answer.html, "mathjax"
        else
          jax_failed = jax_failed + 1
          if first.mathjax == nil then first.mathjax = first_failure(items[number].tex, (answer.error or ""):gsub("%s+$", "")) end
        end
      end
    else
      jax_reason, jax_failed = reason, #items
    end
  end
  -- KaTeX takes the rest
  local katex_failed, katex_reason = 0, nil
  if have_katex then
    local rest, number_of = {}, {}
    for number, item in ipairs(items) do
      if html[number] == nil then rest[#rest + 1] = item; number_of[#rest] = number end
    end
    if #rest > 0 then
      local answers, reason = katex(rest)
      if answers then
        for position, answer in ipairs(answers) do
          if answer.html then
            html[number_of[position]], engines[number_of[position]] = answer.html, "katex"
          else
            katex_failed = katex_failed + 1
            if first.katex == nil then
              -- KaTeX underlines the place of the error with combining low lines
              local why = (answer.error or ""):gsub("\204\178", ""):gsub("^KaTeX parse error: ", "")
              first.katex = first_failure(rest[position].tex, why:gsub(" at position %d+:.*$", ""))
            end
          end
        end
      else
        katex_reason, katex_failed = reason, #rest
      end
    end
  end
  -- the formulas on the page (a formula that comes twice counts twice): all, those MathJax did not typeset, those nobody did
  local total, jax_miss, left, used_mathjax, used_katex = 0, 0, 0, false, false
  doc = doc:walk({Math = function(el)
    total = total + 1
    local number = index[key(el)]
    if engines[number] ~= "mathjax" then jax_miss = jax_miss + 1 end
    if html[number] then
      if engines[number] == "mathjax" then used_mathjax = true else used_katex = true end
      return pandoc.RawInline("html", html[number])
    end
    left = left + 1
    return plain(el)
  end})
  local function formulas(n) return n == 1 and "formula" or "formulas" end
  -- what is said: once, and only what happened
  if have_mathjax and jax_reason then
    io.stderr:write(string.format("WARN  weasyprint: MathJax could not run (%s)%s\n", jax_reason,
      have_katex and "; KaTeX typesets the formulas" or "; the formulas are printed as text"))
  elseif have_mathjax and have_katex and jax_miss > left then
    io.stderr:write(string.format("NOTE  weasyprint: MathJax could not typeset %d of %d formulas, KaTeX did%s; the first: %s\n",
      jax_miss, total, left > 0 and string.format(" (not %d)", left) or "", first.mathjax or "?"))
  end
  if left > 0 then
    if have_katex and katex_reason then
      io.stderr:write(string.format("WARN  weasyprint: KaTeX could not run (%s); %d %s %s printed as text\n",
        katex_reason, left, formulas(left), left == 1 and "is" or "are"))
    elseif have_katex then
      io.stderr:write(string.format("WARN  weasyprint: %s could not typeset %d of %d formulas, printed as text; the first: %s\n",
        have_mathjax and "MathJax and KaTeX" or "KaTeX", left, total, first.katex or first.mathjax or "?"))
    elseif have_mathjax and not jax_reason then
      io.stderr:write(string.format("WARN  weasyprint: MathJax could not typeset %d of %d formulas, printed as text; the first: %s\n",
        left, total, first.mathjax or "?"))
    end
  end
  local style = ""
  if used_mathjax then style = style .. "<style>\n" .. (jax_css or "") .. "\n" .. MATHJAX_FIXES .. mathjax_size_style(jax_xheight) .. "</style>" end
  if used_katex then
    local url = variable("pdfmd-katex-url")
    style = style .. '<link rel="stylesheet" href="' .. url .. '/katex.min.css">\n<style>\n' .. KATEX_FIXES .. "</style>"
  end
  if style ~= "" then doc.blocks:insert(1, pandoc.RawBlock("html", style)) end
  return doc
end

local function Pandoc(doc)
  if (variable("pdfmd-mathjax") and variable("pdfmd-mathjax-node"))
      or (variable("pdfmd-katex") and variable("pdfmd-katex-node")) then return typeset(doc) end
  local count = 0
  doc:walk({Math = function() count = count + 1 end})
  if count > 0 then
    io.stderr:write(string.format("WARN  weasyprint: WeasyPrint does not typeset math; %d formula%s %s printed as text "
      .. "(simple ones in Unicode, the others as TeX). Typst or a LaTeX engine typesets %s: -e typst; or "
      .. "`pdfmd --install math:mathjax` (or `pdfmd --install math:katex`) for WeasyPrint itself\n", count,
      count == 1 and "" or "s", count == 1 and "is" or "are", count == 1 and "it" or "them"))
  end
  return nil
end

return {{Meta = Meta, Pandoc = Pandoc}}
