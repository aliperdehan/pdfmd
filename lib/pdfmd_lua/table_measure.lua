-- Loaded for table_width.lua's dump role and the final Typst filter's old-writer compatibility. Keep cell
-- inlines in the AST so the writer discovers packages/macros (strikeout, maths, highlighting and graphics).
local M = {}

local HEADER = [[
\makeatletter
\newcommand{\pdfmdtrim}{\ifdim\lastskip=0pt\else\unskip\expandafter\pdfmdtrim\fi}
\newwrite\pdfmdwidthfile
\immediate\openout\pdfmdwidthfile=\jobname.pdfmdwidths
\newcommand{\pdfmdtable}[1]{\immediate\write\pdfmdwidthfile{T #1 \strip@pt\linewidth\space \strip@pt\dimexpr2\tabcolsep\relax}}
\newcommand{\pdfmdmeasure}[4]{\begingroup\let\par\space\setbox0=\hbox{\ignorespaces#4\pdfmdtrim}\immediate\write\pdfmdwidthfile{C #1 #2 #3 \strip@pt\wd0}\endgroup}
\newcommand{\pdfmdword}[4]{\begingroup\let\par\space\setbox0=\hbox{\ignorespaces#4\pdfmdtrim}\immediate\write\pdfmdwidthfile{W #1 #2 #3 \strip@pt\wd0}\endgroup}
\AtEndDocument{\immediate\closeout\pdfmdwidthfile}
\makeatother
]]

-- Split on breakable whitespace, preserving formatting around every resulting fragment. Raw commands, images
-- and maths are indivisible; they must be measured by the engine rather than by their source spelling.
local function pieces(inlines)
  local out = {}
  for _, inline in ipairs(inlines) do
    if inline.t == "Space" or inline.t == "SoftBreak" or inline.t == "LineBreak" then
      out[#out + 1] = false
    elseif inline.content and inline.t ~= "Image" then
      local pending = pandoc.List()
      local function flush()
        if #pending > 0 then
          local clone = inline:clone()
          clone.content = pending
          out[#out + 1] = clone
          pending = pandoc.List()
        end
      end
      for _, child in ipairs(pieces(inline.content)) do
        if child == false then flush(); out[#out + 1] = false else pending:insert(child) end
      end
      flush()
    else
      out[#out + 1] = inline
    end
  end
  return out
end

-- A writer export keeps relative image paths, unlike Pandoc's PDF route. Give the measuring source stable,
-- content-addressed copies beside its cache; both cells and word fragments can then find the same picture.
local function measurement_image(directory)
  return function(image)
    if not directory then return nil end
    local ok, mime, bytes = pcall(pandoc.mediabag.fetch, image.src)
    if not ok or not bytes then return nil end
    local extensions = {["image/png"] = ".png", ["image/jpeg"] = ".jpg", ["image/svg+xml"] = ".svg",
                        ["application/pdf"] = ".pdf", ["image/gif"] = ".gif"}
    local extension = extensions[mime] or image.src:match("(%.[A-Za-z0-9]+)$") or ""
    local path = pandoc.path.join({directory, pandoc.utils.sha1(bytes) .. extension})
    local existing = io.open(path, "rb")
    local intact = false
    if existing then intact = existing:read("*a") == bytes; existing:close() end
    if not intact then
      local output = assert(io.open(path, "wb"))
      output:write(bytes)
      output:close()
    end
    image.src = path
    return image
  end
end

-- Probe what the selected writer overrides: Pandoc 3.1.3 writes an explicit inset, while newer writers
-- inherit the template's table.inset. Use its expression rather than copying a version-specific default.
local function typst_inset()
  local probe = pandoc.read("| A |\n|---|\n| a |\n", "markdown")
  return pandoc.write(probe, "typst"):match("\n[ ]*inset: ([^\n]+),")
end

-- The old writer emits only a column count, ignoring colspec widths. Run at the final Typst filter so cell
-- conversions, pictures and labels have already been handled; keep the writer's own table/caption spelling.
function M.typst_widths(tbl)
  if not tbl.attributes["data-pdfmd-measured"] then return nil end
  local columns = {}
  for _, spec in ipairs(tbl.colspecs) do
    if spec[2] == nil then return nil end
    columns[#columns + 1] = string.format("%.8f%%", 100 * spec[2])
  end
  local source = pandoc.write(pandoc.Pandoc({tbl}), "typst")
  local changed
  source, changed = source:gsub("(\n[ ]*columns: )[0-9]+,", function(prefix)
    return prefix .. "(" .. table.concat(columns, ", ") .. "),"
  end, 1)
  return changed > 0 and source or nil
end

function M.dump(doc, options)
  local typst = FORMAT:match("typst") ~= nil
  local format = typst and "typst" or "latex"
  local inset = typst and typst_inset()
  local blocks = pandoc.List()
  if not typst then blocks:insert(pandoc.RawBlock("latex", HEADER)) end
  local assets = doc.meta["pdfmd-measure-assets"]
  local image = measurement_image(assets and pandoc.utils.stringify(assets))
  local number = 0
  local function table_dump(tbl)
    number = number + 1
    local o = options(tbl.attr.attributes)
    if o.estimate ~= "measure" or o.mode == "keep" or tbl.attr.attributes["data-pdfmd-widths"] == "fixed" then return end
    if typst then
      local n = #tbl.colspecs
      local cells = string.rep("[],", n)
      local probe = string.format("table(columns: %d, %s%s)", n, inset and "inset: " .. inset .. ", " or "", cells)
      local padding = "measure(box(inset: " .. (inset or "table.inset") .. ", [])).width"
      blocks:insert(pandoc.RawBlock("typst", string.format([[
#layout(pdfmd-size => context [
#metadata((kind: "T", table: "%d", line: pdfmd-size.width / 1pt,
  sep: measure(%s).width / 1pt / %d,
  inset: %s / 1pt,
  gutter: (measure(%s).width - %d * %s) / 1pt)) <pdfmd-measure>
]], number, probe, n, padding, probe, n, padding)))
    else
      blocks:insert(pandoc.RawBlock("latex", "\\pdfmdtable{" .. number .. "}"))
    end
    local row_number = 0
    local function emit(kind, col, contents)
      if typst then
        blocks:insert(pandoc.RawBlock("typst", string.format(
          '#metadata((kind: "%s", table: "%d", row: %d, col: %d, width: measure([',
          kind == "pdfmdmeasure" and "C" or "W", number, row_number, col)))
      else
        blocks:insert(pandoc.RawBlock("latex", string.format("\\%s{%d}{%d}{%d}{", kind, number, row_number, col)))
      end
      for _, block in ipairs(contents) do blocks:insert(block) end
      blocks:insert(pandoc.RawBlock(format, typst and ']).width / 1pt)) <pdfmd-measure>' or "}"))
    end
    local function row_dump(row)
      row_number = row_number + 1
      for col, cell in ipairs(row.cells) do
        cell.contents = cell.contents:walk({Image = image})
        emit("pdfmdmeasure", col, cell.contents)
        local word = pandoc.List()
        local function flush()
          if #word > 0 then emit("pdfmdword", col, {pandoc.Plain(word)}); word = pandoc.List() end
        end
        for _, block in ipairs(cell.contents) do
          if block.content and (block.t == "Plain" or block.t == "Para") then
            for _, part in ipairs(pieces(block.content)) do
              if part == false then flush() else word:insert(part) end
            end
          end
          flush()
        end
      end
    end
    for _, row in ipairs(tbl.head.rows) do row_dump(row) end
    for _, body in ipairs(tbl.bodies) do
      for _, row in ipairs(body.head) do row_dump(row) end
      for _, row in ipairs(body.body) do row_dump(row) end
    end
    for _, row in ipairs(tbl.foot.rows) do row_dump(row) end
    if typst then blocks:insert(pandoc.RawBlock("typst", "])")) end
  end
  doc.blocks:walk({Table = table_dump})
  return pandoc.Pandoc(blocks, doc.meta)
end

return M
