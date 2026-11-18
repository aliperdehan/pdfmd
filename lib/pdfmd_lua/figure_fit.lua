-- Mark the writer's figures after the other filters have finished. Keep their native images in the
-- AST so Pandoc still resolves resources, emits captions and labels, and detects the need for graphicx.
local here = PANDOC_SCRIPT_FILE:gsub("[^/\\]*$", "")

local function read(name)
  local file = assert(io.open(here .. name, "r"))
  local code = file:read("*a")
  file:close()
  return code
end

local function flag(value)
  value = value and pandoc.utils.stringify(value):lower():match("^%s*(.-)%s*$")
  if value == "on" or value == "true" or value == "yes" then return true end
  if value == "off" or value == "false" or value == "no" then return false end
  return nil
end

local function pictures(block)
  local count, override = 0, nil
  block:walk({Image = function(image)
    count = count + 1
    if override == nil then override = flag(image.attributes.fit) end
  end, RawInline = function(inline)
    -- A sized Obsidian embed can already be a graphicx call by this stage.
    if inline.format == "latex" and inline.text:match("^\\includegraphics") then count = count + 1 end
  end})
  return count, override
end

local function hex(value)
  return (value:gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

function Pandoc(doc)
  if FORMAT ~= "latex" and FORMAT ~= "typst" then return end
  local enabled = flag(doc.meta["pdfmd-figure-fit"]) ~= false
  local checking = flag(doc.meta["pdfmd-figure-check"]) == true
  local raw = function(text) return pandoc.RawBlock(FORMAT, text) end
  local count, used = 0, false

  local function identify(element, caption)
    count = count + 1
    local name = element.identifier
    if name == "" then
      name = pandoc.utils.stringify(caption):gsub("%s+", " "):match("^%s*(.-)%s*$")
      name = pandoc.text.sub(name, 1, 60):gsub("%s+$", "")
    end
    local encoded = hex(name)
    local pieces = {}
    for start = 1, #encoded, 16 do table.insert(pieces, encoded:sub(start, start + 15)) end
    if #pieces == 0 then pieces = {""} end
    used = true
    return tostring(count), pieces
  end

  local function opted_in(override)
    if override == nil then return enabled end
    return override
  end

  local function typst_arguments(on, number, pieces)
    return tostring(on) .. ', ("' .. number .. '", "' .. table.concat(pieces, '", "') .. '",)'
  end

  local filter = {traverse = "topdown"}
  function filter.Figure(figure)
    local images, override = pictures(pandoc.Div(figure.content))
    local on = opted_in(override)
    -- Typst also measures figures whose size the document asks to keep.
    if images == 0 or #figure.caption.long == 0 or not (on or checking or FORMAT == "typst") then return figure, false end
    local number, pieces = identify(figure, figure.caption.long)
    if FORMAT == "latex" then
      local messages = {}
      for index, piece in ipairs(pieces) do
        table.insert(messages, "\\pdfmdFitMessage{\\pdfmdFitStatus-" .. number .. "-" .. index .. "-" .. piece .. "}")
      end
      local start = "\\pdfmdFitBegin{" .. table.concat(messages) .. "}{" .. (on and "1" or "0") .. "}"
      return {raw(start), figure, raw("\\pdfmdFitEnd")}, false
    end
    local arguments = typst_arguments(on, number, pieces)
    return {raw("#["), raw("#show figure: pdfmd-fit.with(" .. arguments .. ")"), figure, raw("]")}, false
  end

  if FORMAT == "typst" then
    function filter.Div(div)
      local body = div.content[1]
      if not div.identifier:match("^fig[:-]") or #div.content < 2 or
          not (body.t == "Para" or body.t == "Plain") then return end
      local images = 0
      for _, inline in ipairs(body.content) do
        if inline.t == "Image" then images = images + 1
        elseif inline.t ~= "Space" and inline.t ~= "SoftBreak" and inline.t ~= "LineBreak" then return end
      end
      if images < 2 then return end
      local _, override = pictures(body)
      local on = opted_in(override)
      local number, pieces = identify(div, div.content[2])
      local arguments = typst_arguments(on, number, pieces)
      local blocks = pandoc.Blocks({raw("#pdfmd-fit-group(" .. arguments .. ", ["), body, raw("], [")})
      for index = 2, #div.content do blocks:insert(div.content[index]) end
      blocks:insert(raw("])"))
      div.content = blocks
      return div, false
    end

    local function plain(block)
      if not enabled then return end
      local sized = false
      block:walk({Image = function(image)
        sized = sized or image.attributes.height ~= nil or image.attributes.width ~= nil
      end})
      -- Typst already constrains images that have neither an explicit width nor height.
      if not sized then return end
      used = true
      return {raw("#pdfmd-fit-plain["), block, raw("]")}, false
    end
    filter.Para, filter.Plain = plain, plain
  end

  doc.blocks = doc.blocks:walk(filter)
  if used then
    local extension = FORMAT == "latex" and "tex" or "typ"
    doc.blocks:insert(1, raw(read("figure_fit." .. extension)))
  end
  return doc
end
