-- pdfmd: PDF images in an HTML build (v3.25.17). Browsers and WeasyPrint do not show a PDF in <img>; an SVG they do, and
-- the drawing stays vector. For an HTML-family writer (html, html5, epub) each image whose file is a PDF -- a Markdown
-- image, or an <img> in raw HTML -- is converted (first page) to an SVG with whatever is installed (poppler's
-- pdftocairo, mutool, pdf2svg, inkscape), kept in the cache by the PDF's content, and the image points at it. Other
-- writers are left alone (LaTeX and Typst read a PDF themselves; the Word route has its own). `pdfmd-raw-cache` is the
-- folder for the SVGs; without it, or without a tool, the image is left as written and a warning says why.

local html = FORMAT:match("^html") or FORMAT:match("^epub") or FORMAT == "chunkedhtml"
if not html then return {} end

local cache_dir = nil
local warned = {}

local function warn(key, message)
  if not warned[key] then
    warned[key] = true
    io.stderr:write("WARN  pdf image: " .. message .. "\n")
  end
end

local function file_bytes(path)
  local handle = io.open(path, "rb")
  if not handle then return nil end
  local data = handle:read("a")
  handle:close()
  return data
end

local function locate(src)
  local path = src:gsub("%?.*$", ""):gsub("#.*$", "")
  path = path:gsub("%%20", " ")
  if file_bytes(path) then return path end
  for _, folder in ipairs(PANDOC_STATE.resource_path or {}) do
    local candidate = folder .. "/" .. path
    if file_bytes(candidate) then return candidate end
  end
  return nil
end

local function to_svg(src)
  if not cache_dir then return nil end
  local path = locate(src)
  if not path then return nil end
  local data = file_bytes(path)
  local key = pandoc.sha1(data)
  pcall(pandoc.system.make_directory, cache_dir, true)
  local svg = cache_dir .. "/" .. key .. ".svg"
  if file_bytes(svg) then return svg end
  for _, tool in ipairs({{"pdftocairo", {"-svg", "-f", "1", "-l", "1", path, svg}}, {"mutool", {"draw", "-o", svg, path, "1"}},
                         {"pdf2svg", {path, svg}}, {"inkscape", {path, "--export-type=svg", "--export-filename=" .. svg}}}) do
    if pcall(pandoc.pipe, tool[1], tool[2], "") and file_bytes(svg) then return svg end
  end
  warn("tool", "no tool to turn a PDF into an SVG (install poppler's pdftocairo, mutool, pdf2svg or inkscape); "
       .. "PDF images are left as written")
  return nil
end

local function is_pdf(src)
  return src:gsub("%?.*$", ""):gsub("#.*$", ""):lower():match("%.pdf$") ~= nil
end

local function Meta(meta)
  if meta["pdfmd-raw-cache"] then cache_dir = pandoc.utils.stringify(meta["pdfmd-raw-cache"]) end
end

local function Image(el)
  if is_pdf(el.src) then
    local svg = to_svg(el.src)
    if svg then
      el.src = svg
      return el
    end
  end
end

local function raw(el)
  if el.format ~= "html" and el.format ~= "html5" then return nil end
  local changed = false
  local text = el.text:gsub('(<img[^>]-src%s*=%s*)(["\'])(.-)%2', function(head, quote, src)
    if is_pdf(src) then
      local svg = to_svg(src)
      if svg then
        changed = true
        return head .. quote .. svg .. quote
      end
    end
  end)
  if changed then
    el.text = text
    return el
  end
end

return {{Meta = Meta}, {Image = Image, RawBlock = raw, RawInline = raw}}
