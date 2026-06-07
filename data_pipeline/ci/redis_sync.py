"""Self-contained Snowflake marts -> Redis injector for CI (GitHub Actions).

No dependency on the agent package; reads everything from env vars. Writes the
hash shapes the agents expect:
    grid:node:<x>:<y>        <- mart_city_grid_nodes
    live:survivor:<id>       <- mart_survivor_targets
    route:priority:<road_id> <- mart_route_priorities
"""

import os
import sys
from datetime import datetime, timezone

# Guard: a redis.py at the repo root could shadow the installed `redis` package.
_here = os.path.dirname(os.path.abspath(__file__))
sys.path = [p for p in sys.path if os.path.abspath(p or ".") not in (_here, os.path.dirname(_here))]

import redis
import snowflake.connector


def _s(v):
    return "" if v is None else str(v)


def main():
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "KENTO_AGENT_RUNTIME_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "KENTO_ENTERPRISE_DW"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "MATURED_SEMANTIC_LAYER"),
    )
    r = redis.Redis(
        host=os.environ["REDIS_CLOUD_HOST"],
        port=int(os.getenv("REDIS_CLOUD_PORT", "6379")),
        username=os.getenv("REDIS_CLOUD_USERNAME") or None,
        password=os.getenv("REDIS_CLOUD_PASSWORD") or None,
        ssl=os.getenv("REDIS_CLOUD_SSL", "false").lower() in ("1", "true", "yes"),
        decode_responses=True,
    )

    cur = conn.cursor(snowflake.connector.DictCursor)

    def q(sql):
        cur.execute(sql)
        return [{k.lower(): v for k, v in row.items()} for row in cur.fetchall()]

    grid = q("select * from mart_city_grid_nodes")
    survivors = q("select * from mart_survivor_targets")
    routes = q("select * from mart_route_priorities")
    cur.close()
    conn.close()

    # Clear the previous snapshot.
    for pattern in ("grid:node:*", "live:survivor:*", "route:priority:*"):
        keys = list(r.scan_iter(match=pattern))
        if keys:
            r.delete(*keys)

    g = 0
    for row in grid:
        node_type = row.get("node_type")
        if node_type in (None, "clear"):
            continue
        mapping = {"type": node_type, "passable": _s(row.get("passable")).lower()}
        if row.get("survivor_id"):
            mapping["id"] = row["survivor_id"]
        if row.get("building_id"):
            mapping["building_id"] = row["building_id"]
        if row.get("road_id"):
            mapping["road_id"] = row["road_id"]
        if row.get("rubble_severity"):
            mapping["severity"] = row["rubble_severity"]
        r.hset(f"grid:node:{row['x']}:{row['y']}", mapping=mapping)
        g += 1

    s = 0
    for row in survivors:
        sid = row.get("survivor_id")
        if not sid:
            continue
        r.hset(f"live:survivor:{sid}", mapping={
            k: _s(row.get(k)) for k in (
                "x", "y", "status", "injury_severity", "air_supply",
                "visibility", "recommended_initial_response", "priority_rank", "priority_score",
            )
        })
        s += 1

    rt = 0
    for row in routes:
        rid = row.get("road_id")
        if not rid:
            continue
        r.hset(f"route:priority:{rid}", mapping={k: _s(v) for k, v in row.items()})
        rt += 1

    # Heartbeat: HGETALL pipeline:last_sync to see when Redis was last refreshed.
    r.hset("pipeline:last_sync", mapping={
        "last_sync_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grid_nodes": g,
        "survivors": s,
        "routes": rt,
    })

    print(f"Synced {g} grid nodes, {s} survivors, {rt} routes to Redis.")


if __name__ == "__main__":
    main()
