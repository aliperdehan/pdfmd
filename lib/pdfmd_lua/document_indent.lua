-- The document's first-line indent. Values share the div's parser; office references convert lengths to twips.
local here = (PANDOC_SCRIPT_FILE or ""):gsub("[^/\\]*$", "")
local lengths = dofile(here .. "indent_length.lua")
local target = FORMAT:lower():gsub("[+-].*$", "")
local document_length = nil

function Meta(meta)
  local given = meta["pdfmd-document-indent"]
  if given == nil then given = meta.indent end
  if given == nil then return nil end
  local text = pandoc.utils.stringify(given):lower()
  if text == "true" or text == "yes" or text == "on" or text == "1" then
    -- `true` keeps each writer's indent as it was before lengths existed: LaTeX the class's own \parindent (17pt
    -- at 11pt), Typst 1.5em, Word 0.25in, HTML none. Only a length is new; `pdfmd-options` turns Pandoc's switch on.
    meta.indent = pandoc.MetaBool(true)
    return meta
  end
  local value = lengths.length(pandoc.utils.stringify(given))
  if value == nil then error("indent must be false, true, or a length such as 0.5in, 3em, 1cm") end
  -- False and unset retain the writer's defaults.
  if value == "0pt" then
    if meta["pdfmd-document-indent"] ~= nil then meta.indent = pandoc.MetaBool(false); return meta end
    return nil
  end
  meta.indent = pandoc.MetaBool(true)
  meta["pdfmd-document-indent-length"] = pandoc.MetaString(value)
  document_length = value
  return meta
end

function Pandoc(doc)
  if not document_length then return nil end
  local value = document_length
  if target == "latex" or target == "beamer" then
    doc.blocks:insert(1, pandoc.RawBlock("latex", "\\setlength{\\parindent}{" .. value .. "}"))
  elseif target:match("^html") or target:match("^epub") then
    doc.blocks:insert(1, pandoc.RawBlock("html", "<style>\nbody { text-indent: " .. value .. "; }\n"
      .. "h1, h2, h3, h4, h5, h6, pre, table, ul, ol, blockquote { text-indent: 0; }\n</style>"))
  end
  return doc
end
