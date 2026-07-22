# Handoff: curate Sophia's reference library (luvia 0018 provisioning)

You are building the **fixed reference library** for the luvia `luvia_selfie` tool. Your job:
crop a small, hand-curated set of single-subject images from grid/composite source files,
write a schema-valid `manifest.json`, and validate it against the real resolver. This is
provisioning work only — do not touch plugin code, tests, or the skill.

## Background you must respect

- The reference library is **fixed, small, hand-curated** (ADR `docs/adr/0002-bfl-direct-fixed-reference-library.md`).
  It is NOT auto-grown. Do not turn every grid cell into a reference — more near-identical
  faces only add identity-drift risk. The target is exactly the 5 references listed below.
- `luvia_selfie` **edits a single reference image** with a scene prompt. Therefore:
  - Every reference file must contain **exactly one subject**, cleanly framed. Never a
    2-figure composite, never a second person bleeding in from an adjacent panel, never a
    visible gutter line.
  - References exist for **identity + framing**, not expression/mood — the scene prompt sets
    mood at generation time. Roles are framing/setting, never "smiling" vs "serious".
- The library lives **only on the box** at `$LUVIA_SOPHIA_ASSETS`, is **gitignored, and must
  never be committed to the repo**. Stage your output in the scratchpad; a human moves it to
  the box.

## Source material

Grids live in `assets/sophie/*.jpg` (all 1024x1024). Identity is consistent across all of
them (brown hair, nose freckles, hoop earrings). Formats vary — inspect before cropping:

- **Clean 2x2 face grids** (`create-portrait-of-her-to-pro-*.jpg`, 5 files): four head-angle
  cells split by a gutter at x=512, y=512. You need only ONE front-facing cell total.
- **Panel composites** (`create-portrait-and-pro-*.jpg (1)` and `(2)`): layout is one tall
  left panel + two stacked right panels, split at x~=512 and (right column) y~=512.
- **Open 2-figure scene** (`create-portrait-and-pro-205405625.jpg`, no suffix): two figures
  share one frame with no gutter — **skip it**, you cannot cleanly isolate one subject.
- **Messy collage** (`more-variation-on-this-pro-205405625.jpg`): ~6 overlapping cells with
  varied outfits. Only the work-look figure is wanted; crop it by hand-picked bbox.

## Deliverable: exactly 5 references

Stage all output in:
`/private/tmp/claude-501/-Users-taiseiigresb-Documents--projects-luvia/56676146-d3f7-43ac-a5cd-e60e87dd38f1/scratchpad/refs/`  (a prior pass already put canonical_face.png/half_body.png/full_body.png +
manifest.json there — you will REBUILD this directory to match the spec below; keep only what
matches).

| # | role | default | framing | source file | crop |
|---|------|---------|---------|-------------|------|
| 1 | `canonical_face` | **true** | close front portrait, head+shoulders | `create-portrait-of-her-to-pro-205405625 (2).jpg` | top-left cell, gutter-split ~(6,6)-(506,506); pick the clean FRONT cell (upgrade over the current ¾ canonical) |
| 2 | `half_body` | false | standing three-quarter, sweater+jeans | `create-portrait-and-pro-205405625 (1).jpg` | top-right panel (1024x1024 asset): detect gutters, ~(514,6)-(1018,508) |
| 3 | `full_body_seated` | false | seated cross-legged, sweater+jeans+sneakers | `create-portrait-and-pro-205405625 (1).jpg` | bottom-right panel (1024x1024 asset): detect gutters, ~(514,516)-(1018,1018) |
| 4 | `full_body_standing` | false | standing full body, oversized sweater | `create-portrait-and-pro-205405625 (2).jpg` | left tall panel, single figure ~(6,6)-(510,1018) |
| 5 | `work_look` | false | standing, grey trousers + top (dressed/founder) | `more-variation-on-this-pro-205405625.jpg` | bottom-left figure; VIEW first, hand-pick a bbox that captures one clean figure with no overlap from the center cell (~(8,360)-(330,1018) as a starting guess — refine visually) |

Crop mechanics:
- 2x2 / paneled grids: detect the gutter (brightest near-uniform row/column in the middle
  third) and inset a few pixels so no gutter line survives.
- Composite/collage figures: open the image, choose the cleanest single-subject region by
  eye, crop, then re-open the crop and confirm it contains one subject, face clear, no
  neighbor bleed. Redo if not.
- Save as PNG. Filenames: `<role>.png`.

## manifest.json schema (validated by plugin/reference_manifest.py)

Top-level **JSON array**; one object per reference. Required fields on every row:
`file, role, framing, setting, description, default`. Optional: `tags` (array of strings).
`file` must be a **relative filename** inside the refs dir (no absolute path, no `../`, no
symlink). Exactly one row has `default: true` — it must be `canonical_face` (the portrait
fallback for any missing/unknown role).

Example row:
```json
{
  "file": "canonical_face.png",
  "role": "canonical_face",
  "framing": "close front portrait, head and shoulders",
  "setting": "neutral grey studio wall, soft daylight",
  "tags": ["face", "freckles", "hoop earrings", "grey tank top", "brown hair"],
  "description": "Clean front portrait — identity anchor for every generated selfie.",
  "default": true
}
```

## Validation (must pass before you report done)

Run from repo root:
```bash
uv run python - <<'PY'
from plugin.reference_manifest import load_reference_manifest, resolve_reference_role
d="/private/tmp/claude-501/-Users-taiseiigresb-Documents--projects-luvia/56676146-d3f7-43ac-a5cd-e60e87dd38f1/scratchpad/refs"
refs=load_reference_manifest(d)
assert len(refs)==5, refs
roles={r.role for r in refs}
assert roles=={"canonical_face","half_body","full_body_seated","full_body_standing","work_look"}, roles
assert sum(r.default for r in refs)==1
assert resolve_reference_role(None,d).role=="canonical_face"
assert resolve_reference_role("work_look",d).role=="work_look"
assert resolve_reference_role("nonexistent",d).role=="canonical_face"  # portrait fallback
print("OK", sorted(roles))
PY
```

## Definition of done

- [ ] `/private/tmp/claude-501/-Users-taiseiigresb-Documents--projects-luvia/56676146-d3f7-43ac-a5cd-e60e87dd38f1/scratchpad/refs/` contains exactly 5 PNGs + `manifest.json`, nothing else.
- [ ] Each PNG is one subject, face clear, no gutter/neighbor bleed, all clothed (non-nude — hard rule).
- [ ] Validation script above prints `OK` with the 5 expected roles.
- [ ] Nothing added to git; `assets/sophie/` source grids left untouched.
- [ ] Report the final file list and the validation output. Do NOT move files to the box —
      a human does that and sets `$LUVIA_SOPHIA_ASSETS`.
