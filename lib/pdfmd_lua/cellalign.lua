-- pdfmd: cell tags of pipe tables: one cell's alignment, merged cells, vertical alignment, and a table's widths and heights
-- (v3.31.52 for `<l>` `<c>` `<r>`, entry 3el; spans, vertical alignment and sizes, entry 3fa).
--
-- pdfmd's pre-pass (lib/pdfmd_tables/celltags.py) reads every spelling of a cell tag (`<c>`, `&mc&`, `<merge-up, top>`, a bare `<<`
-- ...) and of a table's attribute line, and writes short raw tags:
--
--   <pc c2 r2 hc vm>    in front of a cell: the owner of a merged region (2 columns, 2 rows), or a cell with its own alignment
--   <pc xl>, <pc xu>    a cell that the owner covers (the owner is to its left, or above it): dropped here
--   <pt c2w=3cm r3ht=1.5cm v=m>    in the first header cell: the table's settings (`w` width, `ht` least height, `h` and `v` alignment;
--                                  `c2` / `r3` for column 2 / row 3, nothing for the table)
--
-- Pandoc's pipe tables have no spans, so this filter makes them: the owner gets `col_span` / `row_span`, covered cells are removed
-- from their rows (the AST wants a row to list only the cells that are not covered), and a span that reaches from the header into the
-- body moves those body rows into the header. The old tags `<l>`, `<c>`, `<r>` at the start of a cell are still read, for a
-- document that did not go through the pre-pass.
--
-- Alignment of a cell, most specific first: its own tag, its row, its column, the column's `:--:` in the separator row, the table's
-- `align=`, the default of pdfmd-options (`-M pdfmd-table-align`, `pdfmd-table-valign`). HTML, Typst, Word and the rest use the alignment a
-- cell carries; LaTeX's writer ignores it for a one-column cell, so for LaTeX and Beamer the content is wrapped in raw TeX:
-- `\multicolumn{1}{c}{...}` in a column of its natural width, `{\centering ...\par}` (`\raggedleft`, `\raggedright`) in a column with a
-- width. A cell that spans columns gets its alignment from the writer's own `\multicolumn`.
--
-- A table that needs more than that in LaTeX (a vertical alignment, a width, a height) is rebuilt as a `longtblr` (tabularray; pdfmd
-- adds the package): LaTeX has one baseline per row, and Pandoc's table model has no lengths. HTML gets `vertical-align` and `height`
-- styles, and percentage widths (the AST's column widths); Typst and Word do not draw these yet. The filter must run after pdfmd's
-- table-width filter, which sets the widths of a table without any, and measures the table as written. The Markdown writers keep the
-- text: the canonical cell tag is turned back into a `&...&` tag.

local ALIGN = {l = "AlignLeft", c = "AlignCenter", r = "AlignRight"}
local TEX_COMMAND = {l = "\\raggedright ", c = "\\centering ", r = "\\raggedleft "}

local BASE = FORMAT:match("^[^+-]+") or FORMAT
local KEEP = {
  gfm = true, markdown = true, markdown_strict = true, markdown_mmd = true, markdown_phpextra = true, markdown_github = true,
  commonmark = true, commonmark_x = true,
}
local TEX = {latex = true, beamer = true}
local HTMLISH = {html = true, html4 = true, html5 = true, epub = true, epub2 = true, epub3 = true, slidy = true, revealjs = true,
  s5 = true, slideous = true, dzslides = true}
local CSS_V = {t = "top", m = "middle", b = "bottom"}
local USE_TBLR = true      -- `-M pdfmd-tblr=off` (pdfmd sets it when LaTeX has no tabularray): vertical letters and sizes are then ignored in LaTeX
local GRID = false         -- `tablestyle: grid` in the metadata (nulabreport's key): a rebuilt table has every rule drawn, like the style's own tables
local DEFAULTS = {}        -- `-M pdfmd-table-align=` / `pdfmd-table-valign=`: the lowest tier

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

-- the inlines after the first one (and the space after it)
local function after_first(inlines)
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
  return rest
end

-- a cell's tag and the cell's inlines without it
local function take_tag(inlines)
  local tag = read_tag(inlines[1])
  if not tag then return nil end
  return tag, after_first(inlines)
end

-- the table's settings from the `<pt ...>` carrier in its first header cell (which is cut out), or nil
local function take_settings(tbl)
  local row = tbl.head.rows[1]
  local cell = row and row.cells[1]
  local block = cell and #cell.contents >= 1 and cell.contents[1] or nil
  if not block or (block.t ~= "Plain" and block.t ~= "Para") then return nil end
  local first = block.content[1]
  if not first or first.t ~= "RawInline" or not first.format:match("^html") then return nil end
  local body = first.text:match("^<pt ([^>]*)>$")
  if not body then return nil end
  local spec = {table = {}, cols = {}, rows = {}, needs = false, words = {}, natural = false}
  for word in body:gmatch("%S+") do
    spec.words[#spec.words + 1] = word
    if word == "nw" then spec.natural = true end
    local scope, key, value = word:match("^([cr]?%d*)(%a+)=(.+)$")
    if key then
      local target = spec.table
      local number = tonumber(scope:sub(2))
      if scope:sub(1, 1) == "c" and number then
        spec.cols[number] = spec.cols[number] or {}
        target = spec.cols[number]
      elseif scope:sub(1, 1) == "r" and number then
        spec.rows[number] = spec.rows[number] or {}
        target = spec.rows[number]
      end
      target[key] = value
      if key == "w" or key == "ht" or key == "v" then spec.needs = true end
    end
  end
  block.content = after_first(block.content)
  return spec
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

-- the value of a setting for the cell at row `r`, column `c`: its row, then its column
local function tier(spec, key, r, c)
  if not spec then return nil end
  return (spec.rows[r] and spec.rows[r][key]) or (spec.cols[c] and spec.cols[c][key])
end

-- the least height of row `r` (a CSS length), for the HTML writers
local function row_height(spec, r)
  return spec and ((spec.rows[r] and spec.rows[r].ht) or spec.table.ht) or nil
end

-- a merged cell's covered text was joined with a raw <br>; only HTML keeps that, so it becomes a real line break
local function line_breaks(inlines)
  local out = pandoc.Inlines{}
  for _, item in ipairs(inlines) do
    if item.t == "RawInline" and item.format:match("^html") and item.text:match("^<br%s*/?>$") then
      out:insert(pandoc.LineBreak())
    else
      out:insert(item)
    end
  end
  return out
end

local function fix_cell(cell, column, ctx)
  local single = #cell.contents == 1 and (cell.contents[1].t == "Plain" or cell.contents[1].t == "Para")
  local tag, rest
  if single then
    tag, rest = take_tag(cell.contents[1].content)
    rest = rest or cell.contents[1].content
  end
  if tag and tag.covered then
    if KEEP[BASE] then
      cell.contents = {pandoc.Plain(pandoc.Inlines{pandoc.RawInline(BASE, restore_text(tag))})}
    else
      cell.contents = {pandoc.Plain(pandoc.Inlines{})}
    end
    return tag
  end
  local effective = tag or {colspan = 1, rowspan = 1}
  local from_tiers = false
  if not effective.halign then
    local letter = tier(ctx.spec, "h", ctx.row, ctx.column)
    if not letter and column and column[1] == "AlignDefault" then
      letter = (ctx.spec and ctx.spec.table.h) or DEFAULTS.h
    end
    if letter and ALIGN[letter] then effective.halign = letter; from_tiers = true end
  end
  if not effective.valign then
    local letter = tier(ctx.spec, "v", ctx.row, ctx.column) or (ctx.spec and ctx.spec.table.v) or DEFAULTS.v
    if letter and CSS_V[letter] then effective.valign = letter; from_tiers = true end
  end
  if KEEP[BASE] then
    if not tag then return nil end
    local text = restore_text(tag)
    local kept = pandoc.Inlines{}
    if text then kept:insert(pandoc.RawInline(BASE, text)) end
    if text and #rest > 0 then kept:insert(pandoc.Space()) end
    kept:extend(rest)
    cell.contents = {pandoc.Plain(kept)}
    return tag
  end
  if not tag and not from_tiers and not (HTMLISH[BASE] and row_height(ctx.spec, ctx.row)) then return nil end
  if rest then rest = line_breaks(rest) end
  local letter = effective.halign
  local style = {}
  if effective.valign and (ctx.tblr or not TEX[BASE]) then
    cell.attr = pandoc.Attr("", {}, {valign = effective.valign})        -- longtblr reads it
    if HTMLISH[BASE] then style[#style + 1] = "vertical-align: " .. CSS_V[effective.valign] .. ";" end
  end
  if HTMLISH[BASE] and row_height(ctx.spec, ctx.row) then style[#style + 1] = "height: " .. row_height(ctx.spec, ctx.row) .. ";" end
  if #style > 0 then cell.attr = pandoc.Attr("", {}, {style = table.concat(style, " ")}) end
  if letter and ALIGN[letter] and TEX[BASE] and effective.colspan == 1 and not ctx.tblr and single then
    local width = column and column[2]
    local natural = width == nil or width == 0
    cell.contents = {pandoc.Plain(#rest > 0 and tex_wrap(letter, rest, natural) or pandoc.Inlines{})}
  else
    if letter and ALIGN[letter] then cell.alignment = ALIGN[letter] end
    if tag and single then cell.contents = {pandoc.Plain(rest)} end
  end
  if effective.colspan > 1 then cell.col_span = effective.colspan end
  if effective.rowspan > 1 then cell.row_span = effective.rowspan end
  return effective
end

-- one row of the input is a regular grid, so a cell's place in the row is its column; covered cells are dropped afterwards
local function fix_rows(rows, colspecs, ctx)
  for _, row in ipairs(rows) do
    ctx.row = ctx.row + 1
    local kept = {}
    for index, cell in ipairs(row.cells) do
      ctx.column = index
      local tag = fix_cell(cell, colspecs[index], ctx)
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

-- does LaTeX need tabularray for this table: a vertical alignment (a cell's tag, the table's settings or the default), a width, a height?
local function wants_tblr(tbl, spec)
  if not (USE_TBLR and TEX[BASE]) then return false end
  if DEFAULTS.v or (spec and spec.needs) then return true end
  local function scan(rows)
    for _, row in ipairs(rows) do
      for _, cell in ipairs(row.cells) do
        local block = #cell.contents >= 1 and cell.contents[1] or nil
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

-- a width word of the pre-pass as tabularray's: `3cm`, `30%` (of the text width), `*` (a share of what is left), `auto`
local function tblr_width(word)
  local percent = word:match("^([%d.]+)%%$")
  if percent then return string.format("%.4f\\linewidth", tonumber(percent) / 100) end
  return word
end

-- The table as a `longtblr` (tabularray), built from Pandoc's own table model: spans, widths, alignments, header rows, caption, label.
local function to_tblr(tbl, spec)
  local ncols = #tbl.colspecs
  local any_width, total = false, 0
  for _, colspec in ipairs(tbl.colspecs) do
    if colspec[2] and colspec[2] > 0 then any_width = true; total = total + colspec[2] end
  end
  local explicit, free = false, false
  for index = 1, ncols do
    if spec and spec.cols[index] and spec.cols[index].w then explicit = true end
  end
  local columns = {}
  for index, colspec in ipairs(tbl.colspecs) do
    local letter = TBLR_H[colspec[1]] or "l"
    local word = spec and spec.cols[index] and spec.cols[index].w
    if explicit then
      if word == "*" or not word then columns[index] = "X[1," .. letter .. "]"; free = true
      elseif word == "auto" then columns[index] = "Q[" .. letter .. "]"
      else columns[index] = "Q[" .. letter .. ",wd=" .. tblr_width(word) .. "]" end
    elseif any_width then
      columns[index] = string.format("X[%.4f,%s]", (colspec[2] and colspec[2] > 0) and colspec[2] or 0.05, letter)
    else
      columns[index] = "Q[" .. letter .. "]"
    end
  end
  local lines, cells, heights = {}, {}, {}
  local busy = {}
  for index = 1, ncols do busy[index] = 0 end
  local rownumber = 0
  local function emit(rows)
    for _, row in ipairs(rows) do
      rownumber = rownumber + 1
      local height = spec and ((spec.rows[rownumber] and spec.rows[rownumber].ht) or spec.table.ht)
      if height then heights[#heights + 1] = string.format("row{%d}={ht=%s}", rownumber, height) end
      local parts, taken, column = {}, 1, 1
      while column <= ncols do
        if busy[column] > 0 then
          busy[column] = busy[column] - 1
          parts[#parts + 1] = ""
          column = column + 1
        else
          local cell = row.cells[taken]
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
  if not GRID then lines[#lines + 1] = "\\toprule" end
  emit(tbl.head.rows)
  if #tbl.head.rows > 0 and not GRID then lines[#lines + 1] = "\\midrule" end
  for _, body in ipairs(tbl.bodies) do
    emit(body.head)
    emit(body.body)
  end
  emit(tbl.foot.rows)
  if not GRID then lines[#lines + 1] = "\\bottomrule" end
  local options = {}
  local caption = latex_of(tbl.caption.long)
  if caption ~= "" then
    options[#options + 1] = "caption={" .. caption .. "}"
    if tbl.attr.identifier ~= "" then options[#options + 1] = "label={" .. tbl.attr.identifier .. "}" end
  else
    -- no caption: tabularray would still print "Table N:" and step the counter; this is `\caption*{}`
    options[#options + 1] = "caption={},entry=none,label=none"
  end
  local edge = GRID and "" or "@{}"      -- a ruled grid keeps its padding at the outer edges, booktabs rules sit flush with the text
  local inner = {"colspec={" .. edge .. table.concat(columns) .. edge .. "}"}
  local table_width = spec and spec.table.w
  if table_width and table_width ~= "*" and table_width ~= "auto" then
    inner[#inner + 1] = "width=" .. tblr_width(table_width)
  elseif free then
    inner[#inner + 1] = "width=\\linewidth"
  elseif any_width and not explicit then
    inner[#inner + 1] = string.format("width=%.4f\\linewidth", total)
  end
  if #tbl.head.rows > 0 then inner[#inner + 1] = "rowhead=" .. #tbl.head.rows end
  if GRID then inner[#inner + 1] = "hlines,vlines" end
  inner[#inner + 1] = "cells={valign=h}"      -- every cell starts at the head of its row: a baseline cell (tabularray's default) beside a middle one misaligns
  for _, item in ipairs(heights) do inner[#inner + 1] = item end
  for _, item in ipairs(cells) do inner[#inner + 1] = item end
  local head = "\\begin{longtblr}" .. (#options > 0 and ("[" .. table.concat(options, ",") .. "]") or "")
    .. "{\n" .. table.concat(inner, ",\n") .. "}\n"
  return pandoc.RawBlock("latex", head .. table.concat(lines, "\n") .. "\n\\end{longtblr}")
end

-- percentage widths outside LaTeX: the AST's column widths (the other columns keep their proportions, scaled to what is left)
local function percent_widths(tbl, spec)
  if not spec then return end
  local count = #tbl.colspecs
  local fixed, taken = {}, 0
  for index = 1, count do
    local word = spec.cols[index] and spec.cols[index].w
    local percent = word and word:match("^([%d.]+)%%$")
    if percent then fixed[index] = tonumber(percent) / 100; taken = taken + fixed[index] end
  end
  if taken == 0 then return end
  local rest = 0
  for index, colspec in ipairs(tbl.colspecs) do
    if not fixed[index] then rest = rest + ((colspec[2] and colspec[2] > 0) and colspec[2] or 1 / count) end
  end
  for index, colspec in ipairs(tbl.colspecs) do
    if fixed[index] then
      colspec[2] = fixed[index]
    elseif rest > 0 then
      colspec[2] = math.max(0, 1 - taken) * ((colspec[2] and colspec[2] > 0) and colspec[2] or 1 / count) / rest
    end
  end
end

-- the Markdown writers keep the attribute line the user wrote: the carrier's words back in its spelling
local function attribute_line(spec)
  local names = {w = "width", ht = "height", h = "align", v = "valign"}
  local items = {}
  for _, word in ipairs(spec.words) do
    local scope, key, value = word:match("^([cr]?%d*)(%a+)=(.+)$")
    if key and names[key] then
      local prefix = ""
      if scope:sub(1, 1) == "c" and #scope > 1 then prefix = "col" .. scope:sub(2) .. "."
      elseif scope:sub(1, 1) == "r" and #scope > 1 then prefix = "row" .. scope:sub(2) .. "." end
      items[#items + 1] = prefix .. names[key] .. "=" .. value
    end
  end
  if #items == 0 then return nil end
  return "{" .. table.concat(items, " ") .. "}"
end

local function handle_table(tbl)
  local spec = take_settings(tbl)
  if spec and spec.natural then
    -- the tags made a line longer than Pandoc's column limit, and it read the dashes as widths: the table as it would have been without them
    for index, colspec in ipairs(tbl.colspecs) do tbl.colspecs[index] = {colspec[1]} end
  end
  local tblr = wants_tblr(tbl, spec)
  local ctx = {tblr = tblr, spec = spec, row = 0, column = 0}
  fix_rows(tbl.head.rows, tbl.colspecs, ctx)
  for _, body in ipairs(tbl.bodies) do
    fix_rows(body.head, tbl.colspecs, ctx)
    fix_rows(body.body, tbl.colspecs, ctx)
  end
  fix_rows(tbl.foot.rows, tbl.colspecs, ctx)
  if not KEEP[BASE] and has_spans(tbl) then promote_header(tbl) end
  if KEEP[BASE] and spec then
    local line = attribute_line(spec)
    if line then return {tbl, pandoc.RawBlock(BASE, line)} end
    return tbl
  end
  if tblr then return to_tblr(tbl, spec) end
  if not KEEP[BASE] then percent_widths(tbl, spec) end
  return tbl
end

return {
  {
    Pandoc = function(doc)
      local function setting(name)
        local value = doc.meta[name]
        return value and pandoc.utils.stringify(value) or nil
      end
      GRID = (setting("tablestyle") or ""):lower() == "grid"
      if setting("pdfmd-tblr") == "off" then USE_TBLR = false end
      local h, v = setting("pdfmd-table-align"), setting("pdfmd-table-valign")
      DEFAULTS.h = h and h:sub(1, 1):lower() or nil
      DEFAULTS.v = v and v:sub(1, 1):lower() or nil
      return pandoc.Pandoc(doc.blocks:walk({Table = handle_table}), doc.meta)
    end,
  },
}
