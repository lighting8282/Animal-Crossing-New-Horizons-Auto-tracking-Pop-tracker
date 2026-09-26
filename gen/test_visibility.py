"""Check Vis() hides exactly the locations the server didn't send.

Options like fishsanity/photosanity delete locations at generation time. The
pack asks the server which locations exist (ALL_LOCATIONS, filled by
archipelago.lua from MissingLocations + CheckedLocations) rather than
replicating that logic, so this test feeds the harness a realistic location
set and checks Vis() agrees.

The expected set is derived independently, by reading the removal lists out of
the apworld's after_create_regions hook.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_lua_parity import LuaHarness  # noqa: E402

APW = os.path.join(HERE, '_apworld')
LOCS = json.load(open(os.path.join(APW, 'data/locations.json'), encoding='utf-8'))['data']


def removed_for(photono, fish, bug, sea):
    """Parse the apworld's removal lists and evaluate them for these options."""
    src = open(os.path.join(APW, 'hooks/World.py'), encoding='utf-8').read()
    start = src.index('def after_create_regions')
    body = src[start:src.index('\ndef ', start + 10)]
    env = {'photono': photono, 'fish': fish, 'bug': bug, 'sea': sea}
    removed, active = set(), None
    for line in body.splitlines():
        s = line.strip()
        m = re.match(r'^if (.+):$', s)
        if m:
            try:
                active = bool(eval(m.group(1), {}, env))
            except Exception:
                active = None
            continue
        m = re.match(r'^locationNamesToRemove\.append\("(.+)"\)$', s)
        if m and active:
            removed.add(m.group(1))
    return removed


def slot_location_ids(photono, fish, bug, sea, post_game_checks=True):
    """The AP location ids a slot actually receives, applying all three cuts.

    1. hooks/World.py after_create_regions removes by sanity/photo options.
    2. categories.json gates a whole category on a yaml option - "Post-Game
       Checks" carries `"yaml_option": ["post_game_checks"]`, which is Manual
       CORE behaviour, not something the world's hooks implement. Grepping the
       hooks alone makes the option look dead; it isn't.
    3. Victory locations become events, not checks.
    """
    removed = removed_for(photono, fish, bug, sea)
    opts = {'post_game_checks': post_game_checks}
    cats = json.load(open(os.path.join(APW, 'data/categories.json'), encoding='utf-8'))
    off = {c for c, d in cats.items()
           for o in (d.get('yaml_option') or []) if not opts.get(o, True)}
    ids = []
    for i, l in enumerate(LOCS):
        if l['name'] in removed:
            continue
        if set(l.get('category') or []) & off:
            continue
        if l.get('victory'):
            continue
        ids.append(i + 1)
    return ids


def main():
    # Lights_ACNH's resolved YAML: everything sanity-related off.
    cases = [
        ('Lights_ACNH (sanity none, no post-game)',
         dict(photono=0, fish=3, bug=3, sea=2, post_game_checks=False)),
        ('everything on',
         dict(photono=10, fish=0, bug=0, sea=0, post_game_checks=True)),
        ('tough excluded, post-game on',
         dict(photono=5, fish=2, bug=2, sea=1, post_game_checks=True)),
    ]
    harness = LuaHarness()
    failures = 0
    for label, opts in cases:
        present_ids = slot_location_ids(**opts)
        harness.set_state({}, {'hemisphere': 0})
        # Live lists are the primary source now; ALL_LOCATIONS is the fallback.
        harness.lua.globals().Archipelago.MissingLocations = harness.lua.table(*present_ids)
        harness.lua.globals().Archipelago.CheckedLocations = harness.lua.table()
        harness.lua.globals().ALL_LOCATIONS = harness.lua.table()
        harness.reset_cache()

        present = set(present_ids)
        wrong = [i + 1 for i in range(len(LOCS))
                 if bool(harness.Vis(i + 1)) != ((i + 1) in present)]
        print('%-42s slot has %3d/%d locations, Vis mismatches: %d'
              % (label, len(present), len(LOCS), len(wrong)))
        failures += len(wrong)

    # Not connected: nothing known -> show everything.
    harness.lua.globals().Archipelago.MissingLocations = harness.lua.table()
    harness.lua.globals().ALL_LOCATIONS = harness.lua.table()
    harness.reset_cache()
    shown = sum(1 for i in range(1, len(LOCS) + 1) if harness.Vis(i))
    print('%-42s shows %d/%d' % ('not connected (empty ALL_LOCATIONS)', shown, len(LOCS)))
    if shown != len(LOCS):
        failures += 1

    # Everything absent -> must not error.
    harness.lua.globals().Archipelago.MissingLocations = None
    harness.lua.globals().ALL_LOCATIONS = None
    harness.reset_cache()
    shown = sum(1 for i in range(1, len(LOCS) + 1) if harness.Vis(i))
    print('%-42s shows %d/%d' % ('ALL_LOCATIONS nil', shown, len(LOCS)))
    if shown != len(LOCS):
        failures += 1

    # Regression: OnClear snapshotted an empty ALL_LOCATIONS (the clear handler
    # can run before PopTracker fills MissingLocations). The live lists must
    # still drive visibility.
    present_ids = slot_location_ids(photono=0, fish=3, bug=3, sea=2,
                                    post_game_checks=False)
    harness.lua.globals().ALL_LOCATIONS = harness.lua.table()   # empty snapshot
    harness.lua.globals().Archipelago.MissingLocations = harness.lua.table(*present_ids)
    harness.lua.globals().Archipelago.CheckedLocations = harness.lua.table()
    harness.reset_cache()
    shown = sum(1 for i in range(1, len(LOCS) + 1) if harness.Vis(i))
    print('%-42s shows %d/%d (expect %d)'
          % ('empty ALL_LOCATIONS, live lists set', shown, len(LOCS), len(present_ids)))
    if shown != len(present_ids):
        failures += 1

    print('failures: %d' % failures)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
