-- Citeproc omits fractional entry-spacing and explicit line-spacing=1 from refs. Recover local style attributes;
-- Pandoc's resource and user-data folders are the same fallbacks used by its style reader.
local function attribute(meta, key)
  if meta.csl == nil then return nil end
  local style = pandoc.utils.stringify(meta.csl)
  if style:match("^https?://") then return nil end  -- pdfmd's remote-style resolver normally supplies a local file
  local names = {style}
  for _, folder in ipairs(PANDOC_STATE.resource_path or {}) do names[#names + 1] = folder .. "/" .. style end
  local data = PANDOC_STATE.user_data_dir
  if data then
    names[#names + 1] = tostring(data) .. "/csl/" .. style
    names[#names + 1] = tostring(data) .. "/" .. style
  end
  for _, name in ipairs(names) do
    local file = io.open(name, "rb")
    if file then
      local text = file:read("*a"); file:close()
      text = text:gsub("<!%-%-.-%-%->", "")
      local attrs = text:match("<[%w_:%-]*bibliography%s+([^>]*)>")
      return attrs and tonumber(attrs:match(key:gsub("%-", "%%-") .. [=[%s*=%s*['"]([^'"]+)['"]]=]) or "") or nil
    end
  end
  return nil
end

return {attribute = attribute}
