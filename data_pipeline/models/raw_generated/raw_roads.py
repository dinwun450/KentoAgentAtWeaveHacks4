"""Road network (deterministic layout, blockage derived from rubble).

Snowpark Python model -> KENTO_DB.RAW.raw_roads. Depends on
raw_rubble_locations to mark which road cells are blocked.
"""

WIDTH = 10
HEIGHT = 10


def _road_cells(width, height):
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


def _rows_as_dicts(df):
    return [{k.lower(): v for k, v in r.as_dict().items()} for r in df.collect()]


def model(dbt, session):
    dbt.config(materialized="table", database="KENTO_DB", schema="RAW")

    rubble = _rows_as_dicts(dbt.ref("raw_rubble_locations"))
    rubble_cells = {(int(r["x"]), int(r["y"])) for r in rubble}

    roads = _road_cells(WIDTH, HEIGHT)

    rows = []
    for (x, y), road_id in sorted(roads.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        blocked = (x, y) in rubble_cells
        rows.append([
            road_id,
            x,
            y,
            "arterial" if "CENTRAL" in road_id else "local",
            blocked,
            "rubble" if blocked else "",
            "snowpark_generator",
        ])

    schema = ["road_id", "x", "y", "road_class", "blocked", "blockage_reason", "source"]
    return session.create_dataframe(rows, schema=schema)
