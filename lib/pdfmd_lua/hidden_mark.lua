-- Preserve hidden containers around the content filters: calc and macros still read them.
local function plain(element)
  return (element.classes:includes("hide") or element.classes:includes("hidden"))
    and not (element.tag == "Div" and element.classes:includes("calc"))
end
return {{Pandoc = function(doc)
  local shown = doc.meta["pdfmd-show-hidden"] == true
  local labels, used = {}, {}
  local function label(el)
    if el.identifier and el.identifier ~= "" then labels[el.identifier] = true end
  end
  local function raw_labels(el)
    for id in el.text:gmatch("\\label{([^}]+)}") do labels[id] = true end
  end
  local function references(el)
    for command, ids in el.text:gmatch("\\([%a]+)%*?{([^}]+)}") do
      if command == "ref" or command == "eqref" or command == "autoref" or command == "cref"
        or command == "Cref" or command == "pageref" or command == "nameref" or command == "vref" then
        for id in ids:gmatch("[^,%s]+") do used[id] = true end
      end
    end
  end
  local function skip_hidden(el)
    if plain(el) and not shown then return el, false end
  end
  doc:walk({traverse = "topdown", Div = skip_hidden, Span = skip_hidden, Link = function(el)
    if el.target:sub(1, 1) == "#" then
      used[(el.target:sub(2):gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end))] = true
    end
  end, Cite = function(el)
    for _, cite in ipairs(el.citations) do used[cite.id] = true end
  end, RawInline = references, RawBlock = references})
  local function mark(element)
    if not plain(element) then return nil end
    local classes = pandoc.List()
    for _, class in ipairs(element.classes) do
      if class ~= "hide" and class ~= "hidden" then classes:insert(class) end
    end
    element.classes = classes
    if shown then return element end
    label(element)
    element:walk({Header = label, Div = label, Span = label, Figure = label, Table = label,
      CodeBlock = label, Image = label, RawInline = raw_labels, RawBlock = raw_labels,
      Str = function(el) for id in el.text:gmatch("{#([^}]+)}") do labels[id] = true end end})
    -- The wrapper survives filters that replace the original div/span.
    local attr = pandoc.Attr("", {"pdfmd-hidden-content"})
    if element.tag == "Div" then return pandoc.Div({element}, attr) end
    return pandoc.Span({element}, attr)
  end
  doc = doc:walk({Div = mark, Span = mark})
  local dangling = {}
  for id in pairs(labels) do if used[id] then dangling[#dangling + 1] = id end end
  table.sort(dangling)
  if #dangling > 0 then
    io.stderr:write("WARN  hidden: referenced label(s) " .. table.concat(dangling, ", ")
      .. " are hidden; references will dangle\n")
    doc.meta["pdfmd-hidden-labels"] = pandoc.MetaList(dangling)
  end
  return doc
end}}
