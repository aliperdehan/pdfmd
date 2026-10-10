-- pdfmd: one page break for every writer (v3.27.13). Before it only the built-in renderer understood
-- `<!-- pagebreak -->`; through Pandoc each writer took its own spelling and dropped the others (LaTeX the TeX commands,
-- WeasyPrint the CSS div, Word nothing but its own XML, Typst none of them).
--
-- A block that is nothing but a page break, in any of these spellings (case does not matter):
--   <!-- pagebreak -->, <!-- page-break -->, <!-- newpage -->, <!-- new-page -->, <!-- pdfmd: pagebreak -->
--   \newpage  \pagebreak  \pagebreak[3]  \clearpage  \newpage{}        \cleardoublepage (to an odd page)
--   <div style="page-break-after: always"></div> (before/after, break-before/after: page), <div class="pagebreak"></div>,
--   <hr class="pagebreak">, a fenced div `::: pagebreak` (or newpage) with nothing in it
--   ```{=typst} #pagebreak() ```   ```{=openxml} <w:p><w:r><w:br w:type="page"/></w:r></w:p> ```
-- becomes the target's own: LaTeX `\newpage{}`, Typst `#pagebreak(weak: true)`, HTML/EPUB/WeasyPrint a
-- `break-after: page` div, Word a page-break run, OpenDocument a paragraph in the `Pagebreak` style (pdfmd adds it to
-- the reference document it builds), ConTeXt `\page`, ms `.bp`, plain text a form feed, GitHub Markdown and CommonMark
-- `<!-- pagebreak -->`. A spelling already in the target's own language is left exactly as written (`\pagebreak[3]`
-- stays for LaTeX). Slides have no page breaks: one there is dropped, with a NOTE. Other writers (Pandoc Markdown, rst,
-- org ...) keep what was written. `--no-auto pagebreak` leaves this filter out.

local COMMENT_WORDS = {pagebreak = true, ["page-break"] = true, newpage = true, ["new-page"] = true}
local TEX_COMMANDS = {newpage = "page", pagebreak = "page", clearpage = "page", cleardoublepage = "odd"}
local CLASSES = {pagebreak = true, ["page-break"] = true, newpage = true, ["new-page"] = true}
local SLIDES = {beamer = true, pptx = true, revealjs = true, slidy = true, slideous = true, dzslides = true, s5 = true}

local function trim(text)
  return (text:gsub("^%s+", ""):gsub("%s+$", ""))
end

-- "page", "odd" or nil for a TeX command line
local function tex_break(text)
  local name, rest = trim(text):match("^\\(%a+)(.*)$")
  if not name or not TEX_COMMANDS[name] then return nil end
  rest = rest:gsub("^%[%d%]", ""):gsub("^{}", "")
  return rest == "" and TEX_COMMANDS[name] or nil
end

local function css_break(style)
  style = (style or ""):lower()
  return style:match("page%-break%-[ab][ef][a-z]*%s*:%s*always") or style:match("break%-[ab][ef][a-z]*%s*:%s*page")
    or style:match("break%-[ab][ef][a-z]*%s*:%s*always")
end

local function html_break(text)
  local lower = trim(text):lower()
  local word = lower:match("^<!%-%-%s*(.-)%s*%-%->$")
  if word then
    word = word:gsub("^pdfmd%s*:%s*", "")
    if COMMENT_WORDS[word] then return "page", "comment" end
    return nil
  end
  local tag, attributes = lower:match("^<(%a+)([^>]*)>")
  if not tag then return nil end
  local whole = lower:match("^<div[^>]*>%s*</div>$") or lower:match("^<hr[^>]*/?>$")
  if not whole then return nil end
  local style = attributes:match('style%s*=%s*"([^"]*)"') or attributes:match("style%s*=%s*'([^']*)'")
  if css_break(style) then return "page", "html" end                 -- a break in HTML as it is
  local class = attributes:match('class%s*=%s*"([^"]*)"') or attributes:match("class%s*=%s*'([^']*)'") or ""
  for name in class:gmatch("%S+") do
    if CLASSES[name] then return "page", "class" end                -- a break only where a stylesheet says so
  end
  return nil
end

-- (kind, the raw format it was written in) of a block that is only a page break, else nil
local function page_break(block)
  if block.t == "RawBlock" then
    local format = block.format:lower()
    if format == "html" or format == "html5" then
      local kind, source = html_break(block.text)
      if kind then return kind, source end
    elseif format == "tex" or format == "latex" then
      local kind = tex_break(block.text)
      if kind then return kind, "latex" end
    elseif format == "typst" and trim(block.text):match("^#pagebreak%(.*%)$") then
      return "page", "typst"
    elseif format == "openxml" and trim(block.text):match('^<w:p>%s*<w:r>%s*<w:br%s+w:type="page"%s*/>%s*</w:r>%s*</w:p>$') then
      return "page", "docx"
    end
  elseif block.t == "Div" then
    local empty = #block.content == 0
    if not empty then return nil end
    for _, class in ipairs(block.classes) do
      if CLASSES[class:lower()] then return "page", "div" end
    end
    if css_break(block.attributes.style) then return "page", "div" end
  elseif (block.t == "Para" or block.t == "Plain") and #block.content == 1 and block.content[1].t == "Str" then
    local kind = tex_break(block.content[1].text)     -- a GitHub-Markdown file reads `\newpage` as words
    if kind then return kind, "words" end
  end
  return nil
end

local target = FORMAT:lower():gsub("[+-].*$", "")
local dropped = 0

local function own(source)
  return (source == "latex" and (target == "latex" or target == "beamer"))
    or (source == "typst" and target == "typst")
    or (source == "docx" and target == "docx")
    or (source == "html" and (target:match("^html") or target:match("^epub")))
end

local function replacement(kind)
  if target == "latex" then
    return pandoc.RawBlock("latex", kind == "odd" and "\\cleardoublepage{}" or "\\newpage{}")
  elseif target == "typst" then
    return pandoc.RawBlock("typst", kind == "odd" and '#pagebreak(weak: true, to: "odd")' or "#pagebreak(weak: true)")
  elseif target:match("^html") or target:match("^epub") then
    return pandoc.RawBlock("html", string.format('<div style="break-after: %s; page-break-after: %s"></div>',
      kind == "odd" and "recto" or "page", kind == "odd" and "right" or "always"))
  elseif target == "docx" then
    return pandoc.RawBlock("openxml", '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
  elseif target == "odt" or target == "opendocument" then
    return pandoc.RawBlock("opendocument", '<text:p text:style-name="Pagebreak"/>')
  elseif target == "context" then
    return pandoc.RawBlock("context", "\\page")
  elseif target == "ms" then
    return pandoc.RawBlock("ms", ".bp")
  elseif target == "plain" then
    return pandoc.RawBlock("plain", "\f")
  elseif target == "gfm" or target == "commonmark" or target == "commonmark_x" then
    return pandoc.RawBlock("markdown", "<!-- pagebreak -->")
  end
  return nil
end

local function block(element)
  local kind, source = page_break(element)
  if not kind then return nil end
  if SLIDES[target] then
    if source == "latex" and target == "beamer" then return nil end
    dropped = dropped + 1
    return {}
  end
  if own(source) then return nil end
  return replacement(kind)
end

local filter = {RawBlock = block, Div = block, Para = block, Plain = block}

return {{Pandoc = function(doc)
  doc = doc:walk(filter)
  if dropped > 0 then
    io.stderr:write(string.format("NOTE  pagebreak: %d page break%s left out: slides have no pages to break\n", dropped,
      dropped == 1 and "" or "s"))
  end
  return doc
end}}
