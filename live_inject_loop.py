"""Local near-real-time injector.

Every N seconds (default 10), read the latest Snowflake marts and push them into
Redis Cloud so the CopilotKit dashboard (which polls /grid-state every 2s)
updates in near-real-time. dbt Cloud regenerates the Snowpark marts every minute;
this loop reflects the latest snapshot into Redis every 100s (slow enough that
field agents can fully rescue a scenario before it refreshes).

Agents (agent:*) are preserved — only grid/survivor/route keys are refreshed.

Run from KentoAgentAtWeaveHacks4/:
    ..\\venv\\Scripts\\python.exe live_inject_loop.py [interval_seconds]
"""

import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import snowflake.connector
from memory.redis_iris import redis_client

INTERVAL = float(sys.argv[1]) if len(sys.argv) > 1 else 100.0
DB = os.getenv("SNOWFLAKE_DATABASE", "KENTO_DB")
SCHEMA = os.getenv("SNOWFLAKE_SCHEMA", "DBT_KENTO")


def connect_snowflake():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "KENTO_AGENT_RUNTIME_WH"),
        database=DB,
        schema=SCHEMA,
    )


def _s(v):
    return "" if v is None else str(v)


def _fetch(cur, table):
    cur.execute(f"select * from {DB}.{SCHEMA}.{table}")
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def inject(cur):
    grid = _fetch(cur, "mart_city_grid_nodes")
    survivors = _fetch(cur, "mart_survivor_targets")
    routes = _fetch(cur, "mart_route_priorities")

    # Keys to replace (agents are intentionally NOT cleared).
    old_keys = []
    for pattern in ("grid:node:*", "live:survivor:*", "route:priority:*"):
        old_keys.extend(redis_client.scan_iter(match=pattern))

    # Apply clear + all writes as ONE atomic transaction so the dashboard never
    # observes a partial/empty state mid-refresh.
    pipe = redis_client.pipeline(transaction=True)
    if old_keys:
        pipe.delete(*old_keys)

    g = 0
    for r in grid:
        node_type = r.get("node_type")
        if node_type in (None, "clear"):
            continue
        mapping = {"type": node_type, "passable": _s(r.get("passable")).lower()}
        if r.get("survivor_id"):
            mapping["id"] = r["survivor_id"]
        if r.get("building_id"):
            mapping["building_id"] = r["building_id"]
        if r.get("road_id"):
            mapping["road_id"] = r["road_id"]
        if r.get("rubble_severity"):
            mapping["severity"] = r["rubble_severity"]
        pipe.hset(f"grid:node:{r['x']}:{r['y']}", mapping=mapping)
        g += 1

    s = 0
    for r in survivors:
        sid = r.get("survivor_id")
        if not sid:
            continue
        pipe.hset(
            f"live:survivor:{sid}",
            mapping={k: _s(r.get(k)) for k in (
                "x", "y", "status", "injury_severity", "air_supply",
                "visibility", "recommended_initial_response", "priority_rank", "priority_score",
            )},
        )
        s += 1

    rt = 0
    for r in routes:
        rid = r.get("road_id")
        if not rid:
            continue
        pipe.hset(f"route:priority:{rid}", mapping={k: _s(v) for k, v in r.items()})
        rt += 1

    pipe.hset(
        "pipeline:last_sync",
        mapping={
            "last_sync_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "grid_nodes": g,
            "survivors": s,
            "routes": rt,
        },
    )
    pipe.execute()
    return g, s, rt


def fingerprint(cur):
    """Cheap order-independent hash of the three marts to detect changes
    without re-reading every row each tick."""
    cur.execute(
        f"select "
        f"(select hash_agg(*) from {DB}.{SCHEMA}.mart_city_grid_nodes), "
        f"(select hash_agg(*) from {DB}.{SCHEMA}.mart_survivor_targets), "
        f"(select hash_agg(*) from {DB}.{SCHEMA}.mart_route_priorities)"
    )
    return tuple(cur.fetchone())


def main():
    print(f"Live injector loop: {DB}.{SCHEMA} -> Redis every {INTERVAL}s, inject only on change (Ctrl+C to stop)", flush=True)
    conn = connect_snowflake()
    cur = conn.cursor()
    last_fp = None
    try:
        while True:
            start = time.time()
            now = datetime.now().strftime("%H:%M:%S")
            try:
                if str(redis_client.get("sim:paused") or "").lower() in ("1", "true", "yes"):
                    # Simulation mode: the field agents own the survivor/grid keys.
                    print(f"[{now}] paused (simulation mode) - skip", flush=True)
                    last_fp = None  # force a resync when the loop resumes
                else:
                    fp = fingerprint(cur)
                    if fp == last_fp:
                        redis_client.hset(
                            "pipeline:last_sync", "last_check_utc",
                            datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        )
                        print(f"[{now}] unchanged - skip", flush=True)
                    else:
                        g, s, rt = inject(cur)
                        last_fp = fp
                        print(f"[{now}] CHANGED -> synced grid={g} survivors={s} routes={rt}", flush=True)
            except Exception as exc:
                print(f"[{now}] error: {exc} (reconnecting)", flush=True)
                last_fp = None
                try:
                    conn.close()
                except Exception:
                    pass
                conn = connect_snowflake()
                cur = conn.cursor()
            time.sleep(max(0.0, INTERVAL - (time.time() - start)))
    finally:
        try:
            cur.close(); conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
