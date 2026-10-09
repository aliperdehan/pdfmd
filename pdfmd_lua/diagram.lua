-- pdfmd: diagrams written as code (v3.26.16). A fenced block whose class is `mermaid`, `d2`, `dot` or `graphviz`
--
--     ```mermaid
--     graph LR; A --> B
--     ```
--
-- is drawn by the tool that reads that language (mmdc, d2, dot) when it is installed, and the picture takes the place of
-- the block, in the format the output takes: a PDF for LaTeX, an SVG for HTML, an SVG (a PNG for Mermaid, whose SVG
-- Typst cannot show) for Typst, a PNG for Word and OpenDocument, an SVG beside the output for flat Markdown (--to gfm), where a
-- Mermaid block stays as it is because GitHub draws it. A tool that is not installed leaves the block as code, with one
-- warning. Attributes: `caption="..."` (a figure; `{#fig:id}` works with pandoc-crossref), `width=`, `engine=` (Graphviz:
-- dot, neato, fdp, sfdp, circo, twopi), `theme=` (Mermaid), `layout=` (D2: dagre, elk).
--
-- Configuration arrives as metadata written by pdfmd, the same keys raw.lua reads: `pdfmd-raw-cache` (where pictures are
-- kept), `pdfmd-raw-rel` (flat Markdown: the folder's name beside the output), `pdfmd-flat` (flat Markdown is on).

local FAMILY = {
  latex = "tex", beamer = "tex", context = "tex",
  typst = "typst",
  html = "html", html4 = "html", html5 = "html", epub = "html", epub2 = "html", epub3 = "html", slidy = "html",
  slideous = "html", revealjs = "html", s5 = "html", dzslides = "html", chunkedhtml = "html",
  docx = "office", odt = "office", opendocument = "office", pptx = "office", openxml = "office",
  gfm = "md",
}
local family = FAMILY[FORMAT] or (FORMAT:match("^html") and "html") or nil

local TOOL = {mermaid = "mmdc", d2 = "d2", dot = "dot", graphviz = "dot"}
local HINT = {
  mmdc = "npm install -g @mermaid-js/mermaid-cli",
  d2 = "brew install d2  (or https://d2lang.com/tour/install)",
  dot = "brew install graphviz  |  apt install graphviz",
}
local GRAPHVIZ_ENGINES = {dot = true, neato = true, fdp = true, sfdp = true, circo = true, twopi = true}
local MERMAID_THEMES = {default = true, dark = true, forest = true, neutral = true}
local D2_LAYOUTS = {dagre = true, elk = true}

local cache_dir, cache_rel = nil, nil
local flat = false
local warned = {}
local present = {}

local function warn(key, message)
  if not warned[key] then
    warned[key] = true
    io.stderr:write("WARN  diagram: " .. message .. "\n")
  end
end

local function file_exists(path)
  local handle = io.open(path, "rb")
  if handle then handle:close() return true end
  return false
end

local function read_file(path)
  local handle = io.open(path, "rb")
  if not handle then return nil end
  local data = handle:read("a")
  handle:close()
  return data
end

local function write_file(path, data)
  local handle = io.open(path, "wb")
  if not handle then return false end
  handle:write(data)
  handle:close()
  return true
end

-- pdfmd lists the tools it found on the PATH in `pdfmd-diagram-tools` (a tool is not run just to ask).
local function installed(tool)
  return present[tool] == true
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

-- The format the output takes for a tool, or nil when the block should stay as it is.
local function wanted_format(tool)
  if family == "tex" then return "pdf" end
  if family == "html" then return "svg" end
  if family == "typst" then return tool == "mmdc" and "png" or "svg" end
  if family == "office" then return "png" end
  if family == "md" then
    if not flat or tool == "mmdc" then return nil end      -- GitHub draws a Mermaid block itself
    return "svg"
  end
  return nil
end

local function run_in(folder, command, args)
  local ok = pcall(pandoc.system.with_working_directory, folder, function() return pandoc.pipe(command, args, "") end)
  return ok
end

-- SVG -> PDF or PNG, for D2 (whose own PDF and PNG need a browser download).
local function convert_svg(svg, out, format)
  local attempts = {}
  if format == "pdf" then
    attempts = {{"rsvg-convert", {"-f", "pdf", "-o", out, svg}}, {"inkscape", {svg, "--export-type=pdf", "--export-filename=" .. out}}}
  else
    attempts = {{"rsvg-convert", {"-z", "2", "-f", "png", "-o", out, svg}}, {"inkscape", {svg, "--export-type=png", "--export-dpi=192", "--export-filename=" .. out}}}
  end
  for _, attempt in ipairs(attempts) do
    if pcall(pandoc.pipe, attempt[1], attempt[2], "") and file_exists(out) then return true end
  end
  return false
end

local function draw(tool, source, attributes, format)
  local key = pandoc.sha1(table.concat({tool, format, attributes.engine or "", attributes.theme or "", attributes.layout or "", source}, "\0"))
  local target = cache_dir .. "/" .. key .. "." .. format
  if file_exists(target) and #(read_file(target) or "") > 0 then return target end
  local made = false
  pandoc.system.with_temporary_directory("pdfmd-diagram", function(folder)
    if tool == "dot" then
      local engine = GRAPHVIZ_ENGINES[attributes.engine or "dot"] and (attributes.engine or "dot") or "dot"
      local args = {"-T" .. format}
      if format == "png" then args[#args + 1] = "-Gdpi=192" end
      local ok, data = pcall(pandoc.pipe, engine, args, source)
      if ok and data and #data > 0 then made = write_file(target, data) end
    elseif tool == "d2" then
      write_file(folder .. "/in.d2", source)
      local args = {}
      if attributes.layout and D2_LAYOUTS[attributes.layout] then args = {"--layout", attributes.layout} end
      args[#args + 1] = "in.d2"
      args[#args + 1] = "out.svg"
      if run_in(folder, "d2", args) and file_exists(folder .. "/out.svg") then
        if format == "svg" then
          made = write_file(target, read_file(folder .. "/out.svg"))
        elseif convert_svg(folder .. "/out.svg", folder .. "/out." .. format, format) then
          made = write_file(target, read_file(folder .. "/out." .. format))
        end
      end
    else                                                    -- mmdc
      write_file(folder .. "/in.mmd", source)
      local args = {"-i", "in.mmd", "-o", "out." .. format, "-b", "transparent", "--quiet"}
      if attributes.theme and MERMAID_THEMES[attributes.theme] then args[#args + 1] = "-t" args[#args + 1] = attributes.theme end
      if format == "png" then args[#args + 1] = "-s" args[#args + 1] = "3" end
      if format == "pdf" then args[#args + 1] = "--pdfFit" end
      local config = os.getenv("PDFMD_MMDC_CONFIG")
      if config and config ~= "" then args[#args + 1] = "-p" args[#args + 1] = config end
      if run_in(folder, "mmdc", args) and file_exists(folder .. "/out." .. format) then
        made = write_file(target, read_file(folder .. "/out." .. format))
      end
    end
  end)
  if made then return target end
  return nil
end

local function link_to(path)
  if cache_rel then return cache_rel .. "/" .. path:match("[^/\\]+$") end
  local suffix = path:match("%.(%w+)$")
  if FORMAT:match("^html") and MIME[suffix] then        -- an HTML file carries its pictures (EPUB takes the files)
    local data = read_file(path)
    if data and #data < 3000000 then return "data:" .. MIME[suffix] .. ";base64," .. base64(data) end
  end
  return path
end

local function diagram(block)
  local tool
  for _, class in ipairs(block.classes) do
    tool = TOOL[class:lower()]
    if tool then break end
  end
  if not tool or not family then return nil end
  local format = wanted_format(tool)
  if not format then return nil end
  if not installed(tool) then
    warn(tool, "a " .. tool .. " diagram was left as code: `" .. tool .. "` is not installed (" .. HINT[tool] .. ")")
    return nil
  end
  local attributes = {}
  for _, pair in ipairs(block.attributes) do attributes[pair[1]] = pair[2] end
  local file = draw(tool, block.text, attributes, format)
  if not file then
    warn(tool .. block.text, "a " .. tool .. " diagram could not be drawn (does the source parse? run `" .. tool .. "` on it to see); it was left as code")
    return nil
  end
  local image_attributes = {}
  if attributes.width then image_attributes.width = attributes.width end
  local image = pandoc.Image({}, link_to(file), "", pandoc.Attr("", {"pdfmd-diagram"}, image_attributes))
  local caption = attributes.caption
  if caption and caption ~= "" then
    local text = pandoc.utils.blocks_to_inlines(pandoc.read(caption, "markdown").blocks)
    return pandoc.Figure({pandoc.Plain({image})}, {long = {pandoc.Plain(text)}}, pandoc.Attr(block.identifier or ""))
  end
  return pandoc.Para({image})
end

function Pandoc(doc)
  if family == nil then return nil end
  local given = doc.meta["pdfmd-raw-cache"]
  if given then cache_dir = pandoc.utils.stringify(given) end
  if not cache_dir then return nil end
  if doc.meta["pdfmd-raw-rel"] then cache_rel = pandoc.utils.stringify(doc.meta["pdfmd-raw-rel"]) end
  flat = doc.meta["pdfmd-flat"] ~= nil
  local tools = doc.meta["pdfmd-diagram-tools"]
  if tools then
    for _, name in ipairs(tools) do present[pandoc.utils.stringify(name)] = true end
  end
  pcall(pandoc.system.make_directory, cache_dir, true)
  return doc:walk({CodeBlock = diagram})
end
