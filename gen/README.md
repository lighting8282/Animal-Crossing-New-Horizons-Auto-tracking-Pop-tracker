# Logic generation

The pack's access rules are **generated from the apworld**, not hand-written.
`gen/_apworld/` is a copy of `manual_animalcrossingnewhorizons.apworld`, which
is the single source of truth for logic.

## Regenerating

```bash
python gen/build_logic.py
```

Writes:

| Output | Contents |
|---|---|
| `scripts/logic/rules_data.lua` | rule trees for all 417 locations + the 5-region graph |
| `locations/*.json` | `access_rules` rewritten to `$Rule|<ap_location_id>` |

`scripts/logic/rules.lua` is hand-written and is **not** regenerated — it's the
runtime that walks the generated trees.

To pick up a new apworld release, replace `gen/_apworld/` with the new
extracted apworld and re-run. The build fails loudly if the apworld and the
pack have drifted (unmapped item, missing progressive stage, location count
mismatch, unmatched section path).

## Why a parser and not hand-written rules

PopTracker's native `access_rules` syntax is two levels deep: the array is an
OR, each string is a comma-separated AND. ACNH's requires nest three deep and
branch on YAML options, so they don't fit. Instead every section delegates to
`$Rule|<id>` and the tree is evaluated in Lua.

## Matching Manual's semantics exactly

`parse_requires.py` is a **structural port** of Manual's own evaluator rather
than a "correct" boolean parser, because the tracker has to agree with what
Archipelago actually did at generation time. Quirks reproduced deliberately:

- **`AND` and `OR` have equal precedence** and are left-associative, so
  `a OR b AND c` means `(a OR b) AND c`. This is not the usual precedence, so
  a conventional parser would quietly disagree with Archipelago.
- `AND`/`OR` match case-insensitively, so `Or` and `and` are valid.
- An unclosed `(` is tolerated and behaves as if closed at end of expression.
- A stray `)` is a hard error in Manual, so it is here too.

## Tests

```bash
python gen/test_lua_syntax.py       # every .lua file parses
python gen/test_progressive_items.py # received copies -> correct stage
python gen/test_parity.py        # parsed tree vs Manual's evaluator
python gen/test_lua_parity.py    # the real rules.lua vs Manual's evaluator
python gen/test_visibility.py    # Vis() hides exactly what the slot lacks
python gen/test_progression.py   # sanity: does the map actually gate and open
```

`test_parity` and `test_lua_parity` copy Manual's `infix_to_postfix` and
`evaluate_postfix` verbatim from the apworld's `Rules.py` and compare verdicts
over random inventories and option sets. `test_lua_parity` loads the actual
`rules.lua` through `lupa` with stubbed PopTracker globals, so it covers the
generated data, the Lua tree walk, the region chain and item/stage code
resolution together.

Both should report `mismatches: 0`.

## Fixes to the original pack

`scripts/autotracking/location_mapping.lua` line 410 (entry `[397]`) had a
stray double comma. That is a Lua syntax error, so `init.lua` aborted on load
and `watches.lua` never ran — meaning no AP handlers were ever registered and
the pack never auto-tracked at all, despite shipping complete autotracking
code. PopTracker reports this as a single line in its log and otherwise looks
healthy: the map renders and the websocket connects. `test_lua_syntax.py`
guards against a recurrence.

`items/items.json` referenced a nonexistent `images/items/update.png` for the
internal `update` toggle; repointed at `placeholderitem.png`.

`ItemUpdate` in `scripts/autotracking/archipelago.lua` mishandled progressive
items. It now counts received copies (`PROGRESSIVE_COUNTS`, reset in
`OnClear`) and writes the stage **absolutely** from that count:

```lua
item_obj.Active = true          -- a stage write is discarded while inactive
item_obj.CurrentStage = count   -- CurrentStage is 1-based; 0 means disabled
```

For an `allow_disabled` progressive, `CurrentStage` is 1-based with 0 meaning
disabled, so N received copies == `CurrentStage` N. That is NOT the `stages`
array index, and the saved JSON stores `[active, CurrentStage - 1]`. Confirmed
by readback logging against the real app, not inferred.

Three separate bugs came from this one property:
1. Blind `CurrentStage + 1` with `Active` never set - read one too high.
2. Writing `count - 1`, and writing the stage before activating - the write
   was discarded, capping everything at stage 1.
3. Relative increments - PopTracker restores the autosave around the time the
   clear handler runs, so increments stacked on last session's restored stage
   (4 saved + 3 replayed = 7).

The result must depend ONLY on the replayed copy count, never on what the item
already holds. `test_progressive_items.py` covers all three, including a
stale-restored-state case that reproduces the 7.

Set `TRACE_AP = true` at the top of `archipelago.lua` to log the AP handler
call sequence and post-write readback to PopTracker's log - that is what
settled the semantics.

## Visibility

A slot's real location set is cut three ways:

1. `hooks/World.py` `after_create_regions` removes locations by `fishsanity`,
   `bugsanity`, `seasanity` and `photosanity`.
2. `data/categories.json` gates a whole category on a yaml option --
   `"Post-Game Checks"` carries `"yaml_option": ["post_game_checks"]`. This is
   **Manual core behaviour, not implemented in the world's hooks**, so
   grepping `hooks/World.py` for `post_game_checks` finds nothing and makes
   the option look dead. It is not: it removes 29 locations.
3. Victory locations become events, not checks.

For Lights_ACNH: 417 - 211 - 29 - 4 = **173**, matching the AP room.
`slot_location_ids()` in `test_visibility.py` models all three.

Each section carries `$Vis|<id>`, which asks the *server* what exists rather
than replicating the removal logic. That's authoritative, covers every option
at once, and needs no maintenance when the apworld's option handling changes.
Before connecting, everything is shown.

`Vis()` reads `Archipelago.MissingLocations` / `.CheckedLocations` **live**,
not the `ALL_LOCATIONS` snapshot that `archipelago.lua` takes in `OnClear`.
The clear handler can run before PopTracker has populated those lists, and an
empty snapshot silently left every removed location visible on the map.
`ALL_LOCATIONS` remains a fallback. PopTracker rebuilds its visibility cache
whenever an item changes (`_visibilityStale` in `tracker.cpp`), so reading
live values is safe and self-correcting.

Note that `post_game_checks` is declared in `options.json` but never read
anywhere in the apworld — it currently does nothing.
