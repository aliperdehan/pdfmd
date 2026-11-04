-- Metadata values that APPEND instead of replace (v3.31.40, entry 3du point 20).
--
-- pdfmd merges the layers itself (global metadata, a folder's .pdfmd/metadata.yaml, metadata/, the document's own front
-- matter: `author+: [B]` adds to what the layers below hold, and `pdfmd-options: {metadata-append: [author]}` makes the
-- document's own `author:` add to it too) and hands the finished values over in a metadata file under `pdfmd-merged`.
-- Pandoc cannot do this part: the document's front matter beats every metadata file, so a file could never replace the
-- value the document itself sets. This filter runs FIRST, so every other filter and the template see the finished value,
-- and it removes the `key+` keys, which no template knows.

function Meta(meta)
  local merged = meta["pdfmd-merged"]
  if merged ~= nil then
    local keys = {}
    for key in pairs(merged) do keys[#keys + 1] = key end
    for _, key in ipairs(keys) do meta[key] = merged[key] end
    meta["pdfmd-merged"] = nil
  end
  local plus = {}
  for key in pairs(meta) do
    if type(key) == "string" and #key > 1 and key:sub(-1) == "+" then plus[#plus + 1] = key end
  end
  for _, key in ipairs(plus) do meta[key] = nil end
  return meta
end
