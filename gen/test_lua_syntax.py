"""Syntax-check every Lua file in the pack.

The pack shipped with a stray double comma in location_mapping.lua, which
aborted init.lua on load. PopTracker reports that as one line buried in its
log and otherwise carries on looking normal - the map renders, the websocket
connects, and nothing auto-tracks. Cheap to guard against, so we do.
"""
import os
import sys

import lupa

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)


def main():
    lua = lupa.LuaRuntime()
    loadstring = lua.globals().load or lua.globals().loadstring
    failures = 0
    checked = 0
    warnings = []
    for root, dirs, files in os.walk(os.path.join(PACK, 'scripts')):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in sorted(files):
            if not name.endswith('.lua'):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, PACK).replace('\\', '/')
            with open(path, encoding='utf-8') as f:
                src = f.read()
            checked += 1
            if not src.strip():
                continue          # empty stubs are fine
            chunk, err = None, None
            res = loadstring(src, '@' + rel)
            if isinstance(res, tuple):
                chunk, err = res
            else:
                chunk = res
            if chunk is None:
                msg = str(err)
                if 'const variable' in msg:
                    # lupa embeds a newer Lua than PopTracker. Lua 5.5 made
                    # for-loop control variables const; 5.3/5.4 (what
                    # PopTracker runs) allow assigning to them. archipelago.lua
                    # does this in DumpTable and PopTracker loads it fine, so
                    # this is a version artefact, not a pack bug.
                    warnings.append((rel, msg))
                    continue
                failures += 1
                print('SYNTAX ERROR %s: %s' % (rel, msg))
    for rel, msg in warnings:
        print('note (newer-Lua only, harmless in PopTracker) %s: %s' % (rel, msg))
    print('checked %d lua files, %d failed, %d notes'
          % (checked, failures, len(warnings)))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
