-- pdfmd: `cover` (v3.29.9). `pdfmd-options: {cover: true}` puts the title block on a page of its own, `cover: picture.png` puts that
-- picture on the first page (a LaTeX or HTML-family PDF, an HTML page) or makes it the cover of an EPUB (and so of a Kindle book, which
-- Calibre makes from it). Other writers (Word, OpenDocument, Typst ...) are told once that it was not applied.
--
-- Metadata the command line gives it: pdfmd-cover = title | image, pdfmd-cover-image = the picture's path, pdfmd-cover-latex = 0 when
-- the document's class has no `titlepage` option to give.
local function plain(value)
  return value and pandoc.utils.stringify(value) or ""
end

local function append(meta, key, value)
  local current = meta[key]
  if current == nil then
    meta[key] = pandoc.MetaList({value})
  elseif current.t == "MetaList" then
    current[#current + 1] = value
    meta[key] = current
  else
    meta[key] = pandoc.MetaList({current, value})
  end
end

function Meta(meta)
  local mode = plain(meta["pdfmd-cover"])
  if mode == "" then return nil end
  local image = plain(meta["pdfmd-cover-image"])
  local format = FORMAT or ""
  if format:match("^epub") then
    if image ~= "" and meta["cover-image"] == nil then meta["cover-image"] = pandoc.MetaString(image) end
    return meta
  end
  local latex = format:match("latex") or format:match("beamer")
  if not (latex or format:match("^html")) then
    io.stderr:write("NOTE  cover: is not applied to " .. format .. " (LaTeX and HTML-family PDFs, HTML and EPUB have it)\n")
    return nil
  end
  if mode == "image" then
    if image == "" then return nil end
    if latex then
      return nil         -- pdfmd's own header file does it (cover_header_args): metadata header-includes are dropped by pdfmd's others
    else
      local picture = pandoc.Image({}, image, "", pandoc.Attr("", {}, {{"width", "100%"}}))
      append(meta, "include-before", pandoc.MetaBlocks({
        pandoc.Div({pandoc.Para({picture})}, pandoc.Attr("pdfmd-cover", {}, {{"style", "break-after: page; page-break-after: always; text-align: center"}}))}))
    end
  elseif latex then
    if plain(meta["pdfmd-cover-latex"]) ~= "0" then append(meta, "classoption", pandoc.MetaString("titlepage")) end
  else
    append(meta, "include-before", pandoc.MetaBlocks({pandoc.RawBlock("html",
      "<style>#title-block-header { break-after: page; page-break-after: always; text-align: center; padding-top: 6cm; }</style>")}))
  end
  return meta
end
