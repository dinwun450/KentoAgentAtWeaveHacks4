from memory.redis_iris import GRID_SIZE_X, GRID_SIZE_Y, redis_client


def initialize_mock_disaster_grid():
    """
    Simulates the injection of dbt/Snowflake structural data combined with
    live hazard streams into Redis Cloud using an explicit X/Y coordinate plane.
    """
    print("🗺️ Initializing Mock Disaster Map Grid in Redis Cloud...")
    pipe = redis_client.pipeline()

    rubble_coordinates = [(2, 3), (2, 4), (5, 5), (6, 5), (7, 5), (8, 2)]
    for x, y in rubble_coordinates:
        pipe.hset(f"grid:node:{x}:{y}", mapping={"type": "rubble", "passable": "false"})

    visible_survivors = {
        "Survivor-V1": {"x": 3, "y": 4, "status": "injured_visible", "injury_severity": "moderate"},
        "Survivor-V2": {"x": 7, "y": 6, "status": "injured_visible", "injury_severity": "minor"},
    }
    for s_id, data in visible_survivors.items():
        pipe.hset(f"grid:node:{data['x']}:{data['y']}", mapping={"type": "survivor_visible", "id": s_id})
        pipe.hset(f"live:survivor:{s_id}", mapping=data)

    trapped_survivors = {
        "Survivor-T1": {"x": 2, "y": 3, "status": "trapped_beneath", "air_supply": "low"},
        "Survivor-T2": {"x": 5, "y": 5, "status": "trapped_beneath", "air_supply": "stable"},
    }
    for s_id, data in trapped_survivors.items():
        pipe.hset(f"grid:node:{data['x']}:{data['y']}", mapping={"type": "survivor_trapped", "id": s_id})
        pipe.hset(f"live:survivor:{s_id}", mapping=data)

    pipe.execute()
    print("✅ Grid Map successfully hydrated to Redis.")


def display_ascii_map(matrix):
    """Prints a human-readable visual grid layout in your Cursor terminal."""
    print("\n--- OPERATIONAL DISASTER HIVE MAP GRID ---")
    print("   " + " ".join([str(x) for x in range(GRID_SIZE_X)]))
    for y in range(GRID_SIZE_Y):
        row_str = f"{y}  " + " ".join(matrix[y])
        print(row_str)
    print("------------------------------------------\nLEGEND: [.] Clear  [█] Rubble/Blocked  [V] Visible Survivor  [T] Trapped Survivor\n")
