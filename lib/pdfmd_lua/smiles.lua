-- pdfmd: chemical structures written as text (v3.31.42, pdfmd_smiles has the drawing). A fenced block or a div of class `smiles`
--
--     ```smiles                         ::: {.smiles caption="Aspirin" file="aspirin.mol"}
--     CC(=O)Oc1ccccc1C(=O)O ASA         :::
--     ```
--
-- is drawn as a picture in the format the output takes (a PDF for LaTeX, an SVG for HTML and Typst, a PNG for Word and
-- OpenDocument unless `office-format` says SVG, an SVG beside the output for flat Markdown) and takes the block's place;
-- with `caption="..."` it is a figure (`{#fig:id}` works with pandoc-crossref). The body is one structure per line (a name after
-- the SMILES is written under it), or a molfile / SD file / Tripos mol2 / InChI (`kind=` says which; it is read from the text or
-- the file's extension otherwise), or `file="x.mol"` names a file beside the document. Block attributes are the settings of
-- `pdfmd-options.smiles` (engine, format, office-format, palette, cell-width, cell-height, columns, bond-length, dpi) and `width=`.
--
-- Every block of a document is drawn by ONE call of `python3 pdfmd_smiles` (RDKit is imported once). Where the drawing cannot be
-- done (RDKit missing, a structure that does not read) the block stays as it is, with one warning.
--
-- Configuration arrives as metadata written by pdfmd: `pdfmd-smiles` (the resolved settings), `pdfmd-smiles-python` (the
-- interpreter), `pdfmd-smiles-dir` (the pdfmd_smiles folder) and the keys diagram.lua reads (`pdfmd-raw-cache`, `pdfmd-raw-rel`,
-- `pdfmd-flat`).

local FAMILY = {
  latex = "tex", beamer = "tex", context = "tex",
  typst = "typst",
  html = "html", html4 = "html", html5 = "html", epub = "html", epub2 = "html", epub3 = "html", slidy = "html",
  slideous = "html", revealjs = "html", s5 = "html", dzslides = "html", chunkedhtml = "html",
  docx = "office", odt = "office", opendocument = "office", pptx = "office", openxml = "office",
  gfm = "md",
}
local family = FAMILY[FORMAT] or (FORMAT:match("^html") and "html") or nil

local cache_dir, cache_rel = nil, nil
local flat = false
local warned = {}

local function warn(key, message)
  if not warned[key] then
    warned[key] = true
    io.stderr:write("WARN  smiles: " .. message .. "\n")
  end
end

local function read_file(path)
  local handle = io.open(path, "rb")
  if not handle then return nil end
  local data = handle:read("a")
  handle:close()
  return data
end

-- Base64, for a picture inside an HTML file (so that the file can be moved or sent without a folder beside it).
local B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local function base64(data)
  local out = {}
  for index = 1, #data, 3 do
    local a, b, c = data:byte(index, index + 2)
    local n = a * 65536 + (b or 0) * 256 + (c or 0)
    local c1, c2, c3, c4 = (n >> 18) & 63, (n >> 12) & 63, (n >> 6) & 63, n & 63
    out[#out + 1] = B64:sub(c1 + 1, c1 + 1) .. B64:sub(c2 + 1, c2 + 1)
      .. (b and B64:sub(c3 + 1, c3 + 1) or "=") .. (c and B64:sub(c4 + 1, c4 + 1) or "=")
  end
  return table.concat(out)
end
local MIME = {svg = "image/svg+xml", png = "image/png"}

local function link_to(path)
  if cache_rel then return cache_rel .. "/" .. path:match("[^/\\]+$") end
  local suffix = path:match("%.(%w+)$")
  if FORMAT:match("^html") and MIME[suffix] then        -- an HTML file carries its pictures (EPUB takes the files)
    local data = read_file(path)
    if data and #data < 3000000 then return "data:" .. MIME[suffix] .. ";base64," .. base64(data) end
  end
  return path
end

-- The text of inlines as it was written: Pandoc reads `[N+](=O)` as a link and `[O-]` as text, and a structure written
-- in a div has to come back as the author typed it.
local function inlines_source(inlines)
  local out = {}
  for _, el in ipairs(inlines) do
    local kind = el.t
    if kind == "Str" or kind == "Code" then out[#out + 1] = el.text
    elseif kind == "Space" then out[#out + 1] = " "
    elseif kind == "SoftBreak" or kind == "LineBreak" then out[#out + 1] = "\n"
    elseif kind == "Link" then out[#out + 1] = "[" .. inlines_source(el.content) .. "](" .. el.target .. ")"
    elseif el.content and type(el.content) == "table" then out[#out + 1] = inlines_source(el.content)
    else out[#out + 1] = pandoc.utils.stringify(el) end
  end
  return table.concat(out)
end

local function div_source(div)
  local parts = {}
  for _, block in ipairs(div.content) do
    if block.t == "CodeBlock" then parts[#parts + 1] = block.text
    elseif block.t == "Para" or block.t == "Plain" then parts[#parts + 1] = inlines_source(block.content)
    else parts[#parts + 1] = pandoc.utils.stringify(block) end
  end
  return table.concat(parts, "\n")
end

local function has_class(classes, name)
  for _, class in ipairs(classes) do
    if class:lower() == name then return true end
  end
  return false
end

local function attributes_of(el)
  local result = {}
  for _, pair in ipairs(el.attributes) do result[pair[1]] = pair[2] end
  return result
end

local function document_folder()
  local files = PANDOC_STATE and PANDOC_STATE.input_files or {}
  local first = files[1]
  return first and first:match("^(.*)[/\\][^/\\]*$") or "."
end

-- The structure's text for a block: the file the block names, else its body. nil, with a warning, when the file is missing.
local function source_of(el, attributes)
  local body = el.t == "Div" and div_source(el) or el.text
  local name = attributes.file
  if not name or name == "" then return body, "" end
  local path = name
  if not (name:match("^/") or name:match("^%a:[/\\]") or name:match("^~")) then path = document_folder() .. "/" .. name end
  local data = read_file(path)
  if not data then
    warn("file" .. name, "file=\"" .. name .. "\" was not found (looked for " .. path .. "); the block was left as it is")
    return nil
  end
  return data, name:match("(%.%w+)$") or ""
end

-- One walk gathers the blocks, a second puts the pictures in their places; both visit them in the same order.
local function is_smiles(el)
  return (el.t == "CodeBlock" or el.t == "Div") and has_class(el.classes, "smiles")
end

local function figure(image, attributes, identifier)
  local caption = attributes.caption
  if caption and caption ~= "" then
    local text = pandoc.utils.blocks_to_inlines(pandoc.read(caption, "markdown").blocks)
    return pandoc.Figure({pandoc.Plain({image})}, {long = {pandoc.Plain(text)}}, pandoc.Attr(identifier or ""))
  end
  return pandoc.Para({image})
end

function Pandoc(doc)
  if family == nil then return nil end
  flat = doc.meta["pdfmd-flat"] ~= nil
  if family == "md" and not flat then return nil end        -- plain Markdown without a folder beside it keeps the block
  local given = doc.meta["pdfmd-raw-cache"]
  if given then cache_dir = pandoc.utils.stringify(given) end
  if not cache_dir then return nil end
  if doc.meta["pdfmd-raw-rel"] then cache_rel = pandoc.utils.stringify(doc.meta["pdfmd-raw-rel"]) end
  local python = doc.meta["pdfmd-smiles-python"] and pandoc.utils.stringify(doc.meta["pdfmd-smiles-python"]) or "python3"
  local folder = doc.meta["pdfmd-smiles-dir"] and pandoc.utils.stringify(doc.meta["pdfmd-smiles-dir"]) or nil
  if not folder then return nil end
  local settings = {}
  if doc.meta["pdfmd-smiles"] then
    for key, value in pairs(doc.meta["pdfmd-smiles"]) do settings[key] = pandoc.utils.stringify(value) end
  end

  local items, sources = {}, {}
  local function gather(el)
    if not is_smiles(el) then return nil end
    local attributes = attributes_of(el)
    local text, extension = source_of(el, attributes)
    items[#items + 1] = text and {text = text, extension = extension, attributes = attributes} or false
    return nil, false
  end
  doc:walk({traverse = "topdown", CodeBlock = gather, Div = gather})
  if #items == 0 then return nil end

  local requests = {}
  for index, item in ipairs(items) do
    if item then requests[#requests + 1] = item; sources[#requests] = index end
  end
  local answers = {}
  if #requests > 0 then
    pcall(pandoc.system.make_directory, cache_dir, true)
    local payload = pandoc.json.encode({cache = cache_dir, settings = settings, target = family, items = requests})
    local ok, out = pcall(pandoc.pipe, python, {folder}, payload)
    local decoded, list = false, nil
    if ok then decoded, list = pcall(pandoc.json.decode, out, false) end
    if not decoded or type(list) ~= "table" then
      warn("run", "the drawing step (python3 pdfmd_smiles) could not run; the blocks were left as they are")
      return nil
    end
    for position, index in ipairs(sources) do answers[index] = list[position] end
  end

  local counter = 0
  local function replace(el)
    if not is_smiles(el) then return nil end
    counter = counter + 1
    local answer = answers[counter]
    if not answer then return nil end
    if answer.error then
      warn("e" .. counter .. answer.error, answer.error .. "; the block was left as it is")
      return nil
    end
    local attributes = attributes_of(el)
    local image_attributes = {}
    if attributes.width then image_attributes.width = attributes.width
    elseif answer.format == "png" then image_attributes.width = tostring(answer.width) .. "px" end
    local image = pandoc.Image({}, link_to(answer.file), "", pandoc.Attr("", {"pdfmd-smiles"}, image_attributes))
    return figure(image, attributes, el.identifier), false
  end
  return doc:walk({traverse = "topdown", CodeBlock = replace, Div = replace})
end
