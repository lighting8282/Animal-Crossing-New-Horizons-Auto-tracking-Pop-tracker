-- Logic evaluator for the ACNH Manual pack.
--
-- The rule trees themselves live in rules_data.lua, which is GENERATED from
-- the apworld by gen/build_logic.py. This file is the hand-written runtime
-- that walks those trees. Semantics are a deliberate match for Manual's own
-- evaluator (see gen/parse_requires.py for the details that matter).
--
-- Reachability of a location = its region chain is reachable
--                              AND its own `requires` passes.

require("scripts.logic.rules_data")

local ROOT_REGION = "__start__"

-- Region results are memoised for one evaluation pass. PopTracker recomputes
-- access on item state change, and the "*" watch registered at the bottom
-- clears the cache at exactly those moments. Slot data arriving also lands
-- here, because archipelago.lua's ForceUpdate() toggles the `update` item.
local region_cache = {}

local function has(code)
	return (Tracker:ProviderCountForCode(code) or 0) > 0
end

---Evaluate a {YamlCompare(option op value)} node against the AP slot data.
---Returns nil when slot data is unavailable, so callers can fall back.
local function yaml_compare(option, op, want)
	if SLOT_DATA == nil then
		return nil
	end
	local have = SLOT_DATA[option]
	if have == nil then
		return nil
	end
	have = tonumber(have)
	if have == nil then
		return nil
	end
	if op == "==" then return have == want end
	if op == "!=" then return have ~= want end
	if op == ">"  then return have >  want end
	if op == "<"  then return have <  want end
	if op == ">=" then return have >= want end
	if op == "<=" then return have <= want end
	print(string.format("rules.lua: unknown YamlCompare operator %q", tostring(op)))
	return nil
end

local eval

---@param node table generated rule node: {"i",code} {"y",opt,op,val} {"a",...} {"o",...}
---@return boolean
eval = function(node)
	local tag = node[1]
	if tag == "i" then
		return has(node[2])
	elseif tag == "y" then
		local ok = yaml_compare(node[2], node[3], node[4])
		if ok == nil then
			-- Not connected yet (or the option is missing from slot data).
			-- Treat the comparison as satisfied so the map stays usable
			-- offline instead of hiding every season-gated check.
			return true
		end
		return ok
	elseif tag == "a" then
		for i = 2, #node do
			if not eval(node[i]) then
				return false
			end
		end
		return true
	elseif tag == "o" then
		for i = 2, #node do
			if eval(node[i]) then
				return true
			end
		end
		return false
	end
	print(string.format("rules.lua: unknown rule node tag %q", tostring(tag)))
	return true
end

---@param name string region name, or ROOT_REGION
---@return boolean
local function region_reachable(name)
	if name == nil or name == "" or name == ROOT_REGION then
		return true
	end
	local cached = region_cache[name]
	if cached ~= nil then
		return cached
	end
	local region = REGION_RULES[name]
	if region == nil then
		print(string.format("rules.lua: unknown region %q, treating as open", name))
		return true
	end

	-- Guard against a cyclic region graph: mark in-progress as unreachable so
	-- recursion terminates rather than blowing the Lua stack.
	region_cache[name] = false

	local reachable = false
	for _, parent in ipairs(region.parents) do
		if region_reachable(parent) then
			reachable = true
			break
		end
	end
	if reachable and region.req ~= nil then
		reachable = eval(region.req)
	end

	region_cache[name] = reachable
	return reachable
end

---Access rule entry point, referenced from locations/*.json as `$Rule|<id>`.
---@param loc_id string|number Archipelago location id
---@return number 1 when in logic, 0 otherwise
function Rule(loc_id)
	local rule = LOCATION_RULES[tonumber(loc_id)]
	if rule == nil then
		print(string.format("rules.lua: no rule for location id %s", tostring(loc_id)))
		return 1
	end
	if not region_reachable(rule.region) then
		return 0
	end
	if rule.req ~= nil and not eval(rule.req) then
		return 0
	end
	return 1
end

-- Which locations actually exist in this slot. Options like fishsanity and
-- photosanity delete locations at generation time, so a pack that draws all
-- 417 would show checks the player can never make. Rather than replicating
-- that removal logic, we ask the server: archipelago.lua fills ALL_LOCATIONS
-- from MissingLocations + CheckedLocations in OnClear, which is authoritative
-- and needs no maintenance when the apworld's options change.
local present_cache = nil
local present_count = 0

local function add_ids(list)
	if type(list) ~= "table" then
		return
	end
	for _, v in ipairs(list) do
		local n = tonumber(v)
		if n ~= nil and present_cache[n] == nil then
			present_cache[n] = true
			present_count = present_count + 1
		end
	end
end

local function location_present(loc_id)
	if present_cache == nil then
		present_cache = {}
		present_count = 0
		-- Read Archipelago's LIVE lists rather than ALL_LOCATIONS, which is a
		-- snapshot archipelago.lua takes in OnClear -- the clear handler can
		-- run before PopTracker has populated them, and an empty snapshot
		-- leaves every location visible. ALL_LOCATIONS stays as a fallback.
		if Archipelago ~= nil then
			add_ids(Archipelago.MissingLocations)
			add_ids(Archipelago.CheckedLocations)
		end
		if present_count == 0 then
			add_ids(ALL_LOCATIONS)
		end
	end
	if present_count == 0 then
		-- Not connected yet: show everything rather than an empty map.
		return true
	end
	return present_cache[loc_id] == true
end

---Visibility rule entry point, referenced as `$Vis|<id>`.
---@param loc_id string|number Archipelago location id
---@return number 1 when the location exists in this slot, 0 otherwise
function Vis(loc_id)
	return location_present(tonumber(loc_id)) and 1 or 0
end

---Access rule entry point for whole-region nodes, as `$Region|<name>`.
---@param name string region name
---@return number 1 when in logic, 0 otherwise
function Region(name)
	return region_reachable(name) and 1 or 0
end

ScriptHost:AddWatchForCode("rules cache reset", "*", function()
	region_cache = {}
	present_cache = nil
end)
