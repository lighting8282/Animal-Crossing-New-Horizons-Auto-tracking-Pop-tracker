"""Regression test for progressive item stages coming from Archipelago.

The pack's ItemUpdate incremented CurrentStage without ever setting Active.
These items are `allow_disabled` with `initial_stage_idx: 0`, so stage index 0
is the FIRST stage and "none" is Active == false - meaning the first received
copy jumped straight to stage 2 and every progressive read one too high.

This loads the real archipelago.lua with stubbed PopTracker globals and checks
that receiving N copies lands on stage N.
"""
import os
import re
import sys

import lupa

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)

PREAMBLE = """
_items = {}
-- Models PopTracker's allow_disabled progressive item: a CurrentStage write is
-- DISCARDED while the item is inactive, and activating it lands on the first
-- stage. Getting that ordering wrong silently caps every item at stage 1.
-- CurrentStage is 1-based: 0 means disabled, 1..n are the stages. Confirmed
-- by readback logging against the real PopTracker (after N received copies
-- CurrentStage reads exactly N). A write is discarded while disabled, and
-- activating lands on stage 1.
function _mkitem(code, typ, stages)
    local b = {Name = code, Type = typ, _stage = 0, _stages = stages or 1}
    local proxy = setmetatable({}, {
        __index = function(_, k)
            if k == "CurrentStage" then return b._stage end
            if k == "Active" then return b._stage > 0 end
            return b[k]
        end,
        __newindex = function(_, k, v)
            if k == "CurrentStage" then
                if b._stage > 0 then
                    if v < 0 then v = 0 elseif v > b._stages then v = b._stages end
                    b._stage = v
                end
            elseif k == "Active" then
                if v then
                    if b._stage == 0 then b._stage = 1 end
                else
                    b._stage = 0
                end
            else
                b[k] = v
            end
        end,
    })
    _items[code] = proxy
    return proxy
end
-- Force an item to a stage, as restoring an autosave would.
function _restore(code, stage)
    _items[code].Active = true
    _items[code].CurrentStage = stage
end
Tracker = {}
function Tracker:FindObjectForCode(code) return _items[code] end
ScriptHost = {}
function ScriptHost:AddWatchForCode(...) end
function ScriptHost:AddOnFrameHandler(...) end
function ScriptHost:RemoveOnFrameHandler(...) end
function ScriptHost:CreateLuaItem() return {} end
Archipelago = {PlayerNumber = 1, TeamNumber = 0,
               MissingLocations = {}, CheckedLocations = {}}
function Archipelago:SetNotify(...) end
function Archipelago:Get(...) end
function require(_) return true end
"""


def compat(src):
    """Make the source loadable under lupa's Lua 5.5.

    5.5 made `for` control variables const; PopTracker runs an older Lua where
    DumpTable's `k = '"' .. k .. '"'` is legal. Rebind to a local for the test
    only - this does not change what ships.
    """
    return src.replace(
        "        for k, v in pairs(o) do\n"
        "            if type(k) ~= 'number' then\n",
        "        for k0, v in pairs(o) do\n"
        "            local k = k0\n"
        "            if type(k) ~= 'number' then\n")


def stage_of(harness, code):
    # CurrentStage is 1-based with 0 = none, so it IS the copy count.
    return harness.globals()._items[code].CurrentStage


def main():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(PREAMBLE)
    for path in ('scripts/autotracking/item_mapping.lua',
                 'scripts/autotracking/location_mapping.lua',
                 'scripts/autotracking/archipelago.lua'):
        with open(os.path.join(PACK, path), encoding='utf-8') as f:
            lua.execute(compat(f.read()))

    # Build the fake items the mapping refers to, with real stage counts.
    import json
    pack_items = json.load(open(os.path.join(PACK, 'items/items.json'), encoding='utf-8'))
    stages = {}
    for it in pack_items:
        if it.get('type') == 'progressive':
            base = str(it['stages'][0].get('codes', '')).split(',')[0].strip()
            stages[base] = len(it['stages'])
    mkitem = lua.globals()._mkitem
    mapping = {}
    src = open(os.path.join(PACK, 'scripts/autotracking/item_mapping.lua'),
               encoding='utf-8').read()
    for ap_id, code in re.findall(r'\[(\d+)\]\s*=\s*\{\{"([^"]+)"', src):
        typ = 'progressive' if code in stages else 'toggle'
        mkitem(code, typ, stages.get(code, 1))
        mapping[code] = int(ap_id)

    on_item = lua.globals().OnItem
    failures = 0
    index = 0
    # Mirrors Lights_ACNH's real deliveries, including the counts >= 2 that
    # exposed the activate-then-set-stage ordering bug.
    cases = [('progressiveshovel', 1), ('progressiveaxe', 1),
             ('progressivevillager', 4), ('progressivefishingrod', 2),
             ('progressivewateringcan', 2), ('progressivenet', 0)]
    print('%-26s %8s %8s' % ('item', 'received', 'stage'))
    for code, n in cases:
        for _ in range(n):
            index += 1
            on_item(index, mapping[code], code, 1)
        got = stage_of(lua, code)
        ok = got == n
        failures += not ok
        print('%-26s %8d %8d  %s' % (code, n, got, 'ok' if ok else 'WRONG'))

    # A reset (what OnClear does) must clear both stage and the counter,
    # so a reconnect that replays the same items lands in the same place.
    # Mirror what OnClear does: rewind the item index and clear the counters.
    lua.execute('PROGRESSIVE_COUNTS = {}; CUR_INDEX = -1')
    for code, _ in cases:
        item = lua.globals()._items[code]
        item.CurrentStage = 0
        item.Active = False
    index = 0
    for code, n in cases:
        for _ in range(n):
            index += 1
            on_item(index, mapping[code], code, 1)
    replay_bad = [c for c, n in cases if stage_of(lua, c) != n]
    print('\nreplay after reset matches: %s' % ('yes' if not replay_bad else replay_bad))
    failures += len(replay_bad)

    # Regression for the 4+3=7 bug: PopTracker restores the autosave around the
    # time the clear handler runs, so an item can already hold last session's
    # stage when the replay starts. The result must depend only on the replayed
    # copy count, never on what the item happened to contain.
    lua.execute('PROGRESSIVE_COUNTS = {}; CUR_INDEX = -1')
    restore = lua.globals()._restore
    restore('progressivevillager', 4)
    restore('progressivefishingrod', 2)
    index = 0
    for code, n in cases:
        for _ in range(n):
            index += 1
            on_item(index, mapping[code], code, 1)
    stale_bad = [(c, stage_of(lua, c), n) for c, n in cases if stage_of(lua, c) != n]
    print('stale restored state ignored: %s'
          % ('yes' if not stale_bad else stale_bad))
    failures += len(stale_bad)

    print('failures: %d' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
