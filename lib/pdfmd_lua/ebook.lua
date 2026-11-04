-- pdfmd: the EPUB that becomes an ebook through Calibre (v3.29.1). Two jobs, both for the EPUB writer only:
--
-- 1. A picture the LaTeX filter drew for a formula (pdfmd_office/office.lua) carries `pdfmd:svg=<a path in pdfmd's
--    cache>;dp=...` as its title, for the Word route to read. In an ebook it would be a tooltip that names a folder of
--    this machine, so it goes; the picture's description (`LaTeX: x^2`) stays.
-- 2. For a target with no math (`pdfmd-ebook-math=text`: pdb, rb, snb, tcr, pmlz, txtz, rtf, txt, fb2, and a target that
--    would have had pictures where there is no LaTeX to draw them) each formula becomes plain text, as Pandoc's plain
--    math writes it (simple ones as text with superscripts, else their TeX), and a WARN says so once, with their number. MathML would be
--    dropped by the converter and leave a hole in the sentence.
if not FORMAT:match("^epub") then return {} end

local plain_math = pandoc.WriterOptions({html_math_method = "plain"})

local function meta_string(doc, key)
  local value = doc.meta[key]
  return value ~= nil and pandoc.utils.stringify(value) or nil
end

local function Image(el)
  if el.title and el.title:match("^pdfmd:") then
    el.title = ""
    return el
  end
  return nil
end

-- a formula as Pandoc's plain math writes it
local function plain(el)
  local html
  local function attempt() html = pandoc.write(pandoc.Pandoc({pandoc.Plain({el})}), "html", plain_math) end
  if pandoc.log and pandoc.log.silence then pandoc.log.silence(attempt) else attempt() end
  return pandoc.RawInline("html", (html:gsub("%s+$", "")))
end

local function Pandoc(doc)
  if meta_string(doc, "pdfmd-ebook-math") ~= "text" then return nil end
  local count = 0
  doc = doc:walk({Math = function(el)
    count = count + 1
    return plain(el)
  end})
  if count > 0 then
    local why = meta_string(doc, "pdfmd-ebook-why")
    io.stderr:write(string.format("WARN  %s has no math: %d formula%s %s text (the simple ones with their superscripts, "
      .. "the rest as TeX)%s\n", meta_string(doc, "pdfmd-ebook") or "the ebook", count, count == 1 and "" or "s",
      count == 1 and "is" or "are", why and (" - " .. why) or ""))
  end
  return doc
end

return {{Image = Image}, {Pandoc = Pandoc}}
