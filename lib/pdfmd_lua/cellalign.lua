-- pdfmd: cell tags of pipe tables: ONE cell's alignment, merged cells (v3.31.52 for `<l>` `<c>` `<r>`, entry 3el; spans, entry 3fa).
--
-- pdfmd's pre-pass (lib/pdfmd_tables/celltags.py) reads every spelling of a cell tag (`<c>`, `&mc&`, `<merge-up, top>`, a bare `<<`
-- ...) and writes one canonical raw tag in front of each cell it touches:
--
--   <pc c2 r2 hc vm>    the owner of a merged region (2 columns, 2 rows), or a cell with its own alignment; every word is optional
--   <pc xl>, <pc xu>    a cell that the owner covers (the owner is to its left, or above it): dropped here
--
-- Pandoc's pipe tables have no spans, so this filter makes them: the owner gets `col_span` / `row_span`, covered cells are removed
-- from their rows (the AST wants a row to list only the cells that are not covered), and a span that reaches from the header into the
-- body moves those body rows into the header. The old tags `<l>`, `<c>`, `<r>` at the start of a cell are still read, for a
-- document that did not go through the pre-pass.
--
-- Vertical alignment (`valign`): LaTeX and Beamer rebuild such a table as a `longtblr` (tabularray; pdfmd adds the package), HTML gets a
-- `vertical-align` style; Typst and Word do not draw it yet.
--
-- Alignment: HTML, Typst, Word and the rest use the alignment a cell carries; LaTeX's writer ignores it for a one-column cell, so for
-- LaTeX and Beamer the cell's content is wrapped in raw TeX: `\multicolumn{1}{c}{...}` in a column of its natural width, `{\centering ...\par}`
-- (`\raggedleft`, `\raggedright`) in a column with a width (a `p{}` column). A cell that spans columns gets its alignment from the
-- writer's own `\multicolumn`. The filter must run after pdfmd's table-width filter, which sets those widths and measures an
-- unmerged table. The Markdown writers keep the text: the canonical tag is turned back into a `&...&` tag.

local ALIGN = {l = "AlignLeft", c = "AlignCenter", r = "AlignRight"}
local TEX_COMMAND = {l = "\\raggedright ", c = "\\centering ", r = "\\raggedleft "}

local BASE = FORMAT:match("^[^+-]+") or FORMAT
local USE_TBLR = true      -- `-M pdfmd-tblr=off` (pdfmd sets it when LaTeX has no tabularray): vertical letters are then ignored in LaTeX
local KEEP = {
  gfm = true, markdown = true, markdown_strict = true, markdown_mmd = true, markdown_phpextra = true, markdown_github = true,
  commonmark = true, commonmark_x = true,
}
local TEX = {latex = true, beamer = true}
local CSS_V = {t = "top", m = "middle", b = "bottom"}

-- the words of a `<pc ...>` raw tag, or an old `<l>`, `<c>`, `<r>`: {colspan, rowspan, halign, valign, covered}
local function read_tag(inline)
  if not inline or inline.t ~= "RawInline" or not inline.format:match("^html") then return nil end
  local body = inline.text:match("^<pc([^>]*)>$")
  if body then
    local tag = {colspan = 1, rowspan = 1}
    for word in body:gmatch("%S+") do
      local kind, value = word:sub(1, 1), word:sub(2)
      if kind == "x" then tag.covered = true; tag.arrow = value
      elseif kind == "c" and tonumber(value) then tag.colspan = tonumber(value)
      elseif kind == "r" and tonumber(value) then tag.rowspan = tonumber(value)
      elseif kind == "h" and #value == 1 then tag.halign = value
      elseif kind == "v" and #value == 1 then tag.valign = value end
    end
    return tag
  end
  local letter = inline.text:match("^<([lcrLCR])>$")
  if letter then return {halign = letter:lower(), colspan = 1, rowspan = 1} end
  return nil
end

-- a cell's tag and the cell's inlines without it (and the space after it)
local function take_tag(inlines)
  local tag = read_tag(inlines[1])
  if not tag then return nil end
  local rest = pandoc.Inlines{}
  local skipping = true
  for index = 2, #inlines do
    local item = inlines[index]
    if skipping and (item.t == "Space" or item.t == "SoftBreak") then
      -- the space after the tag
    else
      skipping = false
      rest:insert(item)
    end
  end
  return tag, rest
end

local function tex_wrap(letter, inlines, natural)
  local wrapped = pandoc.Inlines{}
  if natural then
    wrapped:insert(pandoc.RawInline("latex", "\\multicolumn{1}{" .. letter .. "}{"))
    wrapped:extend(inlines)
    wrapped:insert(pandoc.RawInline("latex", "}"))
  else
    wrapped:insert(pandoc.RawInline("latex", "{" .. TEX_COMMAND[letter]))
    wrapped:extend(inlines)
    wrapped:insert(pandoc.RawInline("latex", "\\par}"))
  end
  return wrapped
end

-- the Markdown writers keep what the user wrote, as a `&...&` tag
local function restore_text(tag)
  if tag.covered then return tag.arrow == "u" and "&^^&" or "&<<&" end
  local words = {}
  if tag.halign then words[#words + 1] = tag.halign end
  if tag.valign then words[#words + 1] = tag.valign end
  if #words == 0 then return nil end
  return "&" .. table.concat(words, ",") .. "&"
end

local function fix_cell(cell, column, tblr)
  if #cell.contents ~= 1 then return nil end
  local block = cell.contents[1]
  if block.t ~= "Plain" and block.t ~= "Para" then return nil end
  local tag, rest = take_tag(block.content)
  if not tag then return nil end
  if KEEP[BASE] then
    local text = restore_text(tag)
    local kept = pandoc.Inlines{}
    if text then kept:insert(pandoc.RawInline(BASE, text)) end
    if text and #rest > 0 then kept:insert(pandoc.Space()) end
    kept:extend(rest)
    cell.contents = {pandoc.Plain(kept)}
    return tag
  end
  local letter = tag.halign
  if tag.valign and not tag.covered and (tblr or not TEX[BASE]) then
    cell.attr = pandoc.Attr("", {}, {valign = tag.valign})       -- longtblr reads it; HTML gets a style below
    if BASE:match("^html") or BASE == "epub" or BASE == "slidy" or BASE == "revealjs" then
      cell.attr = pandoc.Attr("", {}, {style = "vertical-align: " .. CSS_V[tag.valign] .. ";"})
    end
  end
  if tag.covered then
    cell.contents = {pandoc.Plain(pandoc.Inlines{})}
  elseif letter and ALIGN[letter] and TEX[BASE] and tag.colspan == 1 and not tblr then
    local width = column and column[2]
    local natural = width == nil or width == 0
    cell.contents = {pandoc.Plain(#rest > 0 and tex_wrap(letter, rest, natural) or pandoc.Inlines{})}
  else
    if letter and ALIGN[letter] then cell.alignment = ALIGN[letter] end
    cell.contents = {pandoc.Plain(rest)}
  end
  if tag.colspan > 1 then cell.col_span = tag.colspan end
  if tag.rowspan > 1 then cell.row_span = tag.rowspan end
  return tag
end

-- one row of the input is a regular grid, so a cell's place in the row is its column; covered cells are dropped afterwards
local function fix_rows(rows, colspecs, tblr)
  for _, row in ipairs(rows) do
    local kept = {}
    for index, cell in ipairs(row.cells) do
      local tag = fix_cell(cell, colspecs[index], tblr)
      if not (tag and tag.covered and not KEEP[BASE]) then kept[#kept + 1] = cell end
    end
    row.cells = kept
  end
end

-- a header cell that spans rows reaches into the body: those body rows become header rows
local function promote_header(tbl)
  local head = tbl.head.rows
  local body = tbl.bodies[1]
  if not body or #body.body == 0 then return end
  local need = #head
  for index, row in ipairs(head) do
    for _, cell in ipairs(row.cells) do
      if (cell.row_span or 1) > 1 then need = math.max(need, index + cell.row_span - 1) end
    end
  end
  while #head < need and #body.body > 0 do
    head[#head + 1] = table.remove(body.body, 1)
  end
  tbl.head.rows = head
end

local function has_spans(tbl)
  local function scan(rows)
    for _, row in ipairs(rows) do
      for _, cell in ipairs(row.cells) do
        if (cell.row_span or 1) > 1 or (cell.col_span or 1) > 1 then return true end
      end
    end
    return false
  end
  if scan(tbl.head.rows) then return true end
  for _, body in ipairs(tbl.bodies) do
    if scan(body.body) then return true end
  end
  return false
end

-- does any cell of the table carry a vertical alignment? (read from the tags before they are cut off)
local function wants_tblr(tbl)
  if not (USE_TBLR and TEX[BASE]) then return false end
  local function scan(rows)
    for _, row in ipairs(rows) do
      for _, cell in ipairs(row.cells) do
        local block = #cell.contents == 1 and cell.contents[1] or nil
        if block and (block.t == "Plain" or block.t == "Para") then
          local tag = read_tag(block.content[1])
          if tag and tag.valign and not tag.covered then return true end
        end
      end
    end
    return false
  end
  if scan(tbl.head.rows) then return true end
  for _, body in ipairs(tbl.bodies) do
    if scan(body.head) or scan(body.body) then return true end
  end
  return scan(tbl.foot.rows)
end

-- tabularray's own words: `h` is the head (top) of the row, `m` the middle, `f` the foot (bottom). Its `t` and `b` are baseline
-- alignments, which are not what "top" and "bottom" mean to a reader.
local TBLR_V = {t = "h", m = "m", b = "f"}
local TBLR_H = {AlignLeft = "l", AlignRight = "r", AlignCenter = "c"}

local function latex_of(blocks)
  local text = pandoc.write(pandoc.Pandoc(blocks), "latex")
  text = text:gsub("^%s+", ""):gsub("%s+$", "")
  text = text:gsub("\n\n+", " \\par ")
  return text
end

-- The table as a `longtblr` (tabularray), built from Pandoc's own table model: spans, widths, alignments, header rows, caption, label.
local function to_tblr(tbl)
  local ncols = #tbl.colspecs
  local any_width, total = false, 0
  for _, spec in ipairs(tbl.colspecs) do
    if spec[2] and spec[2] > 0 then any_width = true; total = total + spec[2] end
  end
  local columns = {}
  for index, spec in ipairs(tbl.colspecs) do
    local letter = TBLR_H[spec[1]] or "l"
    if any_width then
      columns[index] = string.format("X[%.4f,%s]", (spec[2] and spec[2] > 0) and spec[2] or 0.05, letter)
    else
      columns[index] = "Q[" .. letter .. "]"
    end
  end
  local lines, cells = {}, {}
  local busy = {}
  for index = 1, ncols do busy[index] = 0 end
  local rownumber = 0
  local function emit(rows)
    for _, row in ipairs(rows) do
      rownumber = rownumber + 1
      local parts, taken, column = {}, 1, 1
      while column <= ncols do
        local cell = nil
        if busy[column] > 0 then
          busy[column] = busy[column] - 1
          parts[#parts + 1] = ""
          column = column + 1
        else
          cell = row.cells[taken]
          taken = taken + 1
          if not cell then
            parts[#parts + 1] = ""
            column = column + 1
          else
            local colspan, rowspan = cell.col_span or 1, cell.row_span or 1
            local style = {}
            local horizontal = TBLR_H[cell.alignment]
            if horizontal then style[#style + 1] = "halign=" .. horizontal end
            local vertical = TBLR_V[cell.attr.attributes.valign or ""]
            if vertical then style[#style + 1] = "valign=" .. vertical end
            local span = {}
            if rowspan > 1 then span[#span + 1] = "r=" .. rowspan end
            if colspan > 1 then span[#span + 1] = "c=" .. colspan end
            if #span > 0 or #style > 0 then
              cells[#cells + 1] = string.format("cell{%d}{%d}={%s}{%s}", rownumber, column, table.concat(span, ","), table.concat(style, ","))
            end
            parts[#parts + 1] = "{" .. latex_of(cell.contents) .. "}"
            for _ = 2, colspan do parts[#parts + 1] = "" end
            if rowspan > 1 then
              for offset = 0, colspan - 1 do busy[column + offset] = rowspan - 1 end
            end
            column = column + colspan
          end
        end
      end
      lines[#lines + 1] = table.concat(parts, " & ") .. " \\\\"
    end
  end
  lines[#lines + 1] = "\\toprule"
  emit(tbl.head.rows)
  if #tbl.head.rows > 0 then lines[#lines + 1] = "\\midrule" end
  for _, body in ipairs(tbl.bodies) do
    emit(body.head)
    emit(body.body)
  end
  emit(tbl.foot.rows)
  lines[#lines + 1] = "\\bottomrule"
  local options = {}
  local caption = latex_of(tbl.caption.long)
  if caption ~= "" then
    options[#options + 1] = "caption={" .. caption .. "}"
    if tbl.attr.identifier ~= "" then options[#options + 1] = "label={" .. tbl.attr.identifier .. "}" end
  else
    -- no caption: tabularray would still print "Table N:" and step the counter; this is `\caption*{}`
    options[#options + 1] = "caption={},entry=none,label=none"
  end
  local inner = {"colspec={@{}" .. table.concat(columns) .. "@{}}"}
  if any_width then inner[#inner + 1] = string.format("width=%.4f\\linewidth", total) end
  if #tbl.head.rows > 0 then inner[#inner + 1] = "rowhead=" .. #tbl.head.rows end
  inner[#inner + 1] = "cells={valign=h}"      -- every cell starts at the head of its row: a baseline cell (tabularray's default) beside a middle one misaligns
  for _, spec in ipairs(cells) do inner[#inner + 1] = spec end
  local head = "\\begin{longtblr}" .. (#options > 0 and ("[" .. table.concat(options, ",") .. "]") or "")
    .. "{\n" .. table.concat(inner, ",\n") .. "}\n"
  return pandoc.RawBlock("latex", head .. table.concat(lines, "\n") .. "\n\\end{longtblr}")
end

local function handle_table(tbl)
  local tblr = wants_tblr(tbl)
  fix_rows(tbl.head.rows, tbl.colspecs, tblr)
  for _, body in ipairs(tbl.bodies) do
    fix_rows(body.head, tbl.colspecs, tblr)
    fix_rows(body.body, tbl.colspecs, tblr)
  end
  fix_rows(tbl.foot.rows, tbl.colspecs, tblr)
  if not KEEP[BASE] and has_spans(tbl) then promote_header(tbl) end
  if tblr then return to_tblr(tbl) end
  return tbl
end

return {
  {
    Pandoc = function(doc)
      local setting = doc.meta["pdfmd-tblr"]
      if setting and pandoc.utils.stringify(setting) == "off" then USE_TBLR = false end
      return pandoc.Pandoc(doc.blocks:walk({Table = handle_table}), doc.meta)
    end,
  },
}
