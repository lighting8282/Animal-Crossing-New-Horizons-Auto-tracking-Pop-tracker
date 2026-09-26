"""Sanity check: how many checks open up at realistic progression points.

Parity tests prove we agree with Manual. This one proves the result is
actually *useful* - i.e. the map gates at the start and opens as items come
in, rather than being all-green or all-red.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_lua_parity import LuaHarness  # noqa: E402

APW = os.path.join(HERE, '_apworld', 'data')
LOCS = json.load(open(os.path.join(APW, 'locations.json'), encoding='utf-8'))['data']

STEPS = [
    ('nothing (fresh slot)', {}),
    ('+ Net 1', {'Progressive Net': 1}),
    ('+ Axe 1 (Nook\'s Cranny)', {'Progressive Net': 1, 'Progressive Axe': 1}),
    ('+ 3 Villagers', {'Progressive Net': 1, 'Progressive Axe': 1,
                       'Progressive Villager': 3}),
    ('all tools maxed + 8 villagers', {
        'Progressive Net': 2, 'Progressive Fishing Rod': 2,
        'Progressive Shovel': 2, 'Progressive Axe': 2,
        'Progressive Watering Can': 2, 'Vaulting Pole': 1, 'Ladder': 1,
        'Progressive Villager': 8}),
]


def main():
    harness = LuaHarness()
    options = {'hemisphere': 0, 'fishsanity': 0, 'bugsanity': 0, 'seasanity': 0}
    print('%-34s %s' % ('state', 'in logic / 417'))
    prev = None
    for label, inv in STEPS:
        harness.set_state(inv, options)
        n = sum(1 for i in range(1, len(LOCS) + 1) if harness.Rule(i))
        delta = '' if prev is None else '  (%+d)' % (n - prev)
        print('%-34s %3d%s' % (label, n, delta))
        prev = n

    # offline behaviour: no slot data at all must not crash
    harness.set_state({}, None)
    n = sum(1 for i in range(1, len(LOCS) + 1) if harness.Rule(i))
    print('\nno slot data, empty inventory:  %d in logic '
          '(season gates treated as open)' % n)

    # everything, both hemispheres
    full = {'Progressive Net': 2, 'Progressive Fishing Rod': 2,
            'Progressive Shovel': 2, 'Progressive Axe': 2,
            'Progressive Watering Can': 2, 'Progressive Inventory Space': 2,
            'Progressive Villager': 8}
    items = json.load(open(os.path.join(APW, 'items.json'), encoding='utf-8'))['data']
    for it in items:
        full.setdefault(it['name'], int(it.get('count', 1) or 1))
    for hemi, name in ((0, 'northern'), (1, 'southern')):
        harness.set_state(full, dict(options, hemisphere=hemi))
        n = sum(1 for i in range(1, len(LOCS) + 1) if harness.Rule(i))
        print('every item, %-8s hemisphere: %d in logic' % (name, n))


if __name__ == '__main__':
    main()
