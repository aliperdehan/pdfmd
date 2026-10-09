-- pdfmd: flat Markdown (v3.26.3). `--to gfm` writes plain GitHub-flavoured Markdown that any viewer reads as it is: no
-- HTML, no attribute braces, no Pandoc-only syntax. This filter runs last (after pandoc-crossref, the raw-piece
-- expansion, citeproc and the document's own filters) and takes out what Pandoc's gfm writer would otherwise leave as
-- HTML or as noise:
--
--   * a title block: `# Title`, an `*Author -- date*` line and the abstract (the front matter itself is not written);
--   * headings: attributes dropped, the section numbers written into the text when the document numbers its sections;
--   * captions: `**Table 1.** text` above a table, the same under a figure (pandoc-crossref's `Table 1: text` is split at
--     its number, whatever the language), and no `{#tbl:x}` left behind;
--   * `<div>`, `<span>`, `<figure>` and the bibliography's divisions: unwrapped; links to ids that no longer exist become
--     plain text, links to a heading point at the slug GitHub gives that heading;
--   * display math: the numbering environment is unwrapped (\begin{equation}, \label, \nonumber), align -> aligned;
--   * subscripts and superscripts: Unicode (H2O -> H₂O) where every character has one, else `_(..)` / `^(..)`;
--     `html` keeps <sub>/<sup>, `drop` writes the plain text, `ascii` always writes `_(..)` / `^(..)`;
--   * definition lists (a bold term, then the definition), line blocks, small capitals, underline;
--   * tables GFM cannot hold (spans, several header rows, block or multi-line cells) are written as an HTML table, the
--     one HTML that stays, and counted in a note;
--   * raw pieces that no writer could carry (a raw Word XML, a LaTeX macro nothing read) are left out and counted in a
--     warning, not dropped silently.
--
-- Configuration arrives as metadata written by pdfmd: `pdfmd-flat` = {scripts = "unicode|html|drop|ascii", title = true|false}.

if not FORMAT:match("^gfm") and not FORMAT:match("^commonmark") and not FORMAT:match("^markdown") then return {} end

local config = {scripts = "unicode", title = true}
local flat = false

local function truthy(value)
  if value == nil then return false end
  if type(value) == "boolean" then return value end
  local text = pandoc.utils.stringify(value):lower()
  return text == "true" or text == "yes" or text == "on" or text == "1"
end

local function read_config(meta)
  local setting = meta["pdfmd-flat"]
  if type(setting) ~= "table" then return end
  flat = true
  if setting.scripts then config.scripts = pandoc.utils.stringify(setting.scripts):lower() end
  if setting.title ~= nil then config.title = truthy(setting.title) end
end

-- sub/superscripts -----------------------------------------------------------------------------------------------------
local SUPER = {
  ["0"] = "⁰", ["1"] = "¹", ["2"] = "²", ["3"] = "³", ["4"] = "⁴", ["5"] = "⁵", ["6"] = "⁶", ["7"] = "⁷",
  ["8"] = "⁸", ["9"] = "⁹", ["+"] = "⁺", ["-"] = "⁻", ["−"] = "⁻", ["="] = "⁼", ["("] = "⁽", [")"] = "⁾",
  a = "ᵃ", b = "ᵇ", c = "ᶜ", d = "ᵈ", e = "ᵉ", f = "ᶠ", g = "ᵍ", h = "ʰ", i = "ⁱ", j = "ʲ", k = "ᵏ", l = "ˡ",
  m = "ᵐ", n = "ⁿ", o = "ᵒ", p = "ᵖ", r = "ʳ", s = "ˢ", t = "ᵗ", u = "ᵘ", v = "ᵛ", w = "ʷ", x = "ˣ", y = "ʸ",
  z = "ᶻ", A = "ᴬ", B = "ᴮ", D = "ᴰ", E = "ᴱ", G = "ᴳ", H = "ᴴ", I = "ᴵ", J = "ᴶ", K = "ᴷ", L = "ᴸ", M = "ᴹ",
  N = "ᴺ", O = "ᴼ", P = "ᴾ", R = "ᴿ", T = "ᵀ", U = "ᵁ", V = "ⱽ", W = "ᵂ",
}
local SUB = {
  ["0"] = "₀", ["1"] = "₁", ["2"] = "₂", ["3"] = "₃", ["4"] = "₄", ["5"] = "₅", ["6"] = "₆", ["7"] = "₇",
  ["8"] = "₈", ["9"] = "₉", ["+"] = "₊", ["-"] = "₋", ["−"] = "₋", ["="] = "₌", ["("] = "₍", [")"] = "₎",
  a = "ₐ", e = "ₑ", h = "ₕ", i = "ᵢ", j = "ⱼ", k = "ₖ", l = "ₗ", m = "ₘ", n = "ₙ", o = "ₒ", p = "ₚ", r = "ᵣ",
  s = "ₛ", t = "ₜ", u = "ᵤ", v = "ᵥ", x = "ₓ",
}

local function plain_text(inlines)
  -- the text of inlines made only of words and spaces; nil when anything else is in them (emphasis, math, a link ...)
  local out = {}
  for _, item in ipairs(inlines) do
    if item.t == "Str" then out[#out + 1] = item.text
    elseif item.t == "Space" or item.t == "SoftBreak" then out[#out + 1] = " "
    else return nil end
  end
  return table.concat(out)
end

local function mapped(text, table_)
  local out = {}
  for _, code in utf8.codes(text) do
    local character = utf8.char(code)
    local replacement = table_[character]
    if not replacement then return nil end
    out[#out + 1] = replacement
  end
  return table.concat(out)
end

local function script(element, marker, table_, tag)
  local mode = config.scripts
  local content = element.content
  if mode == "html" then
    local out = pandoc.Inlines{pandoc.RawInline("markdown", "<" .. tag .. ">")}
    out:extend(content)
    out:insert(pandoc.RawInline("markdown", "</" .. tag .. ">"))
    return out
  elseif mode == "drop" then
    return content
  end
  local text = plain_text(content)
  if mode == "unicode" and text then
    local unicode = mapped(text, table_)
    if unicode then return pandoc.Str(unicode) end
  end
  if text then
    if utf8.len(text) == 1 and text:match("^[%w]$") then return pandoc.RawInline("markdown", marker .. text) end
    return pandoc.RawInline("markdown", marker .. "(" .. text .. ")")
  end
  return content            -- emphasis or math inside a script: the plain content
end

-- math -------------------------------------------------------------------------------------------------------------------
-- A viewer's math (GitHub, VS Code, Obsidian: MathJax or KaTeX) has no equation numbers or labels, and knows `aligned`,
-- not `align`: the numbering environment is unwrapped, \label and \nonumber go, align/gather become aligned/gathered.
local function display_math(element)
  if element.mathtype ~= "DisplayMath" then return nil end
  local text = element.text
  local changed = false
  local function replace(pattern, with)
    local result, count = text:gsub(pattern, with)
    if count > 0 then text, changed = result, true end
  end
  replace("\\label%s*{[^}]*}", "")
  replace("\\nonumber", "")
  replace("\\notag", "")
  local inner = text:match("^%s*\\begin%s*{equation%*?}(.-)\\end%s*{equation%*?}%s*$")
  if inner then text, changed = inner, true end
  for from, to in pairs({align = "aligned", gather = "gathered"}) do
    local body = text:match("^%s*\\begin%s*{" .. from .. "%*?}(.-)\\end%s*{" .. from .. "%*?}%s*$")
    if body then text, changed = "\\begin{" .. to .. "}" .. body .. "\\end{" .. to .. "}", true end
  end
  if changed then return pandoc.Math("DisplayMath", (text:gsub("^%s+", ""):gsub("%s+$", ""))) end
  return nil
end

-- headings, slugs, links ---------------------------------------------------------------------------------------------
local slugs = {}            -- heading id -> the anchor GitHub gives the heading

local function github_slug(text)
  local out = text:lower():gsub("[^%w%s_%-\128-\255]", ""):gsub("%s", "-")
  return out
end

local function truthy_meta(meta, ...)
  for _, key in ipairs({...}) do
    if truthy(meta[key]) then return true end
  end
  return false
end

local function number_headings(doc)
  local options = PANDOC_WRITER_OPTIONS
  if not ((options and options.number_sections) or truthy_meta(doc.meta, "number-sections", "numbersections")) then
    return doc
  end
  local counters = {0, 0, 0, 0, 0, 0}
  local base = nil                       -- Pandoc numbers from the shallowest level in use
  doc.blocks:walk({Header = function(header) if not base or header.level < base then base = header.level end end})
  local walked = pandoc.walk_block(pandoc.Div(doc.blocks), {
    Header = function(header)
      if header.classes:includes("unnumbered") then return nil end
      local level = math.min(header.level, 6)
      counters[level] = counters[level] + 1
      for deeper = level + 1, 6 do counters[deeper] = 0 end
      local parts = {}
      for index = (base or 1), level do parts[#parts + 1] = tostring(counters[index]) end
      header.content = pandoc.Inlines{pandoc.Str(table.concat(parts, ".")), pandoc.Space()} .. header.content
      return header
    end,
  })
  doc.blocks = walked.content
  return doc
end

local function collect_slugs(doc)
  local seen = {}
  doc.blocks:walk({Header = function(header)
    local slug = github_slug(pandoc.utils.stringify(header))
    local count = seen[slug] or 0
    seen[slug] = count + 1
    local anchor = count == 0 and slug or (slug .. "-" .. count)
    if header.identifier ~= "" then slugs[header.identifier] = anchor end
  end})
end

local function link(element)
  local target = element.target
  if target:sub(1, 1) ~= "#" then
    element.attr = pandoc.Attr()
    return element
  end
  local anchor = slugs[target:sub(2)]
  if anchor then
    element.target = "#" .. anchor
    element.attr = pandoc.Attr()
    return element
  end
  return element.content                 -- the anchor is gone (a figure, a table, a reference entry): the text stays
end

-- captions -------------------------------------------------------------------------------------------------------------
-- pandoc-crossref writes "Table 1: text" (any language, any delimiter): the label is everything up to the Str that holds
-- the number and ends in the delimiter.
local function split_caption(inlines)
  for index = 1, math.min(#inlines, 9) do
    local item = inlines[index]
    if item.t == "Str" and item.text:match("^[%w%.%-]*%d[%w%.%-]*[:.]$") then
      local label = pandoc.Inlines{}
      for k = 1, index - 1 do
        if inlines[k].t ~= "Str" and inlines[k].t ~= "Space" then return nil, inlines end
        label:insert(inlines[k])
      end
      label:insert(pandoc.Str(item.text:sub(1, -2) .. "."))
      local rest = pandoc.Inlines{}
      local from = index + 1
      while inlines[from] and inlines[from].t == "Space" do from = from + 1 end
      for k = from, #inlines do rest:insert(inlines[k]) end
      return label, rest
    end
  end
  return nil, inlines
end

local function caption_inlines(caption)
  local out = pandoc.Inlines{}
  for _, block in ipairs(caption.long) do
    if block.content then
      if #out > 0 then out:insert(pandoc.Space()) end
      out:extend(block.content)
    end
  end
  return out
end

local function caption_paragraph(caption)
  local inlines = caption_inlines(caption)
  if #inlines == 0 then return nil end
  local label, rest = split_caption(inlines)
  if label then
    local out = pandoc.Inlines{pandoc.Strong(label)}
    if #rest > 0 then out:insert(pandoc.Space()) out:extend(rest) end
    return pandoc.Para(out)
  end
  return pandoc.Para{pandoc.Emph(inlines)}
end

-- tables ---------------------------------------------------------------------------------------------------------------
local function has_line_break(blocks)
  local found = false
  pandoc.walk_block(pandoc.Div(blocks), {LineBreak = function() found = true end})
  return found
end

local function simple_table(tbl)
  if #tbl.bodies ~= 1 or #tbl.head.rows > 1 or #tbl.foot.rows > 0 then return false end
  if tbl.bodies[1].row_head_columns > 0 or #tbl.bodies[1].head > 0 then return false end
  local function cells_ok(rows)
    for _, row in ipairs(rows) do
      for _, cell in ipairs(row.cells) do
        if cell.row_span > 1 or cell.col_span > 1 or #cell.contents > 1 then return false end
        local block = cell.contents[1]
        if block and block.t ~= "Plain" and block.t ~= "Para" then return false end
        if block and has_line_break({block}) then return false end
      end
    end
    return true
  end
  return cells_ok(tbl.head.rows) and cells_ok(tbl.bodies[1].body)
end

local html_tables = 0

local function convert_table(tbl)
  local caption = caption_paragraph(tbl.caption)
  tbl.caption = pandoc.Caption({})
  tbl.attr = pandoc.Attr()
  local out = pandoc.Blocks{}
  if caption then out:insert(caption) end
  if simple_table(tbl) then
    out:insert(tbl)
  else
    html_tables = html_tables + 1
    out:insert(pandoc.RawBlock("markdown", pandoc.write(pandoc.Pandoc({tbl}), "html")))
  end
  return out
end

-- figures --------------------------------------------------------------------------------------------------------------
local function convert_figure(figure)
  local out = pandoc.Blocks{}
  for _, block in ipairs(figure.content) do
    if block.t == "Plain" then out:insert(pandoc.Para(block.content)) else out:insert(block) end
  end
  local caption = caption_paragraph(figure.caption)
  if caption then out:insert(caption) end
  return out
end

-- the document's head ---------------------------------------------------------------------------------------------------
local function meta_inlines(value)
  if value == nil then return nil end
  local kind = pandoc.utils.type(value)
  if kind == "Inlines" then return value end
  if kind == "Blocks" then
    local first = value[1]
    if first and first.content then return first.content end
  end
  local text = pandoc.utils.stringify(value)
  if text == "" then return nil end
  return pandoc.Inlines{pandoc.Str(text)}
end

local function author_names(value)
  local names = {}
  if value == nil then return names end
  if pandoc.utils.type(value) == "List" then
    for _, item in ipairs(value) do
      local name = type(item) == "table" and item.name or item
      names[#names + 1] = pandoc.utils.stringify(name)
    end
  else
    names[1] = pandoc.utils.stringify(value)
  end
  return names
end

local function title_block(meta)
  local out = pandoc.Blocks{}
  local title = meta_inlines(meta.title)
  if title then out:insert(pandoc.Header(1, title)) end
  local subtitle = meta_inlines(meta.subtitle)
  if subtitle then out:insert(pandoc.Para{pandoc.Strong(subtitle)}) end
  local line = table.concat(author_names(meta.author), ", ")
  local date = meta.date and pandoc.utils.stringify(meta.date) or ""
  if line ~= "" and date ~= "" then line = line .. " — " .. date elseif date ~= "" then line = date end
  if line ~= "" then out:insert(pandoc.Para{pandoc.Emph{pandoc.Str(line)}}) end
  local abstract = meta.abstract
  if abstract then
    local inlines = meta_inlines(abstract)
    if inlines then
      local text = pandoc.Inlines{pandoc.Strong{pandoc.Str("Abstract.")}, pandoc.Space()}
      text:extend(inlines)
      out:insert(pandoc.Para(text))
    end
  end
  return out
end

-- raw pieces nothing carried -------------------------------------------------------------------------------------------
local KEEP_RAW = {markdown = true, gfm = true, commonmark = true, ["markdown_strict"] = true}
local RAW_NAME = {tex = "LaTeX", latex = "LaTeX", html = "HTML", html5 = "HTML", typst = "Typst", openxml = "Word XML",
                  opendocument = "OpenDocument XML"}
local dropped = {}
local samples = {}

local function note_raw(element)
  if KEEP_RAW[element.format] then return nil end
  if element.format == "openxml" and element.text:match("^<w:tcPr><w:vAlign[^>]*/></w:tcPr>$") then return {} end   -- pandoc-crossref's own
  local name = RAW_NAME[element.format] or element.format
  dropped[name] = (dropped[name] or 0) + 1
  if not samples[name] then
    local text = element.text:gsub("%s+", " ")
    samples[name] = #text > 40 and (text:sub(1, 40) .. "...") or text
  end
  return {}
end

local function report_dropped()
  local names = {}
  for name in pairs(dropped) do names[#names + 1] = name end
  table.sort(names)
  for _, name in ipairs(names) do
    local count = dropped[name]
    io.stderr:write(string.format("WARN  gfm: %d raw %s piece%s (e.g. %s) %s no plain-Markdown form and %s left out\n",
      count, name, count == 1 and "" or "s", samples[name], count == 1 and "has" or "have", count == 1 and "was" or "were"))
  end
  if html_tables > 0 then
    io.stderr:write(string.format("NOTE  gfm: %d table%s too rich for a Markdown table (spans, several header rows, block cells) "
      .. "%s written as an HTML table\n", html_tables, html_tables == 1 and "" or "s", html_tables == 1 and "was" or "were"))
  end
end

-- the passes -------------------------------------------------------------------------------------------------------------
local function remove_title_attr(element)
  element.attr = pandoc.Attr()
  return element
end

local inline_pass = {
  Span = function(span) return span.content end,
  SmallCaps = function(item) return item.content end,
  Underline = function(item) return item.content end,
  Subscript = function(item) return script(item, "_", SUB, "sub") end,
  Superscript = function(item) return script(item, "^", SUPER, "sup") end,
  Link = link,
  Math = display_math,
  Image = remove_title_attr,
  Code = remove_title_attr,
  RawInline = note_raw,
}

local function code_block(block)
  local language = nil
  for _, class in ipairs(block.classes) do
    if class ~= "numberLines" and class ~= "number-lines" and class ~= "sourceCode" then language = class break end
  end
  block.attr = language and pandoc.Attr("", {language}) or pandoc.Attr()
  return block
end

local function definition_list(list)
  local out = pandoc.Blocks{}
  for _, item in ipairs(list.content) do
    out:insert(pandoc.Para{pandoc.Strong(item[1])})
    for _, definition in ipairs(item[2]) do
      for _, block in ipairs(definition) do
        out:insert(block.t == "Plain" and pandoc.Para(block.content) or block)
      end
    end
  end
  return out
end

local function line_block(block)
  local inlines = pandoc.Inlines{}
  for index, line in ipairs(block.content) do
    if index > 1 then inlines:insert(pandoc.LineBreak()) end
    inlines:extend(line)
  end
  return pandoc.Para(inlines)
end

local block_pass = {
  Div = function(div) return div.content end,
  Header = remove_title_attr,
  CodeBlock = code_block,
  Figure = convert_figure,
  Table = convert_table,
  DefinitionList = definition_list,
  LineBlock = line_block,
  RawBlock = note_raw,
}

local function flatten(doc)
  read_config(doc.meta)
  if not flat then return nil end
  doc = number_headings(doc)
  collect_slugs(doc)
  doc = doc:walk(inline_pass)
  doc = doc:walk(block_pass)
  if config.title then
    local head = title_block(doc.meta)
    head:extend(doc.blocks)
    doc.blocks = head
  end
  report_dropped()
  return doc
end

return {{Pandoc = flatten}}
