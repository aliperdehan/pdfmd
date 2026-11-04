-- pdfmd: one line break for every writer (v3.31.49, entry 3el; the same idea as pagebreak.lua).
--
-- Each writer takes its own spelling of a line break and drops the others: HTML's `<br>` is dropped by LaTeX ("one<br>two"
-- printed "onetwo"), a raw TeX `\newline` by HTML, Word and Typst. In a table cell a blank line or `\par` would break the table,
-- so there was no way to put two lines in one cell. This filter reads every spelling that follows, whatever the reader kept
-- it as, and gives the target its own: Pandoc's LineBreak, which LaTeX draws as `\\` (in a table cell `\newline` or a box
-- of lines), Typst as `\`, Word as a break run, HTML as `<br />`.
--
--   <br>  <br/>  <br />  (any case)                        raw HTML
--   \newline  \linebreak  \linebreak[2]  \newline{}         raw TeX (Pandoc Markdown, not gfm)
--   #linebreak()                                            raw Typst
--   <w:r><w:br/></w:r>                                      raw Word (openxml)
--   \crlf                                                   raw ConTeXt
--
-- A spelling that is already in the target's own language is left exactly as written (`\newline` for LaTeX, `<br>` for HTML),
-- and so is everything for the Markdown family of writers, which keep what was written (unless raw HTML is switched off for
-- the writer, as in pdfmd's flat Markdown: there `<br>` would be dropped, so it is turned into a line break). A paragraph or a cell that holds
-- nothing but breaks is left too (the `space` markup kind reads `<br>` on a line of its own), and a break at the very start or
-- end of a run of text is dropped (a LineBreak there would only leave an empty line behind).
--
-- pdfmd passes the families that take part as `-M pdfmd-linebreak=html,tex,...` (html, tex, typst, word, context; run by hand
-- without it, every family does) and where, `-M pdfmd-linebreak-where=cells` (only inside tables, pdfmd's default) or `all`.

local families = {html = true, tex = true, typst = true, word = true, context = true}
local where = "cells"
local FAMILY_OF = {html = "html", tex = "tex", typst = "typst", openxml = "word", context = "context"}
local KEEP = {
  gfm = true, markdown = true, markdown_strict = true, markdown_mmd = true, markdown_phpextra = true, markdown_github = true,
  commonmark = true, commonmark_x = true,
}
-- the raw language each writer reads as its own
local OWN = {
  latex = "tex", beamer = "tex", context = "context", typst = "typst", docx = "openxml", pptx = "openxml",
  html = "html", html4 = "html", html5 = "html", epub = "html", epub2 = "html", epub3 = "html", revealjs = "html", s5 = "html",
  slideous = "html", slidy = "html", dzslides = "html", chunkedhtml = "html",
}

-- FORMAT carries the writer's extensions (`gfm-raw_html+tex_math_dollars`): the name alone, and whether raw HTML is switched off
-- (pdfmd's flat Markdown does that: a `<br>` would be dropped there, so it becomes a real line break like for any other writer)
local BASE = FORMAT:match("^[^+-]+") or FORMAT
local RAW_HTML_OFF = FORMAT:find("-raw_html", 1, true) ~= nil

local function trim(text)
  return (text:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- the raw language a line break is spelled in, or nil when the element is not one
local function spelling(element)
  if element.t ~= "RawInline" then return nil end
  local format, text = element.format, trim(element.text)
  if format:match("^html") and text:match("^<[bB][rR]%s*/?>$") then return "html" end
  if format == "tex" or format == "latex" then
    text = text:gsub("{}$", "")
    if text == "\\newline" or text == "\\linebreak" or text:match("^\\linebreak%[%d%]$") then return "tex" end
  end
  if format == "typst" and text == "#linebreak()" then return "typst" end
  if format == "openxml" and (text:gsub("%s", "")) == "<w:r><w:br/></w:r>" then return "openxml" end
  if format == "context" and text == "\\crlf" then return "context" end
  return nil
end

local function is_break(element)
  local language = spelling(element)
  return language ~= nil and families[FAMILY_OF[language]] == true
    and not (language == OWN[BASE] and not (language == "html" and RAW_HTML_OFF))
end

local function convert(inlines)
  local has_break, has_text = false, false
  for _, element in ipairs(inlines) do
    if is_break(element) then
      has_break = true
    elseif element.t ~= "Space" and element.t ~= "SoftBreak" and element.t ~= "LineBreak" then
      has_text = true
    end
  end
  if not has_break or not has_text then return nil end
  local out = pandoc.List()
  for _, element in ipairs(inlines) do
    out:insert(is_break(element) and pandoc.LineBreak() or element)
  end
  while #out > 0 and out[1].t == "LineBreak" do out:remove(1) end
  while #out > 0 and out[#out].t == "LineBreak" do out:remove(#out) end
  return out
end

local function setting(meta, key)
  local value = meta[key]
  if value == nil then return nil end
  return (pandoc.utils.stringify(value):lower())
end

return {
  {Meta = function(meta)
    local list = setting(meta, "pdfmd-linebreak")
    if list ~= nil then
      families = {}
      for word in list:gmatch("[%a]+") do families[word] = true end
    end
    where = setting(meta, "pdfmd-linebreak-where") or "cells"
    return nil
  end},
  {Pandoc = function(document)
    if KEEP[BASE] and not RAW_HTML_OFF then return nil end
    if where == "cells" then
      return document:walk({Table = function(table) return table:walk({Inlines = convert}) end})
    end
    return document:walk({Inlines = convert})
  end},
}
