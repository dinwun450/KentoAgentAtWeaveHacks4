import snowflake.connector, redis, json

snow = snowflake.connector.connect(
    account="your_account", user="your_user", password="your_password",
    warehouse="your_warehouse", database="your_db", schema="MARTS")
r = redis.Redis(host="your_redis_host", port=6379, password="your_redis_password")
cur = snow.cursor()

def load(query, key_fn):
    cur.execute(query)
    cols = [c[0].lower() for c in cur.description]
    for row in cur:
        rec = dict(zip(cols, row))
        r.set(key_fn(rec), json.dumps(rec))

load("SELECT * FROM mart_city_grid_nodes",  lambda d: f"grid:node:{d['x']}:{d['y']}")
load("SELECT * FROM mart_survivor_targets", lambda d: f"live:survivor:{d['survivor_id']}")
load("SELECT * FROM mart_route_priorities", lambda d: f"agent:task:{d['task_id']}")
load("SELECT * FROM agent_mission_history", lambda d: f"mission:state:{d['mission_id']}")

print("Cubby filled.")
