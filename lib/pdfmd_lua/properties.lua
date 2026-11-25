-- Display rows derived from the document's YAML, before Pandoc changes
-- boolean spelling, date values, or the front-matter order.
local file = assert(io.open(PANDOC_SCRIPT_FILE .. ".json", "rb"))
local config = pandoc.json.decode(file:read("*a"))
file:close()

local slides = {
  beamer = true, revealjs = true, pptx = true, slidy = true, s5 = true, slideous = true, dzslides = true,
}

local function text(value)
  local items = pandoc.List()
  for word in value:gmatch("%S+") do
    if #items > 0 then items:insert(pandoc.Space()) end
    items:insert(pandoc.Str(word))
  end
  return items
end

local function word_style(blocks)
  return pandoc.Div(blocks, pandoc.Attr("", {}, {["custom-style"] = "Properties"}))
end

local function table_cell(value)
  local words = text(value)
  if FORMAT == "docx" then return {word_style({pandoc.Para(words)})} end
  return {pandoc.Plain(words)}
end

local function content()
  if config.style == "inline" then
    local line = pandoc.List()
    for _, row in ipairs(config.rows) do
      local item = text(row[3] and row[2] or row[1])
      if not row[3] and row[2] ~= "" then
        if #item > 0 then item:insert(pandoc.Space()) end
        item:extend(text(row[2]))
      end
      if #item > 0 then
        if #line > 0 then line:extend({pandoc.Space(), pandoc.Str("·"), pandoc.Space()}) end
        line:extend(item)
      end
    end
    return {pandoc.Para(line)}
  end

  if config.style == "list" then
    local items = pandoc.List()
    for _, row in ipairs(config.rows) do
      local sentence = pandoc.List({pandoc.Strong(text(row[1]))})
      if row[2] ~= "" then
        sentence:extend({pandoc.Str(":"), pandoc.Space()})
        sentence:extend(text(row[2]))
      end
      items:insert({pandoc.Plain(sentence)})
    end
    return {pandoc.BulletList(items)}
  end
  local rows = pandoc.List()
  for _, row in ipairs(config.rows) do
    rows:insert({table_cell(row[1]), table_cell(row[2])})
  end
  return {pandoc.utils.from_simple_table(pandoc.SimpleTable(
    {}, {pandoc.AlignDefault, pandoc.AlignDefault}, {0, 0}, {}, rows))}
end

local function include_header(meta, format, value, first)
  local headers = meta["header-includes"]
  if not headers then
    headers = pandoc.MetaList({})
  elseif pandoc.utils.type(headers) ~= "List" then
    headers = pandoc.MetaList({headers})
  end
  local header = pandoc.MetaBlocks({pandoc.RawBlock(format, value)})
  headers:insert(first and 1 or #headers + 1, header)
  meta["header-includes"] = headers
end

function Pandoc(doc)
  if slides[FORMAT] and not config.own then return nil end

  local block = content()
  if FORMAT == "latex" or FORMAT == "beamer" then
    include_header(doc.meta, "latex", [[
\ifcsname pdfmdproperties\endcsname\else
  \newenvironment{pdfmdproperties}{}{}
\fi]], false)
    table.insert(block, 1, pandoc.RawBlock("latex", "\\begin{pdfmdproperties}"))
    table.insert(block, pandoc.RawBlock("latex", "\\end{pdfmdproperties}"))
  elseif FORMAT == "typst" then
    include_header(doc.meta, "typst", "#let pdfmd-properties(body) = body", true)
    table.insert(block, 1, pandoc.RawBlock("typst", "#pdfmd-properties["))
    table.insert(block, pandoc.RawBlock("typst", "]"))
  elseif FORMAT == "docx" then
    block = {word_style(block)}
  elseif FORMAT:match("^html") or FORMAT == "revealjs" or FORMAT:match("^epub") then
    block = {pandoc.Div(block, pandoc.Attr("", {"pdfmd-properties"}))}
  end

  if config.place == "end" then
    doc.blocks:extend(block)
  else
    for index = #block, 1, -1 do doc.blocks:insert(1, block[index]) end
  end
  return doc
end
