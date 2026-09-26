"""End-to-end differential test: the REAL rules.lua vs Manual's evaluator.

test_parity.py checks the Python-side parse. This one goes further: it loads
scripts/logic/rules.lua and rules_data.lua into a Lua runtime with stubbed
PopTracker globals, then compares Rule(id) against Manual's own
infix_to_postfix/evaluate_postfix pipeline over random world states.

That covers the generated data, the Lua tree walk, the region chain and the
item/stage code resolution in one shot.
"""
import json
import os
import random
import sys

import lupa

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import build_logic
from test_parity import manual_eval, OPTION_VALUES  # noqa: E402

APW = os.path.join(HERE, '_apworld', 'data')


def build_code_thresholds():
    """code -> (apworld item name, count needed to provide that code)."""
    name_to_code, stages = build_logic.build_item_codes()
    out = {}
    for name, code in name_to_code.items():
        out[code] = (name, 1)
        for idx, stage_code in enumerate(stages.get(code, [])):
            if stage_code:
                out[stage_code] = (name, idx + 1)
    return out


class LuaHarness:
    def __init__(self):
        self.inv = {}
        self.thresholds = build_code_thresholds()
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.unknown_codes = set()
        self._install_stubs()
        self._load(os.path.join(PACK, 'scripts/logic/rules_data.lua'))
        self._load(os.path.join(PACK, 'scripts/logic/rules.lua'))
        self.Rule = self.lua.globals().Rule
        self.Vis = self.lua.globals().Vis
        self.Region = self.lua.globals().Region

    def _provider_count(self, _self, code):
        entry = self.thresholds.get(code)
        if entry is None:
            self.unknown_codes.add(code)
            return 0
        name, need = entry
        return 1 if self.inv.get(name, 0) >= need else 0

    def _install_stubs(self):
        g = self.lua.globals()
        self.lua.execute(
            'Tracker = {}; ScriptHost = {}; _watches = {}; ALL_LOCATIONS = {}\n'
            'Archipelago = {PlayerNumber = 1, TeamNumber = 0,\n'
            '               MissingLocations = {}, CheckedLocations = {}}')
        g.Tracker.ProviderCountForCode = self._provider_count
        self.lua.execute(
            'function ScriptHost:AddWatchForCode(name, code, fn)'
            ' _watches[#_watches+1] = fn end')
        # `require` is a no-op: we load the files ourselves, in order.
        self.lua.execute('function require(_) return true end')

    def _load(self, path):
        with open(path, encoding='utf-8') as f:
            src = f.read()
        self.lua.execute(src)

    def reset_cache(self):
        self.lua.execute('for _, fn in ipairs(_watches) do fn() end')

    def set_state(self, inv, options):
        self.inv = inv
        g = self.lua.globals()
        g.SLOT_DATA = self.lua.table_from(options) if options is not None else None
        self.reset_cache()


def main(trials=300, seed=99):
    locs = json.load(open(os.path.join(APW, 'locations.json'), encoding='utf-8'))['data']
    regions = json.load(open(os.path.join(APW, 'regions.json'), encoding='utf-8'))
    regions = {k: v for k, v in regions.items() if not k.startswith('$')}
    items = json.load(open(os.path.join(APW, 'items.json'), encoding='utf-8'))['data']
    maxcount = {i['name']: int(i.get('count', 1) or 1) for i in items}

    # Python-side reference model of the region chain, mirroring Manual:
    # reachable(R) = any(reachable(parent)) and R's own requires.
    parents = {n: [] for n in regions}
    for n, d in regions.items():
        for c in d.get('connects_to') or []:
            parents[c].append(n)
    starting = [n for n, d in regions.items() if d.get('starting')] or list(regions)

    def region_reachable(name, inv, options, seen=None):
        if not name:
            return True
        seen = seen or set()
        if name in seen:
            return False
        seen = seen | {name}
        ok = name in starting or any(
            region_reachable(p, inv, options, seen) for p in parents[name])
        if ok:
            ok = manual_eval(regions[name].get('requires'), inv, options, name)
        return ok

    harness = LuaHarness()
    rng = random.Random(seed)
    mismatches = 0
    checked = 0
    for _ in range(trials):
        inv = {n: rng.randint(0, c) for n, c in maxcount.items()}
        options = {
            'hemisphere': rng.choice([0, 1]),
            'fishsanity': rng.choice([0, 1, 2, 3]),
            'bugsanity': rng.choice([0, 1, 2, 3]),
            'seasanity': rng.choice([0, 1, 2]),
        }
        harness.set_state(inv, options)
        for idx, loc in enumerate(locs):
            loc_id = idx + 1
            want = (region_reachable(loc.get('region'), inv, options)
                    and manual_eval(loc.get('requires'), inv, options, loc['name']))
            got = bool(harness.Rule(loc_id))
            checked += 1
            if want != got:
                mismatches += 1
                if mismatches <= 5:
                    print('MISMATCH id=%d %r region=%r\n  requires: %s\n  manual=%s lua=%s'
                          % (loc_id, loc['name'], loc.get('region'),
                             loc.get('requires'), want, got))
    # Offline: no slot data at all. Must not error, and must be permissive
    # about YamlCompare while still honouring item/region gating.
    harness.set_state({}, None)
    offline_empty = sum(1 for i in range(1, len(locs) + 1) if harness.Rule(i))
    full = {n: c for n, c in maxcount.items()}
    harness.set_state(full, None)
    offline_full = sum(1 for i in range(1, len(locs) + 1) if harness.Rule(i))
    print('offline (no slot data): %d in logic empty-handed, %d with every item'
          % (offline_empty, offline_full))
    if offline_full != len(locs):
        print('WARNING: offline with every item should open everything')
        mismatches += 1
    if offline_empty >= len(locs):
        print('WARNING: offline empty-handed should still be gated')
        mismatches += 1

    # Slot data present but missing the keys the rules ask for.
    harness.set_state(full, {'goal': 0})
    partial = sum(1 for i in range(1, len(locs) + 1) if harness.Rule(i))
    print('slot data missing option keys: %d in logic (expect %d)'
          % (partial, len(locs)))
    if partial != len(locs):
        mismatches += 1

    print('checked %d Rule() calls across %d random states' % (checked, trials))
    if harness.unknown_codes:
        print('UNKNOWN CODES REQUESTED BY LUA: %s' % sorted(harness.unknown_codes))
    print('mismatches: %d' % mismatches)
    return 1 if (mismatches or harness.unknown_codes) else 0


if __name__ == '__main__':
    sys.exit(main())
