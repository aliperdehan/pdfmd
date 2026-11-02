-- pdfmd: the alignment of ONE table cell (v3.31.52, entry 3el).
--
-- A pipe table sets the alignment of a whole column, in its separator row (`:--`, `:-:`, `--:`). A cell that starts with
-- `<l>`, `<c>` or `<r>` overrides it for that cell alone:
--
--   | Name | Qty |
--   |:-----|----:|
--   | apples | 3 |
--   | <c> total | <l> 12 |
--
-- The tag is cut off (with the space after it) and the cell takes the alignment. Pandoc reads `<c>` as raw HTML, which most writers
-- drop, so without this filter the tag vanished and the alignment stayed the column's. A cell with nothing else after the tag is
-- an empty cell with that alignment.
--
-- Writers: HTML, Typst, Word and the rest use the alignment a cell carries; LaTeX's writer ignores it, so for LaTeX and
-- Beamer the cell's content is wrapped in raw TeX: `\multicolumn{1}{c}{...}` in a column of its natural width, `{\centering ...\par}`
-- (`\raggedleft`, `\raggedright`) in a column with a width (a `p{}` column). The filter must run after pdfmd's table-width filter,
-- which sets those widths. The Markdown writers keep the text as written, and a cell with more than one block is left alone.

local ALIGN = {l = "AlignLeft", c = "AlignCenter", r = "AlignRight"}
local TEX_COMMAND = {l = "\\raggedright ", c = "\\centering ", r = "\\raggedleft "}

local BASE = FORMAT:match("^[^+-]+") or FORMAT
local KEEP = {
  gfm = true, markdown = true, markdown_strict = true, markdown_mmd = true, markdown_phpextra = true, markdown_github = true,
  commonmark = true, commonmark_x = true,
}
local TEX = {latex = true, beamer = true}

-- the letter of a `<l>`, `<c>`, `<r>` tag at the start of a cell, and the cell's inlines without it
local function take_tag(inlines)
  local first = inlines[1]
  if not first or first.t ~= "RawInline" or not first.format:match("^html") then return nil end
  local letter = first.text:match("^<([lcrLCR])>$")
  if not letter then return nil end
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
  return letter:lower(), rest
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

local function fix_cell(cell, column)
  if #cell.contents ~= 1 then return end
  local block = cell.contents[1]
  if block.t ~= "Plain" and block.t ~= "Para" then return end
  local letter, rest = take_tag(block.content)
  if not letter then return end
  if TEX[BASE] then
    local width = column and column[2]
    local natural = width == nil or width == 0
    if #rest > 0 then
      cell.contents = {pandoc.Plain(tex_wrap(letter, rest, natural))}
    else
      cell.contents = {pandoc.Plain(pandoc.Inlines{})}
    end
  else
    cell.alignment = ALIGN[letter]
    cell.contents = {pandoc.Plain(rest)}
  end
end

local function fix_rows(rows, colspecs)
  for _, row in ipairs(rows) do
    local at = 1
    for _, cell in ipairs(row.cells) do
      fix_cell(cell, colspecs[at])
      at = at + (cell.col_span or 1)
    end
  end
end

if KEEP[BASE] then
  return {}
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
      return tbl
    end,
  },
}
