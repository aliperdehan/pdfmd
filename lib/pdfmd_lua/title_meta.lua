-- pdfmd: a PDF's Title and Author when the title has LaTeX in it (v3.28.6). Pandoc makes `title-meta`, which hyperref
-- writes into the PDF's properties, from the title as plain text with raw LaTeX left out: "Reduction of
-- \emph{trans}-Cinnamaldehyde" was "Reduction of -Cinnamaldehyde". Here the LaTeX is read first ("trans"), and the
-- same for the authors (`author-meta`, "A; B"). pdfmd runs it only when the title or the authors have a backslash, and
-- before the document's own filters: one that takes the title out and keeps `title-meta` (nulabreport's, for a part
-- built alone) finds it set, and so does the LaTeX filter, which gives a Word or HTML file's properties the title a
-- house style's cover took out. A `title-meta` or `author-meta` of the document's own stays.
--
-- An author written as a mapping (`- name: Jane Doe` with an `affiliation:`, v3.33.56). Pandoc's `author-meta` holds the
-- authors written as text only, so a LaTeX or HTML PDF named none of two mappings, and only the string of a string and a
-- mapping. pdfmd runs this filter then too, and the names (each mapping's `name`, never the whole mapping) are joined as
-- Pandoc joins authors written as text: one "A; B" for LaTeX and Beamer (hyperref's pdfauthor), one `<meta name="author">`
-- each for HTML (a WeasyPrint or Calibre PDF), raw as office.lua writes them (text in a template variable is wrapped at
-- 72 columns). Typst's template reads `name` itself; other writers are left as they are.

local stringify = pandoc.utils.stringify

local function trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

local function is_tex(raw) return raw.format == "tex" or raw.format == "latex" end

local function html_text(text)
  return (text:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"):gsub('"', "&quot;"))
end

local function wrapped(value)
  local kind = pandoc.utils.type(value)
  if kind == "Inlines" then return pandoc.Plain(value) end
  if kind == "Blocks" then return pandoc.Div(value) end
  return nil
end

local function has_tex(value)
  local element, found = wrapped(value), false
  if element then element:walk({RawInline = function(raw) if is_tex(raw) then found = true end end}) end
  return found
end

local function plain(value)
  local element = wrapped(value)
  if not element then return nil end
  element = element:walk({RawInline = function(raw)
    if not is_tex(raw) then return {} end
    local ok, read = pcall(pandoc.read, raw.text, "latex")
    return ok and pandoc.Str(stringify(read.blocks)) or {}
  end, RawBlock = function() return {} end})
  local text = trim((stringify(element):gsub("%s+", " ")))
  return text ~= "" and text or nil
end

-- An author written as a mapping without `name` (`- affiliation: NU`, v3.33.63) is left out: Pandoc's templates printed it as
-- `true` (LaTeX's \author, Typst's title block and PDF Author, HTML's title block). pdfmd says so (`author entry N has no
-- name: left out`) and runs this filter whenever an author is a mapping.
local function without_nameless(meta)
  local authors = meta.author
  if authors == nil then return false end
  local single = pandoc.utils.type(authors) ~= "List"
  local kept, dropped = pandoc.List(), false
  for _, author in ipairs(single and {authors} or authors) do
    if pandoc.utils.type(author) == "table" and author.name == nil then dropped = true else kept:insert(author) end
  end
  if not dropped then return false end
  meta.author = #kept > 0 and pandoc.MetaList(kept) or nil
  return true
end

function Meta(meta)
  local changed = without_nameless(meta)
  if meta.title ~= nil and meta["title-meta"] == nil and has_tex(meta.title) then
    local text = plain(meta.title)
    if text then meta["title-meta"] = pandoc.MetaString(text); changed = true end
  end
  local authors = meta.author
  if authors ~= nil and meta["author-meta"] == nil then
    local list = pandoc.utils.type(authors) == "List" and authors or {authors}
    local raw, mapped, names = false, false, {}
    for _, author in ipairs(list) do
      local is_mapping = pandoc.utils.type(author) == "table"
      mapped = mapped or is_mapping
      local value = is_mapping and author.name or author
      raw = raw or (value ~= nil and has_tex(value))
      local name = value ~= nil and plain(value) or nil
      if name then names[#names + 1] = name end
    end
    if #names > 0 and mapped and FORMAT:match("^html") then
      local tags = pandoc.MetaList({})
      for _, name in ipairs(names) do tags:insert(pandoc.MetaInlines({pandoc.RawInline("html", html_text(name))})) end
      meta["author-meta"] = tags
      changed = true
    elseif #names > 0 and (raw or (mapped and (FORMAT == "latex" or FORMAT == "beamer"))) then
      meta["author-meta"] = pandoc.MetaString(table.concat(names, "; "))
      changed = true
    end
  end
  return changed and meta or nil
end
