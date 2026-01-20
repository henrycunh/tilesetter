#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

Direction = Literal["N", "E", "S", "W"]


@dataclass(frozen=True)
class TileInfo:
    index: int
    file: str
    sheet_x: int
    sheet_y: int
    rect: tuple[int, int, int, int]  # x, y, w, h


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Organize sliced tiles into named groups + connection metadata.")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("configs/tileset_1bit_16x16.json"),
        help="Config JSON defining directories (objects) and tile positions",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: organized_tilesets/<tileset_id>/)",
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite output directory if it exists")
    return p.parse_args()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _edges_1bit(img: Image.Image) -> dict[Direction, np.ndarray]:
    a = np.array(img.convert("1"), dtype=np.uint8)
    black = (a == 0).astype(np.uint8)
    return {"N": black[0, :], "S": black[-1, :], "W": black[:, 0], "E": black[:, -1]}


def _hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.sum(a != b))


def _opposite(d: Direction) -> Direction:
    return {"N": "S", "S": "N", "E": "W", "W": "E"}[d]  # type: ignore[return-value]


def _copy_tile(src_dir: Path, tile: TileInfo, dst_path: Path) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / tile.file, dst_path)


def _sanitize_base_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "tile"


def _default_base_name_from_group_id(group_id: str) -> str:
    return _sanitize_base_name(group_id.split("/")[-1])


def _tile_filename(base_name: str, x: int, y: int) -> str:
    return f"{base_name}_{x:02d}_{y:02d}.png"


def _assemble_layout(
    *,
    src_dir: Path,
    tile_lookup: dict[int, TileInfo],
    tile_size: tuple[int, int],
    base_name: str,
    entries: list[dict[str, Any]],
    out_path: Path,
) -> dict[str, Any]:
    placed = []
    xs = [int(e["pos"][0]) for e in entries]
    ys = [int(e["pos"][1]) for e in entries]
    min_x, min_y = min(xs), min(ys)
    max_x, max_y = max(xs), max(ys)
    grid_w = max_x - min_x + 1
    grid_h = max_y - min_y + 1

    out_w = grid_w * tile_size[0]
    out_h = grid_h * tile_size[1]
    canvas = Image.new("RGBA", (out_w, out_h), (255, 255, 255, 0))

    for e in entries:
        idx = int(e["index"])
        src_pos = (int(e["pos"][0]), int(e["pos"][1]))
        pos = (src_pos[0] - min_x, src_pos[1] - min_y)
        tile = tile_lookup[idx]
        img = Image.open(src_dir / tile.file).convert("RGBA")
        canvas.paste(img, (pos[0] * tile_size[0], pos[1] * tile_size[1]))
        placed.append(
            {
                "index": idx,
                "pos": [pos[0], pos[1]],
                "source_pos": [src_pos[0], src_pos[1]],
                "file": _tile_filename(base_name, src_pos[0], src_pos[1]),
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return {"grid": [grid_w, grid_h], "placed": placed}


def _edge_match_connections(
    *,
    src_dir: Path,
    tile_lookup: dict[int, TileInfo],
    indexes: list[int],
    top_k: int,
) -> dict[str, Any]:
    imgs = {i: Image.open(src_dir / tile_lookup[i].file) for i in indexes}
    edges = {i: _edges_1bit(imgs[i]) for i in indexes}

    out: dict[str, Any] = {"top_k": top_k, "tiles": {}}
    for i in indexes:
        per_dir: dict[str, Any] = {}
        for d in ("N", "E", "S", "W"):
            dd: Direction = d  # type: ignore[assignment]
            candidates = []
            for j in indexes:
                if i == j:
                    continue
                dist = _hamming(edges[i][dd], edges[j][_opposite(dd)])
                candidates.append({"index": j, "distance": dist})
            candidates.sort(key=lambda c: (c["distance"], c["index"]))
            per_dir[d] = candidates[: top_k]
        out["tiles"][str(i)] = per_dir
    return out


def main() -> None:
    args = _parse_args()
    config = _read_json(args.config)

    tileset_id = str(config["tileset_id"])
    sliced_dir = Path(config["sliced_dir"])
    tile_w, tile_h = int(config["tile_size"][0]), int(config["tile_size"][1])
    out_root = args.out or (Path("organized_tilesets") / tileset_id)

    if out_root.exists() and args.overwrite:
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    manifest = _read_json(sliced_dir / "manifest.json")
    tile_lookup: dict[int, TileInfo] = {}
    for t in manifest["tiles"]:
        idx = int(t["index"])
        rect = t["rect"]
        tile_lookup[idx] = TileInfo(
            index=idx,
            file=str(t["file"]),
            sheet_x=int(t["x"]),
            sheet_y=int(t["y"]),
            rect=(rect[0], rect[1], rect[2], rect[3]),
        )

    used: set[int] = set()
    index: dict[str, Any] = {
        "tileset_id": tileset_id,
        "source": os.fspath(config["source_image"]),
        "tile_size": [tile_w, tile_h],
        "directories": {},
        "tiles": {},
    }

    directories = config.get("directories") or config.get("groups") or []
    for directory in directories:
        directory_id = str(directory["id"])
        base_name = _sanitize_base_name(
            str(directory.get("base_name") or _default_base_name_from_group_id(directory_id))
        )
        connect = directory.get("connect")
        tiles = directory["tiles"]

        directory_entry: dict[str, Any] = {"id": directory_id, "base_name": base_name, "tiles": []}
        if connect is not None:
            directory_entry["connect"] = connect

        directory_dir = out_root / directory_id
        directory_dir.mkdir(parents=True, exist_ok=True)

        # Copy tiles and record mapping.
        if len(tiles) > 1 and any("pos" not in t for t in tiles):
            raise ValueError(
                f"Directory {directory_id} has multiple tiles but some are missing pos=[x,y]; "
                "set pos for every tile so output can be numbered by x/y."
            )
        occupied: set[tuple[int, int]] = set()
        for t in tiles:
            idx = int(t["index"])
            used.add(idx)
            local_pos = t.get("pos")
            tile_info = tile_lookup[idx]
            tile_record: dict[str, Any] = {
                "index": idx,
                "sheet_x": tile_info.sheet_x,
                "sheet_y": tile_info.sheet_y,
            }
            if local_pos is not None:
                tile_record["x"] = int(local_pos[0])
                tile_record["y"] = int(local_pos[1])
            else:
                tile_record["x"] = 0
                tile_record["y"] = 0

            key = (int(tile_record["x"]), int(tile_record["y"]))
            if key in occupied:
                raise ValueError(f"Duplicate local (x,y)={key} in directory {directory_id} (tile index {idx})")
            occupied.add(key)

            filename = _tile_filename(base_name, int(tile_record["x"]), int(tile_record["y"]))
            dst = directory_dir / filename
            _copy_tile(sliced_dir, tile_lookup[idx], dst)
            tile_record["file"] = os.fspath(dst.relative_to(out_root))

            index["tiles"][str(idx)] = {
                "directory": directory_id,
                "file": tile_record["file"],
                "sheet_x": tile_info.sheet_x,
                "sheet_y": tile_info.sheet_y,
                "x": tile_record["x"],
                "y": tile_record["y"],
            }
            directory_entry["tiles"].append(tile_record)

        directory_entry["tiles"].sort(key=lambda t: (int(t["y"]), int(t["x"]), int(t["index"])))

        # Connection metadata.
        if connect and connect.get("type") == "layout":
            entries = [t for t in tiles if "pos" in t]
            if entries:
                assembled_path = directory_dir / "assembled.png"
                layout = _assemble_layout(
                    src_dir=sliced_dir,
                    tile_lookup=tile_lookup,
                    tile_size=(tile_w, tile_h),
                    base_name=base_name,
                    entries=entries,
                    out_path=assembled_path,
                )
                directory_entry["layout"] = layout
                directory_entry["assembled"] = os.fspath(assembled_path.relative_to(out_root))

        if connect and connect.get("type") == "edge_match":
            indexes = [int(t["index"]) for t in tiles]
            top_k = int(connect.get("top_k", 5))
            directory_entry["edge_matches"] = _edge_match_connections(
                src_dir=sliced_dir,
                tile_lookup=tile_lookup,
                indexes=indexes,
                top_k=top_k,
            )

        index["directories"][directory_id] = directory_entry

    missing = sorted(set(tile_lookup.keys()) - used)
    if missing:
        index["unassigned"] = missing

    _write_json(out_root / "tileset.json", index)


if __name__ == "__main__":
    main()
