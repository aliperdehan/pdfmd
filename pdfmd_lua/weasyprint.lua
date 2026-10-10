-- pdfmd: math in a PDF made by WeasyPrint (v3.27.12). WeasyPrint does not draw MathML: Pandoc's default HTML math printed
-- each formula twice as flat text (`x2+abx^2 + \frac{a}{b}`). pdfmd gives Pandoc --math-method=plain for WeasyPrint
-- (simple formulas in Unicode, `αᵢ ≤ β`; the others as their TeX), and this filter says so once, with the way to
-- typeset them. It changes nothing in the document.

if not FORMAT:match("^html") then return {} end

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

return {{Pandoc = Pandoc}}
