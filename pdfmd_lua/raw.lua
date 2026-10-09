-- pdfmd: raw passthrough (v3.25.17). Markdown can carry pieces that are not Markdown: raw HTML (<img>, <table>, <b>...),
-- raw LaTeX (\ce{}, tikz), raw Typst (#...), raw Word/OpenDocument XML. Pandoc keeps the ones written in the format it is
-- writing and silently drops the rest. With `pdfmd-options: {raw: ...}` (or --raw) this filter decides, per output family,
-- which of those syntaxes take part, and carries the foreign ones over:
--
--   html  -> read with Pandoc's HTML reader, so <img>, <table>, <b>...</b>, <div>...</div> become the target's own
--            images, tables, bold text and divisions (an opening and its closing tag in separate raw pieces are matched);
--   tex   -> read with Pandoc's LaTeX reader (what it does not know stays raw LaTeX and is lost outside LaTeX);
--   typst -> drawn by `typst compile` as a cropped PDF picture and placed as an image (an SVG for HTML targets, which
--            cannot show a PDF), so it stays vector;
--   a LaTeX picture Pandoc's reader cannot read (tikzpicture, circuitikz, pgfpicture, forest, \chemfig ...) is drawn by
--   a LaTeX engine with the `standalone` class, the document's preamble (`pdfmd-raw-preamble`) and its own package, and
--   placed the same way, for the HTML, Typst and flat-Markdown families;
--   a syntax that is not on the family's list is left out, the family's own included (a rare, but demonstrative, use).
--
-- Configuration arrives as metadata (written by pdfmd): `pdfmd-raw` = {tex = [...], typst = [...], html = [...],
-- office = [...]} (the syntaxes each family takes) and `pdfmd-raw-cache` (where pictures are kept).
-- The families are the writer's: latex/beamer -> tex, typst, html/html5/epub -> html, docx/odt/pptx -> office.

local SENTINEL = "PDFMDRAWMARK"

local FAMILY = {
  latex = "tex", beamer = "tex", context = "tex",
  typst = "typst",
  html = "html", html4 = "html", html5 = "html", epub = "html", epub2 = "html", epub3 = "html", slidy = "html",
  slideous = "html", revealjs = "html", s5 = "html", dzslides = "html", chunkedhtml = "html",
  docx = "office", odt = "office", opendocument = "office", pptx = "office", openxml = "office",
  gfm = "md",          -- flat Markdown (--to gfm), only when pdfmd marks the build (`pdfmd-flat` in the metadata)
}
local SYNTAX = {
  html = "html", html4 = "html", html5 = "html",
  latex = "tex", tex = "tex",
  typst = "typst",
  openxml = "office", opendocument = "office",
}
local VOID = {area = true, base = true, br = true, col = true, embed = true, hr = true, img = true, input = true,
              link = true, meta = true, source = true, track = true, wbr = true}

local family = FAMILY[FORMAT] or (FORMAT:match("^html") and "html") or nil
local NATIVE_SYNTAX = {tex = "tex", typst = "typst", html = "html", office = "office"}
local family_syntax = family and NATIVE_SYNTAX[family] or nil
local included = nil      -- set of syntaxes this family takes; nil = the filter is off
local office_reads_tex = false   -- pdfmd's LaTeX route (office.lua, which runs after this filter) is on: it takes the LaTeX
local cache_dir = nil
local work_dir = nil       -- where the drawn PDFs are kept when the SVGs go elsewhere (flat Markdown); else the cache
local cache_rel = nil      -- flat Markdown: the folder's name beside the output, which the pictures' links use
local preamble_files = {}  -- the document's LaTeX preamble files, which a LaTeX picture is drawn with
local header_tex = {}      -- and its header-includes
local warned = {}

local function warn(key, message)
  if not warned[key] then
    warned[key] = true
    io.stderr:write("WARN  raw: " .. message .. "\n")
  end
end

local function read_config(meta)
  local raw = meta["pdfmd-raw"]
  if family == "md" and meta["pdfmd-flat"] == nil then return end
  if type(raw) ~= "table" or family == nil then return end
  local list = raw[family]
  if list == nil then return end
  included = {}
  if pandoc.utils.type(list) == "List" then
    for _, item in ipairs(list) do included[pandoc.utils.stringify(item)] = true end
  else
    included[pandoc.utils.stringify(list)] = true
  end
  if meta["pdfmd-raw-cache"] then cache_dir = pandoc.utils.stringify(meta["pdfmd-raw-cache"]) end
  if meta["pdfmd-raw-work"] then work_dir = pandoc.utils.stringify(meta["pdfmd-raw-work"]) end
  if meta["pdfmd-raw-rel"] then cache_rel = pandoc.utils.stringify(meta["pdfmd-raw-rel"]) end
  if meta["pdfmd-raw-preamble"] then
    for _, item in ipairs(meta["pdfmd-raw-preamble"]) do preamble_files[#preamble_files + 1] = pandoc.utils.stringify(item) end
  end
  if meta["header-includes"] then
    -- the LaTeX the writer would put in the header: markdown-looking lines (a `$..$`) come back as TeX
    local function tex_of(value)
      local kind = pandoc.utils.type(value)
      if kind == "Inlines" then value = pandoc.Blocks{pandoc.Plain(value)}
      elseif kind == "Block" then value = pandoc.Blocks{value} end
      local ok, text = pcall(pandoc.write, pandoc.Pandoc(value), "latex")
      return ok and text or ""
    end
    local value = meta["header-includes"]
    if pandoc.utils.type(value) == "List" then
      for _, item in ipairs(value) do header_tex[#header_tex + 1] = tex_of(item) end
    else
      header_tex[1] = tex_of(value)
    end
  end
  office_reads_tex = meta["pdfmd-office-latex"] ~= nil
end

local function file_exists(path)
  local handle = io.open(path, "rb")
  if handle then handle:close() return true end
  return false
end

local function ensure_cache()
  if not cache_dir then return false end
  pcall(pandoc.system.make_directory, cache_dir, true)
  if work_dir then pcall(pandoc.system.make_directory, work_dir, true) end
  return true
end

local function pdf_folder() return work_dir or cache_dir end

-- A drawn PDF -> the file the target takes: the PDF itself, or (HTML, flat Markdown) an SVG next to it.
local function picture_file(pdf, key, what)
  if family ~= "html" and family ~= "md" then return pdf end
  local svg = cache_dir .. "/" .. key .. ".svg"
  if not file_exists(svg) then
    local done = false
    for _, tool in ipairs({{"pdftocairo", {"-svg", pdf, svg}}, {"mutool", {"draw", "-o", svg, pdf, "1"}},
                           {"pdf2svg", {pdf, svg}}, {"inkscape", {pdf, "--export-type=svg", "--export-filename=" .. svg}}}) do
      if pcall(pandoc.pipe, tool[1], tool[2], "") and file_exists(svg) then done = true break end
    end
    if not done then
      warn("svg", "a PDF picture cannot become an SVG for HTML (install poppler's pdftocairo, mutool, pdf2svg or inkscape); " .. what .. " pieces were left out")
      return nil
    end
  end
  return svg
end

-- Typst source -> a PDF picture (cropped to its content), cached by content; an SVG for an HTML target.
local function typst_picture(text)
  if not ensure_cache() then warn("cache", "no cache folder, so Typst pieces cannot be drawn") return nil end
  local key = pandoc.sha1(text)
  local pdf = pdf_folder() .. "/" .. key .. ".pdf"
  if not file_exists(pdf) then
    local source = "#set page(width: auto, height: auto, margin: 2pt)\n" .. text .. "\n"
    local ok, data = pcall(pandoc.pipe, "typst", {"compile", "--format", "pdf", "-", "-"}, source)
    if not ok or #data == 0 then
      warn("typst" .. key, "a Typst piece could not be drawn (is `typst` installed, and is the piece complete?); it was left out")
      return nil
    end
    local handle = io.open(pdf, "wb")
    if not handle then return nil end
    handle:write(data)
    handle:close()
  end
  return picture_file(pdf, key, "Typst")
end

-- LaTeX pictures -----------------------------------------------------------------------------------------------------
-- What Pandoc's LaTeX reader leaves as raw LaTeX and a LaTeX engine draws: the environments and commands of the drawing
-- packages. Each is typeset alone with the `standalone` class (cropped to its content), after the document's own
-- preamble, and its package is loaded if the preamble has not.
local PICTURE_ENV = {tikzpicture = "tikz", circuitikz = "circuitikz", pgfpicture = "tikz", forest = "forest",
                     pspicture = "pstricks", axis = "pgfplots", chemfig = "chemfig", ["tikzcd"] = "tikz-cd"}
local PICTURE_COMMAND = {chemfig = "chemfig", schemestart = "chemfig", tikz = "tikz"}
local TEX_ENGINES = {"lualatex", "xelatex", "pdflatex"}

local function picture_package(text)
  local environment = text:match("^%s*\\begin%s*{([%w%*]+)}")
  if environment and PICTURE_ENV[environment] then return PICTURE_ENV[environment] end
  local command = text:match("^%s*\\(%a+)")
  if command and PICTURE_COMMAND[command] then return PICTURE_COMMAND[command] end
  return nil
end

local function read_file(path)
  local handle = io.open(path, "rb")
  if not handle then return "" end
  local data = handle:read("a")
  handle:close()
  return data
end

local function tex_picture(text, package)
  if not ensure_cache() then warn("cache", "no cache folder, so LaTeX pictures cannot be drawn") return nil end
  local parts = {}
  for _, path in ipairs(preamble_files) do parts[#parts + 1] = read_file(path) end
  for _, snippet in ipairs(header_tex) do parts[#parts + 1] = snippet end
  local preamble = table.concat(parts, "\n")
  local source = "\\documentclass[border=2pt]{standalone}\n" .. preamble
    .. "\n\\makeatletter\\@ifpackageloaded{" .. package .. "}{}{\\usepackage{" .. package .. "}}\\makeatother\n"
    .. "\\begin{document}\n" .. text .. "\n\\end{document}\n"
  local key = pandoc.sha1(source)
  local pdf = pdf_folder() .. "/" .. key .. ".pdf"
  if not file_exists(pdf) then
    -- typeset in a scratch folder: the cache (the folder beside a flat Markdown output) only gets the picture
    local data, problem = nil, nil
    pandoc.system.with_temporary_directory("pdfmd-tex", function(folder)
      local handle = io.open(folder .. "/pic.tex", "wb")
      if not handle then return end
      handle:write(source)
      handle:close()
      for _, engine in ipairs(TEX_ENGINES) do
        pcall(pandoc.system.with_working_directory, folder, function()
          return pandoc.pipe(engine, {"-interaction=nonstopmode", "-halt-on-error", "pic.tex"}, "")
        end)
        if file_exists(folder .. "/pic.pdf") then data = read_file(folder .. "/pic.pdf") break end
        problem = problem or read_file(folder .. "/pic.log"):match("\n(![^\n]*)")
      end
    end)
    if not data or #data == 0 then
      warn("tex" .. key, "a LaTeX picture could not be drawn" .. (problem and (" (" .. problem .. ")") or "")
           .. "; is a LaTeX engine with the `standalone` class installed, and does the picture need a package or macro "
           .. "the document's preamble defines? It was left out")
      return nil
    end
    local out = io.open(pdf, "wb")
    if not out then return nil end
    out:write(data)
    out:close()
  end
  return picture_file(pdf, key, "LaTeX")
end

local function drawable_family()
  return family == "html" or family == "md" or family == "typst"
end

local function link_to(path)
  if cache_rel then return cache_rel .. "/" .. path:match("[^/\\]+$") end
  return path
end

local function picture(text, tex_package)
  local source = tex_package and tex_picture(text, tex_package) or (not tex_package and typst_picture(text)) or nil
  if not source then return nil end
  return pandoc.Image({}, link_to(source), "", pandoc.Attr("", {"pdfmd-raw"}))
end

-- reading -----------------------------------------------------------------------------------------------------------
local function read(text, format)
  local ok, doc = pcall(pandoc.read, text, format)
  if ok then return doc end
  return nil
end

local function inlines_of(doc)
  local out = pandoc.Inlines{}
  for _, block in ipairs(doc.blocks) do
    if block.content and (block.t == "Para" or block.t == "Plain") then
      if #out > 0 then out:insert(pandoc.Space()) end
      out:extend(block.content)
    elseif block.t == "RawBlock" then
      -- nothing an inline position can hold
    end
  end
  return out
end

local function tag_of(text, closing)
  local trimmed = text:match("^%s*(.-)%s*$")
  if closing then return trimmed:match("^</([%a][%w:-]*)%s*>$") end
  local name = trimmed:match("^<([%a][%w:-]*)[%s>/]")
  if not name or not trimmed:match(">$") or trimmed:match("/>$") then return nil end
  if VOID[name:lower()] then return nil end
  -- an opening tag alone: no other tag inside the piece
  if trimmed:sub(2):find("<", 1, true) then return nil end
  return name
end

local function find_close(list, from, name, kind)
  local depth = 0
  for index = from + 1, #list do
    local item = list[index]
    if item.t == kind and SYNTAX[item.format] == "html" then
      local opening = tag_of(item.text, false)
      if opening and opening:lower() == name:lower() then depth = depth + 1 end
      local closing = tag_of(item.text, true)
      if closing and closing:lower() == name:lower() then
        if depth == 0 then return index end
        depth = depth - 1
      end
    end
  end
  return nil
end

local function fill_inlines(doc, middle)
  local found = false
  doc = doc:walk({Inlines = function(list)
    for index, item in ipairs(list) do
      if item.t == "Str" and item.text == SENTINEL then
        local out = pandoc.Inlines{}
        for k = 1, index - 1 do out:insert(list[k]) end
        for _, m in ipairs(middle) do out:insert(m) end
        for k = index + 1, #list do out:insert(list[k]) end
        found = true
        return out
      end
    end
  end})
  return doc, found
end

local function fill_blocks(doc, middle)
  local found = false
  doc = doc:walk({Blocks = function(list)
    for index, item in ipairs(list) do
      if (item.t == "Para" or item.t == "Plain") and #item.content == 1 and item.content[1].t == "Str"
         and item.content[1].text == SENTINEL then
        local out = pandoc.Blocks{}
        for k = 1, index - 1 do out:insert(list[k]) end
        for _, m in ipairs(middle) do out:insert(m) end
        for k = index + 1, #list do out:insert(list[k]) end
        found = true
        return out
      end
    end
  end})
  return doc, found
end

-- list handlers -----------------------------------------------------------------------------------------------------
-- Returns the replacement for the raw item at `index` of `list` and the index to go on from.
local function convert_inline(list, index)
  local item = list[index]
  local syntax = SYNTAX[item.format]
  if syntax == "html" then
    local name = tag_of(item.text, false)
    if name then
      local close = find_close(list, index, name, "RawInline")
      if close then
        local middle = {}
        for k = index + 1, close - 1 do middle[#middle + 1] = list[k] end
        local doc = read(item.text .. SENTINEL .. list[close].text, "html")
        if doc then
          local filled, found = fill_inlines(doc, middle)
          if found then return inlines_of(filled), close + 1 end
        end
        return middle, close + 1
      end
      return {}, index + 1
    end
    if tag_of(item.text, true) then return {}, index + 1 end
    local doc = read(item.text, "html")
    return doc and inlines_of(doc) or {}, index + 1
  elseif syntax == "tex" then
    local package = drawable_family() and picture_package(item.text) or nil
    if package then
      local image = picture(item.text, package)
      return image and {image} or {}, index + 1
    end
    local doc = read(item.text, "latex")
    return doc and inlines_of(doc) or {}, index + 1
  elseif syntax == "typst" then
    local image = picture(item.text)
    return image and {image} or {}, index + 1
  end
  return {}, index + 1
end

-- tags whose content is Markdown blocks: they become a Div (or a block quote) around the real blocks. Anything else that
-- opens and closes in separate pieces (a table, a list ...) is written out as HTML with its content and read back whole.
local CONTAINER = {div = true, section = true, article = true, aside = true, main = true, header = true,
                   footer = true, nav = true, blockquote = true, center = true, figure = false}

local function convert_block(list, index)
  local item = list[index]
  local syntax = SYNTAX[item.format]
  if syntax == "html" then
    local name = tag_of(item.text, false)
    if name then
      local close = find_close(list, index, name, "RawBlock")
      if close then
        local middle = {}
        for k = index + 1, close - 1 do middle[#middle + 1] = list[k] end
        if CONTAINER[name:lower()] then
          local doc = read(item.text .. "\n" .. SENTINEL .. "\n" .. list[close].text, "html")
          if doc then
            local filled, found = fill_blocks(doc, middle)
            if found then return filled.blocks, close + 1 end
          end
          return middle, close + 1
        end
        local inner = pandoc.write(pandoc.Pandoc(middle), "html")
        local doc = read(item.text .. "\n" .. inner .. "\n" .. list[close].text, "html")
        return doc and doc.blocks or middle, close + 1
      end
      return {}, index + 1
    end
    if tag_of(item.text, true) then return {}, index + 1 end
    local doc = read(item.text, "html")
    return doc and doc.blocks or {}, index + 1
  elseif syntax == "tex" then
    local package = drawable_family() and picture_package(item.text) or nil
    if package then
      local image = picture(item.text, package)
      return image and {pandoc.Para{image}} or {}, index + 1
    end
    local doc = read(item.text, "latex")
    return doc and doc.blocks or {}, index + 1
  elseif syntax == "typst" then
    local image = picture(item.text)
    return image and {pandoc.Para{image}} or {}, index + 1
  end
  return {}, index + 1
end

local function process(list, kind, convert)
  local out, changed, index = {}, false, 1
  while index <= #list do
    local item = list[index]
    local syntax = (item.t == kind) and SYNTAX[item.format] or nil
    if syntax == nil then
      out[#out + 1] = item
      index = index + 1
    elseif not included[syntax] then
      changed, index = true, index + 1                              -- not a syntax this family takes
    elseif family == "md" and syntax == "office" then
      out[#out + 1] = item          -- flat Markdown: nothing reads Word XML; flat.lua counts it and says so
      index = index + 1
    elseif syntax == family_syntax or (syntax == "tex" and office_reads_tex) then
      out[#out + 1] = item                   -- its own syntax, or LaTeX that the office route turns into the target's own
      index = index + 1
    else
      local pieces, next_index = convert(list, index)
      for _, piece in ipairs(pieces) do out[#out + 1] = piece end
      changed, index = true, next_index
    end
  end
  if changed then return out end
  return nil
end

function Meta(meta)
  read_config(meta)
  return nil
end

local function Blocks(list)
  if not included then return nil end
  local result = process(list, "RawBlock", convert_block)
  return result and pandoc.Blocks(result) or nil
end

local function Inlines(list)
  if not included then return nil end
  local result = process(list, "RawInline", convert_inline)
  return result and pandoc.Inlines(result) or nil
end

return {
  {Meta = Meta},
  {Blocks = Blocks, Inlines = Inlines},
}
