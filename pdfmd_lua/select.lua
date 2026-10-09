-- pdfmd: keep only the selected parts of a document that was numbered whole (v3.26.2).
--
-- A part built alone for HTML, Word, OpenDocument or Typst is handed to Pandoc together with all the others, each one
-- wrapped in a fenced div `{.pdfmd-part pdfmd-keep="yes|no"}`, so pandoc-crossref numbers and resolves everything as in
-- the full document. This filter runs right after it (and before citeproc): the parts marked "no" are dropped, the
-- ones marked "yes" are unwrapped. A reference in a kept part to something in a dropped part has its number already,
-- as a link that leads nowhere.
--
-- The writer numbers headings (--number-sections) by what it is left with, so a kept heading would restart at 1: this
-- numbers every heading of the whole document first, as Pandoc does, and leaves the number on the heading, which the
-- HTML, Word and OpenDocument writers print as it is.

local function number_headings(doc)
  local options = PANDOC_WRITER_OPTIONS
  if not (options and options.number_sections) then
    return doc
  end
  local counters = { 0, 0, 0, 0, 0, 0 }
  -- the blocks only: the metadata holds headings too (pandoc-crossref's "List of Figures" titles)
  local walked = pandoc.walk_block(pandoc.Div(doc.blocks), {
    Header = function(header)
      if header.classes:includes("unnumbered") or header.attributes.number then
        return nil
      end
      local level = math.min(header.level, 6)
      counters[level] = counters[level] + 1
      for deeper = level + 1, 6 do
        counters[deeper] = 0
      end
      local parts = {}
      for index = 1, level do
        parts[#parts + 1] = tostring(counters[index])
      end
      header.attributes.number = table.concat(parts, ".")
      return header
    end,
  })
  doc.blocks = walked.content
  return doc
end

-- Typst numbers headings itself, from its own counter: before each kept heading set the counter to one less than the
-- heading's number, so Typst arrives at the number the whole document gave it.
local function typst_counter(header)
  local number = header.attributes.number
  if not number then
    return nil
  end
  local values = {}
  for part in number:gmatch("[^.]+") do
    values[#values + 1] = tonumber(part) or 0
  end
  values[#values] = values[#values] - 1
  local items = {}
  for _, value in ipairs(values) do
    items[#items + 1] = tostring(value)
  end
  return pandoc.RawBlock("typst", "#counter(heading).update((" .. table.concat(items, ", ") .. ",))")
end

local function unwrap(content)
  if FORMAT ~= "typst" then
    return content
  end
  local blocks = pandoc.List()
  for _, block in ipairs(content) do
    if block.t == "Header" then
      local counter = typst_counter(block)
      if counter then
        blocks:insert(counter)
      end
    end
    blocks:insert(block)
  end
  return blocks
end

function Pandoc(doc)
  doc = number_headings(doc)
  local blocks = pandoc.List()
  for _, block in ipairs(doc.blocks) do
    if block.t == "Div" and block.classes:includes("pdfmd-part") then
      if block.attributes["pdfmd-keep"] == "yes" then
        blocks:extend(unwrap(block.content))
      end
    else
      blocks:insert(block)
    end
  end
  doc.blocks = blocks
  return doc
end
