-- pdfmd: math in a PDF made by WeasyPrint (v3.27.12). WeasyPrint does not draw MathML: Pandoc's default HTML math printed
-- each formula twice as flat text (`x2+abx^2 + \frac{a}{b}`). pdfmd gives Pandoc --math-method=plain for WeasyPrint
-- (simple formulas in Unicode, `αᵢ ≤ β`; the others as their TeX), and this filter says so once, with the way to
-- typeset them. It changes nothing in the document's text.
--
-- Tables (v3.28.3). Pandoc's own page style is for a screen: a table is a full-width block that scrolls sideways, and
-- a word may break anywhere. WeasyPrint set the caption of a narrow table a syllable a line. While that style is in
-- (no --css, `document-css` not false), a style in `header-includes` makes a table a table again, centred as LaTeX
-- sets it, with its caption centred and broken between words. WeasyPrint has no max-content width, so a caption is as
-- wide as its table; a table is at least 4in wide (LaTeX's caption width) and wider as its text needs. A numbered
-- equation (the LaTeX filter's three-cell table) spans the line, its number at the margin, without a table's rules.
-- An --include-in-header replaces the style, as it replaces the document's own header-includes.

if not FORMAT:match("^html") then return {} end

local TABLE_STYLE = "<style>\n"
  .. "table { display: table; width: auto; min-width: 4in; overflow: visible; margin-left: auto; margin-right: auto; }\n"
  .. "table caption { overflow-wrap: normal; text-align: center; }\n"
  .. 'table[data-custom-style="PdfmdEquation"] { width: 100%; }\n'
  .. 'table[data-custom-style="PdfmdEquation"] tbody { border: none; }\n'
  .. "</style>"

local function Meta(meta)
  local variables = PANDOC_WRITER_OPTIONS and PANDOC_WRITER_OPTIONS.variables or {}
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

local function Pandoc(doc)
  local count = 0
  doc:walk({Math = function() count = count + 1 end})
  if count > 0 then
    io.stderr:write(string.format("WARN  weasyprint: WeasyPrint does not typeset math; %d formula%s %s printed as text "
      .. "(simple ones in Unicode, the others as TeX). Typst or a LaTeX engine typesets %s: -e typst\n", count,
      count == 1 and "" or "s", count == 1 and "is" or "are", count == 1 and "it" or "them"))
  end
  return nil
end

return {{Meta = Meta, Pandoc = Pandoc}}
