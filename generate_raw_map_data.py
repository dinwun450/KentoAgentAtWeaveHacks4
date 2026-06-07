#!/usr/bin/env python3
"""
Generate randomized KentoAgent raw map CSV files for Snowflake.

Outputs:
- raw_city_grid.csv
- raw_buildings.csv
- raw_roads.csv
- raw_rubble_locations.csv

Example:
    python generate_raw_map_data.py --seed 42 --width 10 --height 10 --buildings 6 --rubble 10
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def make_building_cells(x: int, y: int, width: int, height: int) -> list[tuple[int, int]]:
    return [(cx, cy) for cy in range(y, y + height) for cx in range(x, x + width)]


def generate_roads(width: int, height: int) -> dict[tuple[int, int], str]:
    roads: dict[tuple[int, int], str] = {}

    # Border roads
    for x in range(width):
        roads[(x, 0)] = "R-NORTH"
        roads[(x, height - 1)] = "R-SOUTH"

    for y in range(height):
        roads[(0, y)] = "R-WEST"
        roads[(width - 1, y)] = "R-EAST"

    # Cross roads through center
    center_y = height // 2
    center_x = width // 2

    for x in range(width):
        roads[(x, center_y)] = "R-CENTRAL-EW"

    for y in range(height):
        roads[(center_x, y)] = "R-CENTRAL-NS"

    return roads


def generate_buildings(
    rng: random.Random,
    width: int,
    height: int,
    building_count: int,
    roads: dict[tuple[int, int], str],
) -> dict[str, dict]:
    buildings: dict[str, dict] = {}
    occupied: set[tuple[int, int]] = set(roads.keys())

    structure_types = ["residential", "commercial", "medical", "school", "warehouse"]
    damage_states = ["intact", "damaged", "unstable", "collapsed"]
    occupancy_risks = {
        "intact": "low",
        "damaged": "medium",
        "unstable": "high",
        "collapsed": "critical",
    }

    attempts = 0
    max_attempts = building_count * 100

    while len(buildings) < building_count and attempts < max_attempts:
        attempts += 1

        bw = rng.choice([1, 2, 2, 3])
        bh = rng.choice([1, 2, 2, 3])

        x = rng.randint(1, max(1, width - bw - 2))
        y = rng.randint(1, max(1, height - bh - 2))

        cells = make_building_cells(x, y, bw, bh)

        if any(cell in occupied for cell in cells):
            continue

        building_id = f"B-{len(buildings) + 1:03d}"
        damage_state = rng.choices(
            damage_states,
            weights=[35, 35, 20, 10],
            k=1,
        )[0]

        buildings[building_id] = {
            "building_id": building_id,
            "building_name": f"Structure {building_id}",
            "cells": cells,
            "structure_type": rng.choice(structure_types),
            "damage_state": damage_state,
            "occupancy_risk": occupancy_risks[damage_state],
        }

        occupied.update(cells)

    return buildings


def generate_rubble(
    rng: random.Random,
    width: int,
    height: int,
    rubble_count: int,
    buildings: dict[str, dict],
    roads: dict[tuple[int, int], str],
) -> list[dict]:
    rubble: list[dict] = []

    building_by_cell = {
        cell: building_id
        for building_id, building in buildings.items()
        for cell in building["cells"]
    }

    preferred_cells = list(building_by_cell.keys()) + list(roads.keys())
    all_cells = [(x, y) for y in range(height) for x in range(width)]
    candidate_cells = preferred_cells + all_cells

    used: set[tuple[int, int]] = set()

    for i in range(rubble_count):
        available = [cell for cell in candidate_cells if cell not in used]
        if not available:
            break

        x, y = rng.choice(available)
        used.add((x, y))

        associated_building_id = building_by_cell.get((x, y), "")
        severity = rng.choices(
            ["moderate", "high", "critical"],
            weights=[35, 45, 20],
            k=1,
        )[0]

        rubble.append({
            "rubble_id": f"RUB-{i + 1:03d}",
            "x": x,
            "y": y,
            "severity": severity,
            "passable": False,
            "associated_building_id": associated_building_id,
            "source": "random_seed_generator",
        })

    return rubble


def write_raw_buildings(output_dir: Path, buildings: dict[str, dict]) -> None:
    with (output_dir / "raw_buildings.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "building_id",
                "building_name",
                "x",
                "y",
                "structure_type",
                "damage_state",
                "occupancy_risk",
                "source",
            ],
        )
        writer.writeheader()

        for building in buildings.values():
            for x, y in building["cells"]:
                writer.writerow({
                    "building_id": building["building_id"],
                    "building_name": building["building_name"],
                    "x": x,
                    "y": y,
                    "structure_type": building["structure_type"],
                    "damage_state": building["damage_state"],
                    "occupancy_risk": building["occupancy_risk"],
                    "source": "random_seed_generator",
                })


def write_raw_roads(output_dir: Path, roads: dict[tuple[int, int], str], rubble_cells: set[tuple[int, int]]) -> None:
    with (output_dir / "raw_roads.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "road_id",
                "x",
                "y",
                "road_class",
                "blocked",
                "blockage_reason",
                "source",
            ],
        )
        writer.writeheader()

        for (x, y), road_id in sorted(roads.items(), key=lambda item: (item[0][1], item[0][0])):
            blocked = (x, y) in rubble_cells
            writer.writerow({
                "road_id": road_id,
                "x": x,
                "y": y,
                "road_class": "arterial" if "CENTRAL" in road_id else "local",
                "blocked": bool_text(blocked),
                "blockage_reason": "rubble" if blocked else "",
                "source": "random_seed_generator",
            })


def write_raw_rubble_locations(output_dir: Path, rubble: list[dict]) -> None:
    with (output_dir / "raw_rubble_locations.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rubble_id",
                "x",
                "y",
                "severity",
                "passable",
                "associated_building_id",
                "source",
            ],
        )
        writer.writeheader()

        for row in rubble:
            writer.writerow({
                **row,
                "passable": bool_text(row["passable"]),
            })


def write_raw_city_grid(
    output_dir: Path,
    width: int,
    height: int,
    buildings: dict[str, dict],
    roads: dict[tuple[int, int], str],
    rubble: list[dict],
) -> None:
    building_cells = {
        cell
        for building in buildings.values()
        for cell in building["cells"]
    }

    rubble_cells = {(row["x"], row["y"]) for row in rubble}

    with (output_dir / "raw_city_grid.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "map_id",
                "x",
                "y",
                "map_symbol",
                "base_terrain",
                "has_building",
                "has_road",
                "has_rubble",
                "has_survivor",
                "survivor_id",
                "passable",
                "source",
            ],
        )
        writer.writeheader()

        for y in range(height):
            for x in range(width):
                cell = (x, y)
                has_rubble = cell in rubble_cells
                has_road = cell in roads
                has_building = cell in building_cells

                # This generator only creates raw map/building/road/rubble data.
                # Survivor locations can be added later by a separate survivor generator.
                map_symbol = "█" if has_rubble else "."

                writer.writerow({
                    "map_id": "KENTO_RANDOM_CITY_BLOCK",
                    "x": x,
                    "y": y,
                    "map_symbol": map_symbol,
                    "base_terrain": "urban",
                    "has_building": bool_text(has_building),
                    "has_road": bool_text(has_road),
                    "has_rubble": bool_text(has_rubble),
                    "has_survivor": "false",
                    "survivor_id": "",
                    "passable": bool_text(not has_rubble),
                    "source": "random_seed_generator",
                })


def print_ascii_preview(width: int, height: int, rubble: list[dict]) -> None:
    rubble_cells = {(row["x"], row["y"]) for row in rubble}
    print("\n--- GENERATED RAW MAP PREVIEW ---")
    print("   " + " ".join(str(x) for x in range(width)))
    for y in range(height):
        row = []
        for x in range(width):
            row.append("█" if (x, y) in rubble_cells else ".")
        print(f"{y:<2} " + " ".join(row))
    print("---------------------------------\nLEGEND: [.] Clear  [█] Rubble/Blocked\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=10)
    parser.add_argument("--height", type=int, default=10)
    parser.add_argument("--buildings", type=int, default=6)
    parser.add_argument("--rubble", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("generated_raw_map_data"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    roads = generate_roads(args.width, args.height)
    buildings = generate_buildings(rng, args.width, args.height, args.buildings, roads)
    rubble = generate_rubble(rng, args.width, args.height, args.rubble, buildings, roads)
    rubble_cells = {(row["x"], row["y"]) for row in rubble}

    write_raw_buildings(args.output_dir, buildings)
    write_raw_roads(args.output_dir, roads, rubble_cells)
    write_raw_rubble_locations(args.output_dir, rubble)
    write_raw_city_grid(args.output_dir, args.width, args.height, buildings, roads, rubble)

    print(f"Generated CSV files in: {args.output_dir.resolve()}")
    print(f"Seed: {args.seed}")
    print(f"Buildings: {len(buildings)}")
    print(f"Rubble locations: {len(rubble)}")
    print_ascii_preview(args.width, args.height, rubble)


if __name__ == "__main__":
    main()
