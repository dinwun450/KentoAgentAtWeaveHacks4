"""Randomly generated survivors.

Snowpark Python model -> KENTO_DB.RAW.raw_survivor_locations. ~40% are trapped
under rubble/buildings (heavy_rescue_team), the rest visible in the open
(medical_aerial_drone). Depends on raw_buildings and raw_rubble_locations.
"""

import random

WIDTH = 10
HEIGHT = 10
N_SURVIVORS = 4


def _rows_as_dicts(df):
    return [{k.lower(): v for k, v in r.as_dict().items()} for r in df.collect()]


def model(dbt, session):
    dbt.config(materialized="table", database="KENTO_DB", schema="RAW")

    rng = random.Random()

    buildings = _rows_as_dicts(dbt.ref("raw_buildings"))
    rubble = _rows_as_dicts(dbt.ref("raw_rubble_locations"))

    building_cells = {(int(b["x"]), int(b["y"])) for b in buildings}
    rubble_cells = {(int(r["x"]), int(r["y"])) for r in rubble}

    all_cells = [(x, y) for y in range(HEIGHT) for x in range(WIDTH)]
    visible_candidates = [c for c in all_cells if c not in rubble_cells]
    trapped_candidates = list(rubble_cells | building_cells)

    used = set()
    rows = []
    for i in range(N_SURVIVORS):
        trapped = rng.random() < 0.4 and any(c not in used for c in trapped_candidates)
        if trapped:
            pool = [c for c in trapped_candidates if c not in used]
        else:
            pool = [c for c in visible_candidates if c not in used]
        if not pool:
            pool = [c for c in all_cells if c not in used]
        if not pool:
            break

        x, y = rng.choice(pool)
        used.add((x, y))
        survivor_id = f"Survivor-{i + 1:03d}"

        if trapped:
            rows.append([
                survivor_id, x, y, "T", "trapped",
                rng.choice(["moderate", "severe", "critical"]),
                rng.choice(["limited", "critical"]),
                "obscured", "heavy_rescue_team", "snowpark_generator",
            ])
        else:
            rows.append([
                survivor_id, x, y, "V", "injured_visible",
                rng.choice(["minor", "moderate", "severe"]),
                "",
                "visible", "medical_aerial_drone", "snowpark_generator",
            ])

    schema = [
        "survivor_id", "x", "y", "map_symbol", "status", "injury_severity",
        "air_supply", "visibility", "recommended_initial_response", "source",
    ]
    return session.create_dataframe(rows, schema=schema)
