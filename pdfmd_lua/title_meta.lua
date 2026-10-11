-- pdfmd: a PDF's Title and Author when the title has LaTeX in it (v3.28.6). Pandoc makes `title-meta`, which hyperref
-- writes into the PDF's properties, from the title as plain text with raw LaTeX left out: "Reduction of
-- \emph{trans}-Cinnamaldehyde" was "Reduction of -Cinnamaldehyde". Here the LaTeX is read first ("trans"), and the
-- same for the authors (`author-meta`, "A; B"). pdfmd runs it only when the title or the authors have a backslash, and
-- before the document's own filters: one that takes the title out and keeps `title-meta` (nulabreport's, for a part
-- built alone) finds it set, and so does the LaTeX filter, which gives a Word or HTML file's properties the title a
-- house style's cover took out. A `title-meta` or `author-meta` of the document's own stays.

local stringify = pandoc.utils.stringify

local function trim(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end

local function is_tex(raw) return raw.format == "tex" or raw.format == "latex" end

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

function Meta(meta)
  local changed = false
  if meta.title ~= nil and meta["title-meta"] == nil and has_tex(meta.title) then
    local text = plain(meta.title)
    if text then meta["title-meta"] = pandoc.MetaString(text); changed = true end
  end
  local authors = meta.author
  if authors ~= nil and meta["author-meta"] == nil then
    local list = pandoc.utils.type(authors) == "List" and authors or {authors}
    local raw, names = false, {}
    for _, author in ipairs(list) do
      local value = pandoc.utils.type(author) == "table" and author.name or author
      raw = raw or (value ~= nil and has_tex(value))
      local name = value ~= nil and plain(value) or nil
      if name then names[#names + 1] = name end
    end
    if raw and #names > 0 then meta["author-meta"] = pandoc.MetaString(table.concat(names, "; ")); changed = true end
  end
  return changed and meta or nil
end
