# Animal Crossing: New Horizons — Archipelago PopTracker Pack

A PopTracker pack for the `Manual_AnimalCrossingNewHorizons` Archipelago
apworld, with **working auto-tracking** and **logic generated from the apworld**.

Requires PopTracker **0.35.4** or newer.

## Credits

This is a derivative work. Please credit the originals:

- **CourtneyEvie** — the `Manual_AnimalCrossingNewHorizons` apworld and the
  original *ACNH Archipelago Poptracker* pack (v1.0.0) this is built from.
  `manifest.json` still names them as author.
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

## Regenerating the logic

The logic is generated, not hand-written. `gen/_apworld/` is **not committed** —
it is CourtneyEvie's apworld and is not redistributed here. To regenerate:

1. Extract `manual_animalcrossingnewhorizons.apworld` into `gen/_apworld/`
2. Run:

```bash
python gen/build_logic.py
```

This rewrites `scripts/logic/rules_data.lua` and the `access_rules` /
`visibility_rules` in `locations/*.json`. Everything else is hand-written and
left alone.

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
inventories and option sets. All should report 0 mismatches / failures. They
require `gen/_apworld/` to be present.

## Known issues in the apworld

Found while building this, worth reporting upstream:

- 20 locations have **unbalanced parentheses** in `requires` (e.g. `Donate Pike`).
  Manual tolerates it, so they work, but they're latent bugs.
- `Craft Spooky Carriage` uses lowercase `Or` — also tolerated.
- `Craft Hearth` and `Craft Bamboo Noodle Slide` carry a `|Daisy Mae|` term that
  looks unintended; it loosens their logic.
- Several items are flagged `progression: True` but gate nothing:
  `Tool Ring`, `Progressive Inventory Space`, `Bell Voucher`.
