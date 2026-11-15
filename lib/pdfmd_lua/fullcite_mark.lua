-- pdfmd: the full reference in place, first half (runs BEFORE --citeproc; fullcite.lua is the second half, after it).
--
-- Three spellings ask for the formatted reference of a source at the spot where they stand:
--
--     [@trinkaus1984]{.fullcite}        a bracketed span around a real citation (the recommended form)
--     [[fullcite:trinkaus1984]]         the older spelling, alone in its paragraph
--     ::: fullcite                      a block, one `@key` for each entry
--     @trinkaus1984
--     @gould1981
--     :::
--
-- This half turns every spelling into the first one, whose citation citeproc then loads (so the key needs no `nocite`), and
-- records the keys in the span's `pdfmd-keys` attribute, because once citeproc has run the citation is only text. A `list`
-- attribute on the block (`::: {.fullcite list=keep}`) goes to each entry of it that has none of its own.
--
-- With `-M pdfmd-fullcite-engine=biblatex` (or natbib) there is no citeproc: the span becomes `\fullcite{KEY}` (`\bibentry{KEY}`).
--
-- Added by pdfmd only for a document that uses one of the spellings and carries the `fullcite` markup kind.

local engine = nil      -- set from the metadata when the document comes in
local used = false      -- a span became a raw command

local function cite_of(key)
  return pandoc.Cite({pandoc.Str("@" .. key)}, {pandoc.Citation(key, "AuthorInText")})
end

local function marker(key, attributes)
  return pandoc.Span({cite_of(key)}, pandoc.Attr("", {"fullcite"}, attributes or {}))
end

local function keys_in(inlines)
  local keys = {}
  pandoc.Inlines(inlines):walk({
    Cite = function(cite)
      for _, citation in ipairs(cite.citations) do keys[#keys + 1] = citation.id end
    end,
  })
  return keys
end

local function raw_for(keys)
  used = true
  local command = engine == "natbib" and "\\bibentry" or "\\fullcite"
  local out = pandoc.List()
  for number, key in ipairs(keys) do
    if number > 1 then out:insert(pandoc.Space()) end
    out:insert(pandoc.RawInline("latex", command .. "{" .. key .. "}"))
  end
  return out
end

-- a paragraph that is only the old spelling
local function old_spelling(block)
  if #block.content ~= 1 or block.content[1].t ~= "Str" then return nil end
  return block.content[1].text:match("^%[%[fullcite:([^%[%]|]+)%]%]$")
end

local function paragraph(block)
  local key = old_spelling(block)
  if not key then return nil end
  return (block.t == "Plain" and pandoc.Plain or pandoc.Para)({marker(key)})
end

local function block(div)
  if not div.classes:includes("fullcite") then return nil end
  local attributes = {}
  if div.attributes["list"] then attributes.list = div.attributes["list"] end
  local out = pandoc.List()
  pandoc.Blocks(div.content):walk({
    Cite = function(cite)
      for _, citation in ipairs(cite.citations) do out:insert(pandoc.Para({marker(citation.id, attributes)})) end
    end,
  })
  if #out == 0 then return nil end
  return out
end

local function span(element)
  if not element.classes:includes("fullcite") then return nil end
  local keys = keys_in(element.content)
  if #keys == 0 then return nil end
  if engine then return raw_for(keys) end
  element.attributes["pdfmd-keys"] = table.concat(keys, " ")
  return element
end

local function as_list(value)
  if value == nil then return {} end
  if pandoc.utils.type(value) == "List" then return value end
  return {value}
end

-- natbib's \bibentry needs a \nobibliography of the files before the first one (its package comes from pdfmd, as a header file:
-- a header-includes of a filter would be dropped where pdfmd gives Pandoc header files of its own)
local function natbib_files(meta)
  local names = {}
  for _, item in ipairs(as_list(meta.bibliography)) do
    names[#names + 1] = (pandoc.utils.stringify(item):gsub("%.bib$", ""))
  end
  return pandoc.RawBlock("latex", "\\nobibliography{" .. table.concat(names, ",") .. "}")
end

function Pandoc(doc)
  if doc.meta["pdfmd-fullcite-engine"] then engine = pandoc.utils.stringify(doc.meta["pdfmd-fullcite-engine"]) end
  doc = doc:walk({Div = block, Para = paragraph, Plain = paragraph})
  doc = doc:walk({Span = span})
  if engine == "natbib" and used then doc.blocks:insert(1, natbib_files(doc.meta)) end
  return doc
end
