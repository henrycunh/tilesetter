# tilesetter

Utilities for working with tileset images.

## Repo layout

- `raw_tilesets/`: source tileset images (PNG)
- `sliced_tilesets/`: raw uniform slices + `manifest.json`
- `configs/`: human-edited grouping/naming configs
- `organized_tilesets/`: grouped + named outputs + `tileset.json` metadata
- `scripts/`: CLI utilities

## Process used for `tileset_1bit.png`

1) Inspect the source image to determine tile size and grid alignment.
   - `raw_tilesets/tileset_1bit.png` is `128x128`, and its content aligns cleanly on a `16x16` grid (8x8 tiles).

2) Slice on that grid and write a slice manifest:

```bash
python3 scripts/slice_tileset.py raw_tilesets/tileset_1bit.png --tile-w 16 --tile-h 16 --manifest
```

This produces:
- `sliced_tilesets/tileset_1bit_16x16/tile_*.png`
- `sliced_tilesets/tileset_1bit_16x16/manifest.json` (rect + filename per tile)

2.5) Generate a labeled overview (recommended before organizing):

```bash
python3 scripts/overview_tileset.py --sliced-dir sliced_tilesets/tileset_1bit_16x16 --out docs/tileset_1bit_16x16_overview.png --scale 8
```

3) Create a grouping/naming config (manual step).
   - `configs/tileset_1bit_16x16.json` defines:
     - directories (each directory = one object/set, like `objects/archway`)
     - a `base_name` used for filenames
     - per-tile local `pos: [x,y]` so files are numbered as `<base_name>_XX_YY.png`
     - how tiles “connect” within the directory

4) Generate an organized folder tree and connection metadata:

```bash
python3 scripts/organize_tileset.py --config configs/tileset_1bit_16x16.json --overwrite
```

This produces:
- grouped/named PNGs under `organized_tilesets/tileset_1bit_16x16/<directory>/...`
- `organized_tilesets/tileset_1bit_16x16/tileset.json`
- `assembled.png` previews for `connect.type = "layout"` directories

## How an agent should do this for a new tileset

### 1) Add the source image

- Put the PNG in `raw_tilesets/` (e.g. `raw_tilesets/my_tileset.png`).

### 2) Determine the slice grid

Decide:
- `tile_w`, `tile_h` (common: 8/16/32)
- optional `margin` and `spacing` (if the sheet has padding between tiles)

Practical checks:
- Confirm `image_width % tile_w == 0` and `image_height % tile_h == 0` when it’s a uniform grid.
- If unsure, overlay a grid in any image editor and try 8/16/32 until edges line up.

### 3) Slice + write `manifest.json`

```bash
python3 scripts/slice_tileset.py raw_tilesets/my_tileset.png --tile-w 16 --tile-h 16 --manifest
```

If the tileset uses white as “transparent background”, consider:
- `--transparent-white` (turns pure white into alpha=0)
- `--trim-empty` (skips fully empty tiles)

### 4) Inspect slices and decide semantic directories

Goal: produce stable, human-meaningful names and group IDs.

Guidelines:
- Group IDs become folders; use `/` to create hierarchy (example: `terrain/grass`).
- Tile names become filenames; use stable `snake_case` names.
- Prefer “what it is” over “where it was on the sheet”.

Recommended: generate a contact sheet to guide naming and grouping:

```bash
python3 scripts/overview_tileset.py --sliced-dir sliced_tilesets/<tileset_stem>_16x16 --out docs/<tileset_id>_overview.png --scale 8
```

### 5) Write a config in `configs/`

Create `configs/<tileset_id>.json` modeled after `configs/tileset_1bit_16x16.json`.

Each group can optionally declare a connection strategy:

- `connect.type = "layout"`: for multi-tile pieces that are meant to be arranged in a fixed shape.
  - Provide `pos: [x, y]` for each tile in that piece.
  - The organizer emits `assembled.png` and stores the layout in `tileset.json`.

- `connect.type = "edge_match"`: for tiles intended to tile seamlessly.
  - The organizer computes edge similarity (Hamming distance on the boundary pixels) and writes top neighbor suggestions per direction in `tileset.json`.
  - This is a heuristic: the agent should review results and tweak grouping/naming when needed.

### 6) Generate organized output and iterate

```bash
python3 scripts/organize_tileset.py --config configs/<tileset_id>.json --overwrite
```

Iteration loop:
- Open `organized_tilesets/<tileset_id>/tileset.json` and spot-check `edge_matches`.
- Open each `assembled.png` and confirm the piece forms correctly.
- Fix mistakes by editing `configs/<tileset_id>.json` and re-running the organizer.
