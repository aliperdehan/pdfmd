-- Loaded by table_width.lua only for its dump role. Keep cell inlines in the AST so Pandoc's writer discovers
-- their packages and macros (strikeout, maths, highlighting and graphics) as it does for the real table.
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

function M.dump(doc, options)
  local blocks = pandoc.List({pandoc.RawBlock("latex", HEADER)})
  local number = 0
  local function table_dump(tbl)
    number = number + 1
    local o = options(tbl.attr.attributes)
    if o.estimate ~= "measure" or o.mode == "keep" or tbl.attr.attributes["data-pdfmd-widths"] == "fixed" then return end
    blocks:insert(pandoc.RawBlock("latex", "\\pdfmdtable{" .. number .. "}"))
    local row_number = 0
    local function emit(kind, col, contents)
      blocks:insert(pandoc.RawBlock("latex", string.format("\\%s{%d}{%d}{%d}{", kind, number, row_number, col)))
      for _, block in ipairs(contents) do blocks:insert(block) end
      blocks:insert(pandoc.RawBlock("latex", "}"))
    end
    local function row_dump(row)
      row_number = row_number + 1
      for col, cell in ipairs(row.cells) do
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
  end
  doc.blocks:walk({Table = table_dump})
  return pandoc.Pandoc(blocks, doc.meta)
end

return M
