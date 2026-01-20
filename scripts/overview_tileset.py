#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class ManifestTile:
    index: int
    x: int
    y: int
    file: str


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate a labeled overview/contact sheet from sliced tiles.")
    p.add_argument(
        "--sliced-dir",
        type=Path,
        required=True,
        help="Directory containing tile PNGs and manifest.json",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest path (default: <sliced-dir>/manifest.json)",
    )
    p.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output PNG path",
    )
    p.add_argument("--scale", type=int, default=8, help="Nearest-neighbor scale for each tile")
    p.add_argument("--pad", type=int, default=6, help="Padding between tiles (scaled pixels)")
    p.add_argument("--label", choices=["none", "index", "xy", "index+xy"], default="index+xy")
    p.add_argument("--font-size", type=int, default=14, help="Label font size")
    return p.parse_args()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _load_font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_height(font: ImageFont.ImageFont) -> int:
    # Conservative: default bitmap font has no metrics API, so use bbox when available.
    try:
        bbox = font.getbbox("Ag")
        return bbox[3] - bbox[1]
    except Exception:
        return font.size if hasattr(font, "size") else 14


def _parse_manifest(manifest: dict[str, Any]) -> tuple[list[ManifestTile], tuple[int, int], tuple[int, int]]:
    tile_w, tile_h = int(manifest["tile_size"][0]), int(manifest["tile_size"][1])
    cols, rows = int(manifest["grid"][0]), int(manifest["grid"][1])
    tiles: list[ManifestTile] = []
    for t in manifest["tiles"]:
        tiles.append(
            ManifestTile(
                index=int(t["index"]),
                x=int(t["x"]),
                y=int(t["y"]),
                file=str(t["file"]),
            )
        )
    # Ensure stable order.
    tiles.sort(key=lambda t: (t.y, t.x, t.index))
    return tiles, (tile_w, tile_h), (cols, rows)


def make_overview(
    *,
    sliced_dir: Path,
    manifest_path: Path,
    out_path: Path,
    scale: int,
    pad: int,
    label: str,
    font_size: int,
) -> None:
    manifest = _read_json(manifest_path)
    tiles, (tile_w, tile_h), (cols, rows) = _parse_manifest(manifest)

    font = _load_font(font_size)
    label_h = 0 if label == "none" else _text_height(font) + 4

    cell_w = tile_w * scale
    cell_h = tile_h * scale
    out_w = cols * (cell_w + pad) + pad
    out_h = rows * (cell_h + label_h + pad) + pad

    canvas = Image.new("RGB", (out_w, out_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    by_xy = {(t.x, t.y): t for t in tiles}
    for y in range(rows):
        for x in range(cols):
            t = by_xy.get((x, y))
            if t is None:
                continue
            img = Image.open(sliced_dir / t.file).convert("RGB").resize((cell_w, cell_h), Image.NEAREST)

            px = pad + x * (cell_w + pad)
            py = pad + y * (cell_h + label_h + pad)
            canvas.paste(img, (px, py))

            # Border.
            draw.rectangle([px, py, px + cell_w - 1, py + cell_h - 1], outline=(255, 0, 0), width=2)

            if label != "none":
                if label == "index":
                    text = f"{t.index:03d}"
                elif label == "xy":
                    text = f"({t.x},{t.y})"
                else:
                    text = f"{t.index:03d} ({t.x},{t.y})"
                draw.text((px, py + cell_h + 2), text, fill=(0, 0, 0), font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)


def main() -> None:
    args = _parse_args()
    manifest_path = args.manifest or (args.sliced_dir / "manifest.json")
    make_overview(
        sliced_dir=args.sliced_dir,
        manifest_path=manifest_path,
        out_path=args.out,
        scale=int(args.scale),
        pad=int(args.pad),
        label=str(args.label),
        font_size=int(args.font_size),
    )


if __name__ == "__main__":
    main()

