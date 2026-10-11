-- pdfmd: what Typst needs that Pandoc's Typst writer does not give it (v3.27.11). Runs last before the writer.
--
-- Links to anchors that are not in the document. LaTeX and HTML only warn about a link to an id nothing carries; Typst
-- stops the build ("label <x> does not exist in the document"). A pasted transcript that quotes another document's
-- `(see 13.5)` links is enough. Each such link becomes its text, and one WARN says which. Pandoc's Typst writer gives a
-- label to a heading, a div, a span, a figure and a table with an id (Pandoc 3.1.3 and 3.12 alike); a code block, an
-- image, inline code and a link keep theirs only in the AST, so a link to one of those is made text as well.
--
-- A label on two elements stops Typst too ("label <x> occurs multiple times", v3.28.2: a lab report through pdfmd's
-- LaTeX filter, where a drawn figure environment and its own label both carried it): the first keeps it, one WARN.
--
-- Pictures, with a Pandoc before 3.2 building a PDF: it runs Typst in its own working folder (a discovered metadata
-- file's, not always the document's) without fetching the pictures first, so a relative path is looked for there. Each
-- is made the absolute path of the file found on the resource path (pdfmd gives Typst --root=/ with such a Pandoc).

if not FORMAT:match("^typst") then return {} end

local LABELLED = {Header = true, Div = true, Span = true, Figure = true, Table = true}

local function decoded(text)
  return (text:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end))
end

local function plain_missing_links(doc)
  local labels, repeated = {}, {}
  local function collect(element)
    local identifier = element.identifier
    if not identifier or identifier == "" then return nil end
    if labels[identifier] then
      repeated[#repeated + 1] = identifier
      element.identifier = ""
      return element
    end
    labels[identifier] = true
  end
  local collector = {traverse = "topdown"}            -- in the order of the document: the first one keeps its label
  for name in pairs(LABELLED) do collector[name] = collect end
  doc = doc:walk(collector)
  if #repeated > 0 then
    local shown = {}
    for index = 1, math.min(#repeated, 5) do shown[index] = repeated[index] end
    io.stderr:write(string.format("WARN  typst: %d label%s on more than one element (%s%s): only the first keeps it, "
      .. "Typst stops on a label used twice\n", #repeated, #repeated == 1 and "" or "s", table.concat(shown, ", "),
      #repeated > 5 and string.format(" and %d more", #repeated - 5) or ""))
  end

  local missing, order = {}, {}
  doc = doc:walk({Link = function(link)
    local target = link.target
    if target:sub(1, 1) ~= "#" or #target < 2 or labels[target:sub(2)] or labels[decoded(target:sub(2))] then
      return nil
    end
    if not missing[target] then
      missing[target] = 0
      order[#order + 1] = target
    end
    missing[target] = missing[target] + 1
    return link.content
  end})

  if #order > 0 then
    local count = 0
    for _, target in ipairs(order) do count = count + missing[target] end
    local shown = {}
    for index = 1, math.min(#order, 5) do shown[index] = order[index] end
    io.stderr:write(string.format("WARN  typst: %d link%s to anchors that are not in the document (%s%s) %s plain text: "
      .. "Typst stops on a link to a missing label\n", count, count == 1 and "" or "s", table.concat(shown, ", "),
      #order > 5 and string.format(" and %d more", #order - 5) or "", count == 1 and "was made" or "were made"))
  end
  return doc
end

local function readable(path)
  local handle = io.open(path, "rb")
  if handle then handle:close() return true end
  return false
end

local function absolute_pictures(doc)
  local output = (PANDOC_STATE.output_file or ""):lower()
  if not (PANDOC_VERSION < {3, 2}) or not output:match("%.pdf$") then return doc end
  local here = pandoc.system.get_working_directory()
  local folders = PANDOC_STATE.resource_path or {"."}
  return doc:walk({Image = function(image)
    local src = image.src
    if src == "" or src:match("^%a[%w+.-]*:") or pandoc.path.is_absolute(src) then return nil end
    for _, folder in ipairs(folders) do
      for _, name in ipairs({src, decoded(src)}) do
        local candidate = pandoc.path.join({folder, name})
        if not pandoc.path.is_absolute(candidate) then candidate = pandoc.path.join({here, candidate}) end
        if readable(candidate) then
          image.src = pandoc.path.normalize(candidate)
          return image
        end
      end
    end
  end})
end

return {{Pandoc = function(doc) return absolute_pictures(plain_missing_links(doc)) end}}
