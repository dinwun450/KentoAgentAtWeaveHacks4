"""Randomly generated rubble locations.

Snowpark Python model -> KENTO_DB.RAW.raw_rubble_locations. Depends on
raw_buildings so rubble can be associated with collapsed structures.
"""

import random

WIDTH = 10
HEIGHT = 10
N_RUBBLE = 10


def _rows_as_dicts(df):
    return [{k.lower(): v for k, v in r.as_dict().items()} for r in df.collect()]


def model(dbt, session):
    dbt.config(materialized="table", database="KENTO_DB", schema="RAW")

    rng = random.Random()

    buildings = _rows_as_dicts(dbt.ref("raw_buildings"))
    building_by_cell = {(int(b["x"]), int(b["y"])): b["building_id"] for b in buildings}

    all_cells = [(x, y) for y in range(HEIGHT) for x in range(WIDTH)]
    # Prefer building cells, then any cell.
    candidates = list(building_by_cell.keys()) + all_cells

    used = set()
    rows = []
    for i in range(N_RUBBLE):
        available = [c for c in candidates if c not in used]
        if not available:
            break
        x, y = rng.choice(available)
        used.add((x, y))
        severity = rng.choices(["moderate", "high", "critical"], weights=[35, 45, 20], k=1)[0]
        rows.append([
            f"RUB-{i + 1:03d}",
            x,
            y,
            severity,
            False,                              # passable
            building_by_cell.get((x, y), ""),   # associated_building_id
            "snowpark_generator",
        ])

    schema = ["rubble_id", "x", "y", "severity", "passable", "associated_building_id", "source"]
    return session.create_dataframe(rows, schema=schema)
