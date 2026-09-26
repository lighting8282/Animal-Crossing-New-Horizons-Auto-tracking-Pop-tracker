"""Generate PopTracker logic for the ACNH Manual pack from the apworld data.

Reads gen/_apworld/data/{locations,regions,items,options}.json and writes:
  * scripts/logic/rules_data.lua  - generated rule trees + region graph
  * locations/*.json              - access_rules rewritten to $Rule|<id>

Everything else in the pack is left alone. Re-run after updating _apworld.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
APW = os.path.join(HERE, '_apworld', 'data')
sys.path.insert(0, HERE)
from parse_requires import parse

ROOT_REGION = '__start__'


def load(name):
    with open(os.path.join(APW, name), encoding='utf-8') as f:
        return json.load(f)


def read_pack(rel):
    with open(os.path.join(PACK, rel), encoding='utf-8') as f:
        return json.load(f)


def write_pack(rel, data):
    with open(os.path.join(PACK, rel), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.write('\n')


# --------------------------------------------------------------- item codes
def build_item_codes():
    """Map apworld item NAME -> pack item code, plus progressive stage codes."""
    items = load('items.json')['data']
    id_to_name = {i + 1: it['name'] for i, it in enumerate(items)}

    with open(os.path.join(PACK, 'scripts/autotracking/item_mapping.lua'),
              encoding='utf-8') as f:
        lua = f.read()
    id_to_code = {int(m[0]): m[1]
                  for m in re.findall(r'\[(\d+)\]\s*=\s*\{\{"([^"]+)"', lua)}

    name_to_code = {}
    for ap_id, code in id_to_code.items():
        name = id_to_name.get(ap_id)
        if name is None:
            raise SystemExit('item_mapping has id %d with no apworld item' % ap_id)
        name_to_code[name] = code

    stages = {}
    for it in read_pack('items/items.json'):
        if it.get('type') != 'progressive':
            continue
        base, per_stage = None, []
        for idx, st in enumerate(it.get('stages', [])):
            codes = [c.strip() for c in str(st.get('codes', '')).split(',') if c.strip()]
            if idx == 0:
                base = codes[0] if codes else None
            want = '%s_stage%d' % (base, idx + 1)
            per_stage.append(want if want in codes else (codes[-1] if codes else None))
        if base:
            stages[base] = per_stage
    return name_to_code, stages


def code_for(name, count, name_to_code, stages):
    code = name_to_code.get(name)
    if code is None:
        raise SystemExit('no pack item code for apworld item %r' % name)
    if count <= 1:
        return code
    per_stage = stages.get(code)
    if not per_stage:
        raise SystemExit('requires |%s:%d| but %r is not progressive in the pack'
                         % (name, count, code))
    if count > len(per_stage):
        raise SystemExit('requires |%s:%d| but %r only has %d stages'
                         % (name, count, code, len(per_stage)))
    return per_stage[count - 1]


def build_option_values():
    opts = load('options.json')
    values = {}
    for sec in ('core', 'user'):
        for k, v in opts.get(sec, {}).items():
            if isinstance(v, dict) and isinstance(v.get('values'), dict) and v['values']:
                values[k] = {str(n).lower(): int(num) for n, num in v['values'].items()}
    return values


# --------------------------------------------------------------- tree -> lua
def flatten(node):
    """Collapse nested same-operator nodes; AND/OR are associative."""
    op = node[0]
    if op in ('item', 'yaml'):
        return node
    parts = []
    for child in node[1:]:
        child = flatten(child)
        if child[0] == op:
            parts.extend(child[1:])
        else:
            parts.append(child)
    return (op,) + tuple(parts)


def lua_str(s):
    return '"%s"' % s.replace('\\', '\\\\').replace('"', '\\"')


def tree_to_lua(node, name_to_code, stages, option_values):
    op = node[0]
    if op == 'item':
        return '{"i",%s}' % lua_str(code_for(node[1], node[2], name_to_code, stages))
    if op == 'yaml':
        _, opt, cmp_op, raw = node
        mapped = option_values.get(opt, {}).get(str(raw).lower())
        if mapped is None:
            try:
                mapped = int(raw)
            except ValueError:
                raise SystemExit('YamlCompare(%s %s %s): cannot resolve value'
                                 % (opt, cmp_op, raw))
        return '{"y",%s,%s,%d}' % (lua_str(opt), lua_str(cmp_op), mapped)
    tag = 'a' if op == 'and' else 'o'
    inner = ','.join(tree_to_lua(c, name_to_code, stages, option_values)
                     for c in node[1:])
    return '{"%s",%s}' % (tag, inner)


def emit(node, *a):
    return 'nil' if node is None else tree_to_lua(flatten(node), *a)


# ----------------------------------------------------------- locations/*.json
def load_location_paths():
    """Map the pack's section path -> Archipelago location id."""
    with open(os.path.join(PACK, 'scripts/autotracking/location_mapping.lua'),
              encoding='utf-8') as f:
        lua = f.read()
    paths = {}
    for loc_id, path in re.findall(r'\[(\d+)\]\s*=\s*\{"([^"]+)"', lua):
        if path in paths:
            raise SystemExit('location path %r mapped twice' % path)
        paths[path] = int(loc_id)
    return paths


def patch_locations(path_to_id):
    """Rewrite access_rules: sections get $Rule|<id>, containers get nothing.

    Sections declared with `ref` are mirrors of a section defined elsewhere
    (Overworld.json is a flat index of the map files), so they inherit that
    section's rule and must not get one of their own.
    """
    stats = {'ruled': 0, 'refs': 0, 'nodes': 0, 'unmatched': []}

    def walk(nodes, prefix):
        for node in nodes:
            name = node.get('name', '')
            here = prefix + '/' + name if prefix else '@' + name
            if 'access_rules' in node:
                node['access_rules'] = []
                stats['nodes'] += 1
            for section in node.get('sections', []):
                if 'ref' in section:
                    section.pop('access_rules', None)
                    stats['refs'] += 1
                    continue
                spath = here + '/' + section.get('name', '')
                loc_id = path_to_id.get(spath)
                if loc_id is None:
                    stats['unmatched'].append(spath)
                    continue
                section['access_rules'] = ['$Rule|%d' % loc_id]
                section['visibility_rules'] = ['$Vis|%d' % loc_id]
                stats['ruled'] += 1
            walk(node.get('children', []), here)

    for fname in sorted(os.listdir(os.path.join(PACK, 'locations'))):
        if not fname.endswith('.json'):
            continue
        rel = 'locations/' + fname
        data = read_pack(rel)
        walk(data, '')
        write_pack(rel, data)
    return stats


def main():
    locs = load('locations.json')['data']
    regions = {k: v for k, v in load('regions.json').items() if not k.startswith('$')}
    name_to_code, stages = build_item_codes()
    args = (name_to_code, stages, build_option_values())

    parents = {name: [] for name in regions}
    for name, d in regions.items():
        for child in d.get('connects_to') or []:
            if child not in parents:
                raise SystemExit('region %r connects to unknown %r' % (name, child))
            parents[child].append(name)
    starting = [n for n, d in regions.items() if d.get('starting')] or list(regions)
    for n in starting:
        parents[n].append(ROOT_REGION)

    out = ['-- GENERATED by gen/build_logic.py -- do not edit by hand.',
           '-- Source: gen/_apworld/data/{locations,regions}.json',
           '',
           'REGION_RULES = {']
    for name in sorted(regions):
        plist = ','.join(lua_str(p) for p in sorted(parents[name]))
        out.append('\t[%s] = {parents={%s}, req=%s},'
                   % (lua_str(name), plist, emit(parse(regions[name].get('requires')), *args)))
    out += ['}', '', 'LOCATION_RULES = {']
    n_req = 0
    for idx, loc in enumerate(locs):
        tree = parse(loc.get('requires'))
        n_req += tree is not None
        out.append('\t[%d] = {region=%s, req=%s},'
                   % (idx + 1, lua_str(loc.get('region', '')), emit(tree, *args)))
    out += ['}', '']

    path = os.path.join(PACK, 'scripts/logic/rules_data.lua')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    print('wrote scripts/logic/rules_data.lua: %d locations (%d with own requires), %d regions'
          % (len(locs), n_req, len(regions)))

    path_to_id = load_location_paths()
    if len(path_to_id) != len(locs):
        raise SystemExit('location_mapping has %d paths but the apworld has %d locations'
                         % (len(path_to_id), len(locs)))
    stats = patch_locations(path_to_id)
    print('patched locations/*.json: %d sections ruled, %d refs left alone, %d container nodes opened'
          % (stats['ruled'], stats['refs'], stats['nodes']))
    if stats['unmatched']:
        print('WARNING: %d sections had no location id:' % len(stats['unmatched']))
        for p in stats['unmatched'][:10]:
            print('   ' + p)
        raise SystemExit(1)
    if stats['ruled'] != len(locs):
        raise SystemExit('ruled %d sections but the apworld has %d locations'
                         % (stats['ruled'], len(locs)))


if __name__ == '__main__':
    main()
