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
-- Alignment: HTML, Typst, Word and the rest use the alignment a cell carries; LaTeX's writer ignores it for a one-column cell, so for
-- LaTeX and Beamer the cell's content is wrapped in raw TeX: `\multicolumn{1}{c}{...}` in a column of its natural width, `{\centering ...\par}`
-- (`\raggedleft`, `\raggedright`) in a column with a width (a `p{}` column). A cell that spans columns gets its alignment from the
-- writer's own `\multicolumn`. The filter must run after pdfmd's table-width filter, which sets those widths and measures an
-- unmerged table. The Markdown writers keep the text: the canonical tag is turned back into a `&...&` tag.

local ALIGN = {l = "AlignLeft", c = "AlignCenter", r = "AlignRight"}
local TEX_COMMAND = {l = "\\raggedright ", c = "\\centering ", r = "\\raggedleft "}

local BASE = FORMAT:match("^[^+-]+") or FORMAT
local KEEP = {
  gfm = true, markdown = true, markdown_strict = true, markdown_mmd = true, markdown_phpextra = true, markdown_github = true,
  commonmark = true, commonmark_x = true,
}
local TEX = {latex = true, beamer = true}

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

local function fix_cell(cell, column)
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
  if tag.covered then
    cell.contents = {pandoc.Plain(pandoc.Inlines{})}
  elseif letter and ALIGN[letter] and TEX[BASE] and tag.colspan == 1 then
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
local function fix_rows(rows, colspecs)
  for _, row in ipairs(rows) do
    local kept = {}
    for index, cell in ipairs(row.cells) do
      local tag = fix_cell(cell, colspecs[index])
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

return {
  {
    Table = function(tbl)
      fix_rows(tbl.head.rows, tbl.colspecs)
      for _, body in ipairs(tbl.bodies) do
        fix_rows(body.head, tbl.colspecs)
        fix_rows(body.body, tbl.colspecs)
      end
      fix_rows(tbl.foot.rows, tbl.colspecs)
      if not KEEP[BASE] and has_spans(tbl) then promote_header(tbl) end
      return tbl
    end,
  },
}
