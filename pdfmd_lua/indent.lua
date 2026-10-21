-- pdfmd: paragraph indentation for a stretch of text (v3.30.0). A fenced div
--
--   ::: {indent=false}            (also `::: noindent`, `::: {.noindent}`)
--   Calculation lines ...
--   :::
--
-- sets the first-line indent of every paragraph inside it and puts the document's own back at the closing `:::`, so
-- there is no "turn it back on" line to forget. The value:
--   indent=false | no | off | 0     no indent
--   indent=true  | yes | on         1.5em (`.indent` alone means the same)
--   indent=2em | 12pt | 5mm | 0.2in  that length (a bare number is em)
-- Nested divs work (the inner one wins, the outer comes back after it). The div's id and other classes stay.
--
-- LaTeX and Beamer get `\begingroup\setlength{\parindent}{..}` ... `\endgroup`, Typst `#[#set par(first-line-indent: ..)`
-- ... `]`, HTML-family writers a `text-indent` style on the div. Pandoc Markdown, GFM, CommonMark and the like keep the
-- div as written. Every other writer (Word, OpenDocument, EPUB's CSS aside, plain text ...) has no per-block indent
-- to set: the text stays, the setting is dropped, with a NOTE on stderr.
--
-- This filter is added only when a document has such a div (pdfmd.py: indent_filter_args()).

local target = FORMAT:lower():gsub("[+-].*$", "")

local TEX = {latex = true, beamer = true}
local HTML = {html = true, html4 = true, html5 = true, epub = true, epub2 = true, epub3 = true, revealjs = true,
  slidy = true, slideous = true, s5 = true, dzslides = true, chunkedhtml = true}
local KEEP = {markdown = true, markdown_strict = true, markdown_phpextra = true, markdown_mmd = true, gfm = true,
  commonmark = true, commonmark_x = true, json = true, native = true}

local DEFAULT = "1.5em"
local UNITS = {em = true, ex = true, pt = true, cm = true, mm = true, ["in"] = true, bp = true, pc = true,
  px = true, rem = true, ["%"] = true}
local WORDS = {["false"] = "off", no = "off", off = "off", ["true"] = "on", yes = "on", on = "on"}

local unsupported = 0
local invalid = {}

-- "0pt" for off, a length for the rest, nil (and a WARN later) for something else
local function length(value)
  local word = WORDS[value:lower()]
  if word == "off" then return "0pt" end
  if word == "on" then return DEFAULT end
  local number, unit = value:match("^(%-?%d*%.?%d+)%s*(%a*%%?)$")
  if not number then return nil end
  if unit == "" then unit = "em" end
  if not UNITS[unit:lower()] then return nil end
  if tonumber(number) == 0 then return "0pt" end
  return number .. unit:lower()
end

local function wanted(div)
  local value = div.attributes["indent"]
  local classes = {}
  for _, class in ipairs(div.classes) do classes[class] = true end
  if value == nil and not classes.noindent and not classes.indent then return nil end
  local result
  if value ~= nil then
    result = length(value)
    if not result then
      invalid[#invalid + 1] = value
      return nil, true
    end
  else
    result = classes.noindent and "0pt" or DEFAULT
  end
  return result, true
end

local function stripped(div)
  local attributes = pandoc.Attr(div.identifier, {}, {})
  for _, class in ipairs(div.classes) do
    if class ~= "noindent" and class ~= "indent" then attributes.classes:insert(class) end
  end
  for key, value in pairs(div.attributes) do
    if key ~= "indent" then attributes.attributes[key] = value end
  end
  return attributes
end

local function plain(attr)
  if attr.identifier ~= "" or #attr.classes > 0 then return false end
  for _ in pairs(attr.attributes) do return false end
  return true
end

return {{Div = function(div)
  local value, mentioned = wanted(div)
  if not mentioned then return nil end
  if not value then                                   -- invalid value (WARN at the end): no indent change
    return KEEP[target] and nil or pandoc.Div(div.content, stripped(div))
  end
  local attr = stripped(div)
  if TEX[target] then
    local blocks = pandoc.List({pandoc.RawBlock("latex", "\\begingroup\\setlength{\\parindent}{" .. value .. "}")})
    if plain(attr) then
      blocks:extend(div.content)
    else
      blocks:insert(pandoc.Div(div.content, attr))
    end
    blocks:insert(pandoc.RawBlock("latex", "\\endgroup"))
    return blocks
  elseif target == "typst" then
    local rule = value == "0pt" and "0pt" or ("(amount: " .. value .. ", all: true)")
    -- a content block, not a #block[ ]: a set rule inside a #block that follows a paragraph does not indent (Typst 0.15)
    local blocks = pandoc.List({pandoc.RawBlock("typst", "#[#set par(first-line-indent: " .. rule .. ")")})
    blocks:extend(div.content)
    blocks:insert(pandoc.RawBlock("typst", "]" .. (attr.identifier ~= "" and (" <" .. attr.identifier .. ">") or "")))
    return blocks
  elseif HTML[target] then
    local style = "text-indent: " .. value
    local old = attr.attributes["style"]
    attr.attributes["style"] = old and old ~= "" and (old:gsub(";%s*$", "") .. "; " .. style) or style
    return pandoc.Div(div.content, attr)
  elseif KEEP[target] then
    return nil
  end
  unsupported = unsupported + 1
  return pandoc.Div(div.content, attr)
end,
Pandoc = function(doc)
  for _, value in ipairs(invalid) do
    io.stderr:write(string.format("WARN  indent: '%s' is not an indent (false, true, or a length such as 2em, 12pt, 5mm); "
      .. "the div is left as it is\n", value))
  end
  if unsupported > 0 then
    io.stderr:write(string.format("NOTE  indent: %d indent setting%s left out: %s has no per-block paragraph indent\n",
      unsupported, unsupported == 1 and "" or "s", target))
  end
  return doc
end}}
