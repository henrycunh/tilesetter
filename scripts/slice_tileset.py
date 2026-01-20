#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class SliceSpec:
    tile_w: int
    tile_h: int
    margin_x: int
    margin_y: int
    spacing_x: int
    spacing_y: int


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Slice a tileset image into tile PNGs.")
    p.add_argument("image", type=Path, help="Input tileset PNG path")
    p.add_argument("--tile-w", type=int, default=16, help="Tile width in pixels")
    p.add_argument("--tile-h", type=int, default=16, help="Tile height in pixels")
    p.add_argument("--margin-x", type=int, default=0, help="Left margin in pixels")
    p.add_argument("--margin-y", type=int, default=0, help="Top margin in pixels")
    p.add_argument("--spacing-x", type=int, default=0, help="Horizontal spacing between tiles")
    p.add_argument("--spacing-y", type=int, default=0, help="Vertical spacing between tiles")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: sliced_tilesets/<name>_<tilew>x<tileh>/)",
    )
    p.add_argument(
        "--trim-empty",
        action="store_true",
        help="Skip tiles that are fully transparent/white (depending on options)",
    )
    p.add_argument(
        "--transparent-white",
        action="store_true",
        help="Convert pure white pixels (#ffffff) to alpha=0 before saving",
    )
    p.add_argument(
        "--manifest",
        action="store_true",
        help="Write manifest.json with tile rects and filenames",
    )
    return p.parse_args()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _white_to_transparent(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a != 0 and r == 255 and g == 255 and b == 255:
                px[x, y] = (255, 255, 255, 0)
    return rgba


def _is_empty(img: Image.Image, *, empty_is_transparent: bool) -> bool:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.getchannel("A")
    if empty_is_transparent:
        return alpha.getbbox() is None
    # If not treating white as transparent, "empty" means all pixels are white.
    rgb = img.convert("RGB")
    extrema = rgb.getextrema()  # ((rmin,rmax),(gmin,gmax),(bmin,bmax))
    return all(ch == (255, 255) for ch in extrema)


def slice_tileset(
    *,
    image_path: Path,
    out_dir: Path,
    spec: SliceSpec,
    trim_empty: bool,
    transparent_white: bool,
    write_manifest: bool,
) -> None:
    tileset = Image.open(image_path)
    w, h = tileset.size

    start_x = spec.margin_x
    start_y = spec.margin_y
    step_x = spec.tile_w + spec.spacing_x
    step_y = spec.tile_h + spec.spacing_y

    cols = (w - start_x + spec.spacing_x) // step_x
    rows = (h - start_y + spec.spacing_y) // step_y

    _ensure_dir(out_dir)

    manifest: dict[str, object] = {
        "source": os.fspath(image_path),
        "tileset_size": [w, h],
        "tile_size": [spec.tile_w, spec.tile_h],
        "margin": [spec.margin_x, spec.margin_y],
        "spacing": [spec.spacing_x, spec.spacing_y],
        "grid": [cols, rows],
        "tiles": [],
    }

    for ty in range(rows):
        for tx in range(cols):
            x0 = start_x + tx * step_x
            y0 = start_y + ty * step_y
            box = (x0, y0, x0 + spec.tile_w, y0 + spec.tile_h)
            tile = tileset.crop(box)
            if transparent_white:
                tile = _white_to_transparent(tile)

            if trim_empty and _is_empty(tile, empty_is_transparent=transparent_white):
                continue

            idx = ty * cols + tx
            filename = f"tile_{idx:03d}_x{tx:02d}_y{ty:02d}.png"
            out_path = out_dir / filename
            tile.save(out_path)

            if write_manifest:
                manifest["tiles"].append(
                    {
                        "index": idx,
                        "x": tx,
                        "y": ty,
                        "rect": [x0, y0, spec.tile_w, spec.tile_h],
                        "file": filename,
                    }
                )

    if write_manifest:
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    args = _parse_args()
    spec = SliceSpec(
        tile_w=args.tile_w,
        tile_h=args.tile_h,
        margin_x=args.margin_x,
        margin_y=args.margin_y,
        spacing_x=args.spacing_x,
        spacing_y=args.spacing_y,
    )
    out_dir: Path
    if args.out is None:
        out_dir = Path("sliced_tilesets") / f"{args.image.stem}_{spec.tile_w}x{spec.tile_h}"
    else:
        out_dir = args.out

    slice_tileset(
        image_path=args.image,
        out_dir=out_dir,
        spec=spec,
        trim_empty=args.trim_empty,
        transparent_white=args.transparent_white,
        write_manifest=args.manifest,
    )


if __name__ == "__main__":
    main()

