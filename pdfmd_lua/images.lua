-- pdfmd: the images a LaTeX engine cannot read. pdfmd converts each SVG a document names (once, kept by content) and
-- passes the map, as written in the document -> the PDF, in the metadata field `pdfmd-image-map`; this filter puts the
-- PDF where the document named the SVG: a Markdown image, a raw `\includegraphics{a.svg}`, a raw `\includesvg{a}`.

local map = {}

local function lookup(path)
  local found = map[path]
  if found then return found end
  -- \includesvg takes the name without the extension
  return map[path .. ".svg"]
end

local function latex_path(path)
  -- spaces and the like are fine inside graphicx's braces; a percent sign or a hash would not be
  return (path:gsub("([%%#])", "\\%1"))
end

local function rewrite(text)
  local changed = false
  local function swap(command)
    return function(options, path)
      local replaced = lookup((path:gsub("^%s+", ""):gsub("%s+$", "")))
      if not replaced then return nil end
      changed = true
      return "\\includegraphics" .. (options or "") .. "{" .. latex_path(replaced) .. "}"
    end
  end
  local out = text:gsub("\\includegraphics%s*(%b[])%s*(%b{})", function(options, braces)
    return swap("includegraphics")(options, braces:sub(2, -2)) or nil
  end)
  out = out:gsub("\\includegraphics%s*(%b{})", function(braces)
    local result = swap("includegraphics")(nil, braces:sub(2, -2))
    return result or nil
  end)
  out = out:gsub("\\includesvg%s*(%b[])%s*(%b{})", function(options, braces)
    return swap("includesvg")(options, braces:sub(2, -2)) or nil
  end)
  out = out:gsub("\\includesvg%s*(%b{})", function(braces)
    local result = swap("includesvg")(nil, braces:sub(2, -2))
    return result or nil
  end)
  return out, changed
end

local function raw(element)
  if element.format ~= "latex" and element.format ~= "tex" then return nil end
  local text, changed = rewrite(element.text)
  if changed then element.text = text; return element end
  return nil
end

function Pandoc(doc)
  local given = doc.meta["pdfmd-image-map"]
  if type(given) ~= "table" then return nil end
  for key, value in pairs(given) do
    if type(key) == "string" then map[key] = pandoc.utils.stringify(value) end
  end
  return doc:walk({
    Image = function(image)
      local replaced = map[image.src]
      if replaced then image.src = replaced; return image end
      return nil
    end,
    RawBlock = raw,
    RawInline = raw,
  })
end
