-- Second of the two (see header_snap.lua), the last filter of the build: `header-includes` becomes the header files
-- pdfmd passed as -M pdfmd-header-file-1, -2 ... (in that order), with whatever the other filters added to it
-- put in front of the packages header (packages-*.tex, which must see everything) or else at the end.
local utils = pandoc.utils

-- what an item of `header-includes` says, as LaTeX: stringify would give "" for a raw block, so every raw item would look alike
local function key(item)
  local kind = utils.type(item)
  local document
  if kind == "Blocks" then document = pandoc.Pandoc(item)
  elseif kind == "Inlines" then document = pandoc.Pandoc(pandoc.Blocks{pandoc.Plain(item)})
  elseif kind == "string" then return item
  else return utils.stringify(item) end
  local ok, text = pcall(pandoc.write, document, "latex")
  return ok and text or utils.stringify(item)
end

local function items_of(value)
  if value == nil then return {} end
  if utils.type(value) == "List" then return value end
  return { value }
end

function Meta(meta)
  local base = {}
  for _, item in ipairs(items_of(meta["pdfmd-header-base"])) do base[key(item)] = true end
  local added = {}
  for _, item in ipairs(items_of(meta["header-includes"])) do
    if not base[key(item)] then added[#added + 1] = item end
  end
  local merged, placed = pandoc.MetaList({}), false
  local function put_added()
    if placed then return end
    placed = true
    for _, item in ipairs(added) do merged[#merged + 1] = item end
  end
  local index = 1
  while meta["pdfmd-header-file-" .. index] ~= nil do
    local name = utils.stringify(meta["pdfmd-header-file-" .. index])
    meta["pdfmd-header-file-" .. index] = nil
    if name:match("^packages%-[^/\\]*$") or name:match("[/\\]packages%-[^/\\]*$") then put_added() end
    local handle = io.open(name, "rb")
    if handle then
      local text = handle:read("a")
      handle:close()
      merged[#merged + 1] = pandoc.MetaBlocks({ pandoc.RawBlock("latex", text) })
    else
      io.stderr:write("WARN  header files: could not read " .. name .. "\n")
    end
    index = index + 1
  end
  put_added()
  meta["header-includes"] = merged
  meta["pdfmd-header-base"] = nil
  return meta
end
