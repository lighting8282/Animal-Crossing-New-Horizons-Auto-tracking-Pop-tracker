# Animal Crossing: New Horizons — Archipelago PopTracker Pack

A PopTracker pack for the `Manual_AnimalCrossingNewHorizons` Archipelago
apworld, with **working auto-tracking** and **logic generated from the apworld**.

Requires PopTracker **0.35.4** or newer.

## Credits

This is a derivative work. Please credit the originals:

- **CourtneyEvie** — the `Manual_AnimalCrossingNewHorizons` apworld
  ([releases](https://github.com/CourtneyEvie/ACNH-APWorld-Manual/releases)) and the original *ACNH Archipelago Poptracker* pack
  (v1.0.0) this is built from. `manifest.json` still names them as author.
- **Stripes007** — MIT licence holder of the pack template (see `LICENSE`).

Licensed MIT, as the original is.

## What this adds

The upstream pack shipped complete auto-tracking code and **no logic at all** —
every `access_rules` entry was `[" "]` and all `scripts/logic/*.lua` files were
empty, so the entire map read as in-logic from an empty inventory.

It also never auto-tracked, because `location_mapping.lua` had a Lua syntax
error that aborted `init.lua` before the AP handlers were registered.

Changes here:

- **Logic for all 417 locations**, generated from the apworld and
  differentially tested against Manual's own evaluator
- **The 5-region chain** actually gating (39 checks open on a fresh slot, not 417)
- **Visibility** driven by the server's location list, so locations your YAML
  removed are hidden instead of drawn as unreachable
- **Auto-tracking fixed** — one stray comma was disabling it entirely
- **Progressive item stages fixed** — received copies now map to the correct stage
- **A "Hints, Tips and Tricks" tab** with advice for playing this as a Manual

See [`gen/README.md`](gen/README.md) for the technical detail, including the
PopTracker and Manual API behaviours that are easy to get wrong.

## Installing

Copy or clone this folder into PopTracker's `packs/` directory:

```
poptracker/packs/acnh_ap_tracker/
```

PopTracker loads unzipped folders. Pick the **Map Tracker** variant, then
connect with the Archipelago button using your room's host, slot name and
password.

You will also need CourtneyEvie's apworld in Archipelago's `custom_worlds/`:
**[ACNH-APWorld-Manual releases](https://github.com/CourtneyEvie/ACNH-APWorld-Manual/releases)**

## Tests

Needs `lupa` (and `jsonschema` for layout validation).

```bash
python gen/test_lua_syntax.py        # every .lua file parses
python gen/test_progressive_items.py # received copies -> correct stage
python gen/test_parity.py            # parsed rules vs Manual's evaluator
python gen/test_lua_parity.py        # the real rules.lua vs Manual's evaluator
python gen/test_visibility.py        # Vis() hides exactly what the slot lacks
python gen/test_progression.py       # sanity: does the map gate and open
```

The parity tests copy Manual's `infix_to_postfix` and `evaluate_postfix`
verbatim from the apworld's `Rules.py` and compare verdicts over random
inventories and option sets. All should report 0 mismatches / failures.

They need an extracted copy of the apworld in `gen/_apworld/`, which is not
redistributed here — grab it from the
[releases](https://github.com/CourtneyEvie/ACNH-APWorld-Manual/releases) above.
