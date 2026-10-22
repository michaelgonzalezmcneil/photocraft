# Loomwell PhotoCraft workflow pack

Original Loomwell templates, reusable swatches and image preparation actions for the source-built PhotoCraft engine. This add-on does not modify or rebrand the application. It contains no customer images or measured performance claims.

## Export

From the PhotoCraft checkout:

```sh
python3 loomwell/export.py list
python3 loomwell/export.py export all --output ~/Desktop/loomwell-design
python3 loomwell/export.py export social --output ~/Desktop/loomwell-design --content loomwell/content.example.json
```

The script uses Python 3's standard library. It finds the maintained local build, `PHOTOCRAFT_CLI`, or `photocraft-cli` on `PATH`. A standalone checkout can use an explicit executable, with no Atlas dependency:

```sh
python3 loomwell/export.py export all --output ./delivery --cli /absolute/path/to/photocraft-cli
```

Each delivery has editable `.pcraft` files, PNG, lossless WebP, repeatable `.recipe.json` command lists, an importable `loomwell.aco` palette and `manifest.json` with dimensions, byte sizes and SHA-256 digests. PNG and WebP flatten the composition; WebP does not carry print DPI metadata. `.pcraft` preserves type, vector shapes and embedded smart objects.

| Template | Size | Replacement image area, x / y / width / height |
|---|---|---|
| `website` | 1600 × 900 | 950 / 190 / 560 / 560 |
| `social` | 1200 × 630 | 850 / 136 / 286 / 286 |
| `square` | 1080 × 1080 | 280 / 500 / 520 / 410 |

Open the saved files in PhotoCraft to adjust the named `Brand`, `Copy`, `Artwork` and `Footer` layers. These are native type and shape layers, not a flattened placeholder. Inter is bundled with the engine, so the templates do not rely on fonts installed on the host. Font substitution warnings fail the export instead of quietly changing the layout. The PNG previews in `templates/` show the default composition.

After editing a native document, export that saved document directly so your changes are retained:

```sh
photocraft-cli convert ./my-edited-social.pcraft ./my-edited-social.png
photocraft-cli convert ./my-edited-social.pcraft ./my-edited-social.webp
```

The `export.py export` command regenerates a new composition from the pack's recipe and copy. Direct `convert` commands render the exact native document you edited. Keep the `.pcraft` file as the editable master.

## Copy and images

Pass a JSON file using `eyebrow`, `headline`, `subheadline` and `footer` to share copy with the other Loomwell workflow packs. `button` is optional and applies to the website template. Omitted fields use `content.json`. Headline and subheadline strings wrap to at most two lines; explicit arrays of one or two lines also work. Long or out-of-bounds copy is rejected before existing delivery files are replaced. Shorter copy is easier to reuse across all three sizes.

Place an image into the reserved area without stretching it:

```sh
python3 loomwell/export.py export all --output ./delivery --input /absolute/path/to/approved-image.png
```

The original is read and embedded as a smart object. The image fits inside the safe area with its aspect ratio intact; unused space takes the paper background. The source image is never overwritten. Defaults contain only the original woven illustration built from native geometry.

## Palette and image preparation

The four reusable colors are forest `#182822`, paper `#f5f2e9`, sage `#d5e5b3` and terracotta `#b86e4d`. Import `templates/loomwell.aco` with PhotoCraft's Swatches import command, or use the copy written to each delivery. It contains named swatches in the Loomwell group.

The `presets/` JSON action lists can be loaded in PhotoCraft or used for a batch of approved images:

```sh
photocraft-cli batch --actions loomwell/presets/website-width-1600.actions.json --in ./originals --out ./website-images --format webp
photocraft-cli batch --actions loomwell/presets/social-width-1200.actions.json --in ./originals --out ./social-images --format webp
photocraft-cli batch --actions loomwell/presets/square-width-1080.actions.json --in ./originals --out ./square-images --format webp
photocraft-cli batch --actions loomwell/presets/half-resolution.actions.json --in ./originals --out ./previews --format png
```

These width and preview presets preserve each input's aspect ratio and write to a separate folder. A width preset alone does not crop images into a square. Use the square template with `--input` for an exact 1080 × 1080 brand composition. Do not add `--in-place` when preparing originals.

## Verify

```sh
PHOTOCRAFT_CLI=/absolute/path/to/photocraft-cli python3 -m unittest discover -s loomwell -p 'test_*.py' -v
```

The smoke tests render all three sizes through PhotoCraft, reopen native files, compare rendered pixels after a native roundtrip, reimport the palette and check image preservation and content overflow. No GUI or Python packages are needed.

Original pack code and artwork use the repository's MIT OR Apache-2.0 license. Existing engine and font notices remain in `NOTICE` and `ATTRIBUTION.md`. No font files or third-party images were added. This pack does not grant rights to upstream trademarks.
