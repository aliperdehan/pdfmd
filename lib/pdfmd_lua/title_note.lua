-- Audited Pandoc default title blocks: Word, ODT and EPUB print a byline without a title.
-- Python excludes custom templates, defaults files, kits and project filters before adding this filter.
function Meta(meta)
  if FORMAT ~= "latex" and FORMAT ~= "typst"
      and FORMAT ~= "html" and FORMAT ~= "html4" and FORMAT ~= "html5" then return end
  if PANDOC_WRITER_OPTIONS.template == nil then return end
  local variables = PANDOC_WRITER_OPTIONS.variables
  local function present(key)
    local value = variables[key]
    if value ~= nil then return tostring(value) ~= "" end
    value = meta[key]
    return value ~= nil and value ~= false and pandoc.utils.stringify(value) ~= ""
  end
  if not present("title") and (present("author") or present("date")) then
    io.stderr:write("NOTE  author/date not printed: no title (add `title:`)\n")
  end
end
