"""City grid (one row per cell), derived from the other generated raw tables.

Snowpark Python model -> KENTO_DB.RAW.raw_city_grid. Depends on raw_buildings,
raw_roads, raw_rubble_locations, raw_survivor_locations so the grid flags stay
consistent with them.
"""

WIDTH = 10
HEIGHT = 10


def _rows_as_dicts(df):
    return [{k.lower(): v for k, v in r.as_dict().items()} for r in df.collect()]


def model(dbt, session):
    dbt.config(materialized="table", database="KENTO_DB", schema="RAW")

    buildings = _rows_as_dicts(dbt.ref("raw_buildings"))
    roads = _rows_as_dicts(dbt.ref("raw_roads"))
    rubble = _rows_as_dicts(dbt.ref("raw_rubble_locations"))
    survivors = _rows_as_dicts(dbt.ref("raw_survivor_locations"))

    building_cells = {(int(b["x"]), int(b["y"])) for b in buildings}
    road_cells = {(int(r["x"]), int(r["y"])) for r in roads}
    rubble_cells = {(int(r["x"]), int(r["y"])) for r in rubble}
    survivor_by_cell = {(int(s["x"]), int(s["y"])): s for s in survivors}

    rows = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            cell = (x, y)
            has_building = cell in building_cells
            has_road = cell in road_cells
            has_rubble = cell in rubble_cells
            survivor = survivor_by_cell.get(cell)
            has_survivor = survivor is not None

            if has_survivor:
                map_symbol = survivor["map_symbol"]
            elif has_rubble:
                map_symbol = "█"  # full block
            else:
                map_symbol = "."

            rows.append([
                "KENTO_RANDOM_CITY_BLOCK",
                x,
                y,
                map_symbol,
                "urban",
                has_building,
                has_road,
                has_rubble,
                has_survivor,
                survivor["survivor_id"] if has_survivor else "",
                not has_rubble,                 # passable
                "snowpark_generator",
            ])

    schema = [
        "map_id", "x", "y", "map_symbol", "base_terrain",
        "has_building", "has_road", "has_rubble", "has_survivor",
        "survivor_id", "passable", "source",
    ]
    return session.create_dataframe(rows, schema=schema)
