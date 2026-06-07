"""Randomly generated buildings (one row per occupied cell).

Snowpark Python model -> KENTO_DB.RAW.raw_buildings. Regenerated on every dbt
run (random each time), so a scheduled dbt Cloud job produces fresh data with no
local dependency. Ported from generate_raw_map_data.py.
"""

import random

WIDTH = 10
HEIGHT = 10
N_BUILDINGS = 6

STRUCTURE_TYPES = ["residential", "commercial", "medical", "school", "warehouse"]
DAMAGE_STATES = ["intact", "damaged", "unstable", "collapsed"]
OCCUPANCY_RISK = {"intact": "low", "damaged": "medium", "unstable": "high", "collapsed": "critical"}


def _road_cells(width, height):
    """Deterministic road layout (border + central cross), same as the roads model."""
    cells = {}
    for x in range(width):
        cells[(x, 0)] = "R-NORTH"
        cells[(x, height - 1)] = "R-SOUTH"
    for y in range(height):
        cells[(0, y)] = "R-WEST"
        cells[(width - 1, y)] = "R-EAST"
    cy, cx = height // 2, width // 2
    for x in range(width):
        cells[(x, cy)] = "R-CENTRAL-EW"
    for y in range(height):
        cells[(cx, y)] = "R-CENTRAL-NS"
    return cells


def _building_cells(x, y, w, h):
    return [(cx, cy) for cy in range(y, y + h) for cx in range(x, x + w)]


def model(dbt, session):
    dbt.config(materialized="table", database="KENTO_DB", schema="RAW")

    rng = random.Random()  # system entropy -> different layout every run
    occupied = set(_road_cells(WIDTH, HEIGHT).keys())

    rows = []
    made = 0
    attempts = 0
    while made < N_BUILDINGS and attempts < N_BUILDINGS * 100:
        attempts += 1
        bw = rng.choice([1, 2, 2, 3])
        bh = rng.choice([1, 2, 2, 3])
        x = rng.randint(1, max(1, WIDTH - bw - 2))
        y = rng.randint(1, max(1, HEIGHT - bh - 2))
        cells = _building_cells(x, y, bw, bh)
        if any(c in occupied for c in cells):
            continue

        made += 1
        building_id = f"B-{made:03d}"
        damage = rng.choices(DAMAGE_STATES, weights=[35, 35, 20, 10], k=1)[0]
        structure = rng.choice(STRUCTURE_TYPES)
        for (cx, cy) in cells:
            rows.append([
                building_id,
                f"Structure {building_id}",
                cx,
                cy,
                structure,
                damage,
                OCCUPANCY_RISK[damage],
                "snowpark_generator",
            ])
        occupied.update(cells)

    schema = [
        "building_id", "building_name", "x", "y",
        "structure_type", "damage_state", "occupancy_risk", "source",
    ]
    return session.create_dataframe(rows, schema=schema)
