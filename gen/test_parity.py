"""Differential test: our expression tree vs Manual's own evaluation pipeline.

Manual's infix_to_postfix / evaluate_postfix are copied VERBATIM from the
apworld's Rules.py (they have no Archipelago dependencies), and the
substitution steps mirror checkRequireStringForArea. For each random world
state we compare Manual's verdict against evaluating our parsed tree.
"""
import json, random, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_requires import parse

HERE = os.path.dirname(os.path.abspath(__file__))
APW = os.path.join(HERE, '_apworld', 'data')

OPTION_VALUES = {}
_opts = json.load(open(os.path.join(APW, 'options.json'), encoding='utf-8'))
for _sec in ('core', 'user'):
    for _k, _v in _opts.get(_sec, {}).items():
        if isinstance(_v, dict) and isinstance(_v.get('values'), dict) and _v['values']:
            OPTION_VALUES[_k] = _v['values']


# ---- verbatim from apworld Rules.py -------------------------------------
def infix_to_postfix(expr, location):
    prec = {"&": 2, "|": 2, "!": 3}
    stack = []
    postfix = ""
    for c in expr:
        if c.isnumeric():
            postfix += c
        elif c in prec:
            while stack and stack[-1] != "(" and prec[c] <= prec[stack[-1]]:
                postfix += stack.pop()
            stack.append(c)
        elif c == "(":
            stack.append(c)
        elif c == ")":
            while stack and stack[-1] != "(":
                postfix += stack.pop()
            stack.pop()
    while stack:
        postfix += stack.pop()
    return postfix


def evaluate_postfix(expr, location):
    stack = []
    for c in expr:
        if c == "0":
            stack.append(False)
        elif c == "1":
            stack.append(True)
        elif c == "&":
            op2 = stack.pop(); op1 = stack.pop(); stack.append(op1 and op2)
        elif c == "|":
            op2 = stack.pop(); op1 = stack.pop(); stack.append(op1 or op2)
        elif c == "!":
            stack.append(not stack.pop())
    if len(stack) != 1:
        raise AssertionError("stack size %d" % len(stack))
    return stack.pop()
# -------------------------------------------------------------------------


def yaml_compare(opt, op, val, options):
    have = options[opt]
    want = OPTION_VALUES.get(opt, {}).get(str(val).lower(), val)
    want = int(want)
    return {'==': have == want, '!=': have != want, '>': have > want,
            '<': have < want, '>=': have >= want, '<=': have <= want}[op]


def manual_eval(req, inv, options, name):
    """Reproduce checkRequireStringForArea's substitution + eval."""
    if not req:
        return True
    s = req
    for m in set(re.findall(r'\{(\w+)\((.*?)\)\}', s)):
        fname, body = m
        mm = re.match(r'^\s*(\w+)\s*(==|!=|>=|<=|>|<)\s*(\S+)\s*$', body)
        ok = yaml_compare(mm.group(1), mm.group(2), mm.group(3), options)
        s = s.replace("{" + fname + "(" + body + ")}", "1" if ok else "0")
    for item in set(re.findall(r'\|[^|]+\|', s)):
        body = item.lstrip('|@$').rstrip('|')
        parts = body.split(':')
        iname = parts[0].strip() if len(parts) > 1 else body
        icount = int(parts[1].strip()) if len(parts) > 1 else 1
        s = s.replace(item, "1" if inv.get(iname, 0) >= icount else "0")
    s = re.sub(r'\s?\bAND\b\s?', '&', s, count=0, flags=re.IGNORECASE)
    s = re.sub(r'\s?\bOR\b\s?', '|', s, count=0, flags=re.IGNORECASE)
    return evaluate_postfix(infix_to_postfix("".join(s), name), name)


def tree_eval(node, inv, options):
    kind = node[0]
    if kind == 'item':
        return inv.get(node[1], 0) >= node[2]
    if kind == 'yaml':
        return yaml_compare(node[1], node[2], node[3], options)
    if kind == 'and':
        return tree_eval(node[1], inv, options) and tree_eval(node[2], inv, options)
    if kind == 'or':
        return tree_eval(node[1], inv, options) or tree_eval(node[2], inv, options)
    raise AssertionError(kind)


def main(trials=400, seed=1234):
    locs = json.load(open(os.path.join(APW, 'locations.json'), encoding='utf-8'))['data']
    regions = json.load(open(os.path.join(APW, 'regions.json'), encoding='utf-8'))
    items = json.load(open(os.path.join(APW, 'items.json'), encoding='utf-8'))['data']
    maxcount = {i['name']: int(i.get('count', 1) or 1) for i in items}

    cases = [(l['name'], l.get('requires')) for l in locs]
    cases += [(n, d.get('requires')) for n, d in regions.items() if not n.startswith('$')]
    trees = {n: parse(r) for n, r in cases}

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
        for name, req in cases:
            want = manual_eval(req, inv, options, name)
            t = trees[name]
            got = True if t is None else tree_eval(t, inv, options)
            checked += 1
            if want != got:
                mismatches += 1
                if mismatches <= 5:
                    print("MISMATCH %r\n  requires: %s\n  manual=%s tree=%s"
                          % (name, req, want, got))
    print("checked %d evaluations across %d random states" % (checked, trials))
    print("mismatches: %d" % mismatches)
    return 1 if mismatches else 0


if __name__ == '__main__':
    sys.exit(main())
