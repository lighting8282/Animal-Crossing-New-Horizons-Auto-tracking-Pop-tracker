"""Parser for Manual's `requires` mini-language.

This is a STRUCTURAL PORT of Manual's own evaluator (Rules.py:
findAndRecursivelyExecuteFunctions -> item substitution -> AND/OR regex ->
infix_to_postfix -> evaluate_postfix). It deliberately reproduces Manual's
quirks rather than "correct" boolean parsing, because the tracker must agree
with what Archipelago actually did at generation time:

  * AND and OR have EQUAL precedence (both 2) and are left-associative.
    So `a OR b AND c` means `(a OR b) AND c`, NOT `a OR (b AND c)`.
  * AND/OR are matched case-insensitively (`Or` is valid).
  * An unclosed `(` is silently tolerated: the leftover paren is flushed onto
    the postfix output and ignored by the evaluator, which is equivalent to
    closing it at the end of the expression.
  * A stray `)` with no matching `(` is a hard error in Manual, so it is here.

Instead of evaluating, we run the same shunting-yard over operand *tokens*
and rebuild an expression tree from the resulting postfix.
"""
import re

TOKEN_RE = re.compile(r"""
      (?P<ws>\s+)
    | (?P<yaml>\{\s*(?P<fname>\w+)\s*\((?P<ybody>[^)]*)\)\s*\})
    | (?P<item>\|(?P<ibody>[^|]+)\|)
    | (?P<lpar>\()
    | (?P<rpar>\))
    | (?P<and>AND)
    | (?P<or>OR)
""", re.X | re.I)


class ParseError(Exception):
    pass


YAML_RE = re.compile(r'^\s*(\w+)\s*(==|!=|>=|<=|>|<)\s*(\S+)\s*$')


def tokenize(s):
    toks, i = [], 0
    while i < len(s):
        m = TOKEN_RE.match(s, i)
        if not m:
            raise ParseError("unexpected char %r at %d in %r" % (s[i], i, s))
        i = m.end()
        kind = m.lastgroup if m.lastgroup in (
            'ws', 'lpar', 'rpar', 'and', 'or') else None
        if m.group('ws'):
            continue
        if m.group('yaml'):
            fname = m.group('fname')
            if fname != 'YamlCompare':
                raise ParseError("unsupported function %r in %r" % (fname, s))
            mm = YAML_RE.match(m.group('ybody'))
            if not mm:
                raise ParseError("bad YamlCompare body %r" % m.group('ybody'))
            toks.append(('operand', ('yaml', mm.group(1), mm.group(2), mm.group(3))))
        elif m.group('item'):
            body = m.group('ibody').strip()
            if body.startswith('@'):
                raise ParseError("category requires are not supported: %r" % body)
            if ':' in body:
                name, cnt = body.rsplit(':', 1)
                toks.append(('operand', ('item', name.strip(), int(cnt.strip()))))
            else:
                toks.append(('operand', ('item', body, 1)))
        elif m.group('lpar'):
            toks.append(('lpar', None))
        elif m.group('rpar'):
            toks.append(('rpar', None))
        elif m.group('and'):
            toks.append(('op', 'and'))
        elif m.group('or'):
            toks.append(('op', 'or'))
    return toks


def to_postfix(toks, src):
    """Shunting-yard mirroring Manual's infix_to_postfix (equal precedence)."""
    out, stack = [], []
    for kind, val in toks:
        if kind == 'operand':
            out.append(('operand', val))
        elif kind == 'op':
            # prec is equal for & and |, so this pops on every operator
            while stack and stack[-1] != 'lpar':
                out.append(('op', stack.pop()))
            stack.append(val)
        elif kind == 'lpar':
            stack.append('lpar')
        elif kind == 'rpar':
            while stack and stack[-1] != 'lpar':
                out.append(('op', stack.pop()))
            if not stack:
                raise ParseError("unmatched ')' in %r" % src)
            stack.pop()
    while stack:
        top = stack.pop()
        if top == 'lpar':
            continue  # Manual emits it and the evaluator ignores it
        out.append(('op', top))
    return out


def postfix_to_tree(postfix, src):
    stack = []
    for kind, val in postfix:
        if kind == 'operand':
            stack.append(val)
        else:
            if len(stack) < 2:
                raise ParseError("operator %r starved of operands in %r" % (val, src))
            b = stack.pop()
            a = stack.pop()
            stack.append((val, a, b))
    if len(stack) != 1:
        raise ParseError("expression left %d values on the stack in %r"
                         % (len(stack), src))
    return stack[0]


def parse(s):
    """Return an expression tree, or None for an empty/absent requirement."""
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    toks = tokenize(s)
    if not toks:
        return None
    return postfix_to_tree(to_postfix(toks, s), s)
