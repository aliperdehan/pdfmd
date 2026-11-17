-- Shared by document and div indentation. Defaults and units retain the div syntax.
local DEFAULT = "1.5em"
local UNITS = {em = true, ex = true, pt = true, cm = true, mm = true, ["in"] = true, bp = true, pc = true,
  px = true, rem = true, ["%"] = true}
local WORDS = {["false"] = "off", no = "off", off = "off", ["true"] = "on", yes = "on", on = "on"}

-- "0pt" for off, a length for the rest, nil (and a WARN later) for something else
local function length(value)
  value = value:match("^%s*(.-)%s*$")
  local word = WORDS[value:lower()]
  if word == "off" then return "0pt" end
  if word == "on" then return DEFAULT end
  local number, unit = value:match("^(%-?%d*%.?%d+)%s*(%a*%%?)$")
  if not number then return nil end
  if unit == "" then unit = "em" end
  if not UNITS[unit:lower()] then return nil end
  if tonumber(number) == 0 then return "0pt" end
  return number .. unit:lower()
end


return {length = length, default = DEFAULT, units = UNITS}
