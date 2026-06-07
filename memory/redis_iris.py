import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

import redis

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

REDIS_HOST = os.getenv("REDIS_CLOUD_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_CLOUD_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_CLOUD_PASSWORD", "")

GRID_SIZE_X = 10
GRID_SIZE_Y = 10

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=True,
)


def _survivor_key(survivor_id: str) -> str:
    return f"live:survivor:{survivor_id}"


def _agent_key(agent_id: str) -> str:
    return f"agent:{agent_id}"


def _grid_node_key(x: int, y: int) -> str:
    return f"grid:node:{x}:{y}"


def get_survivor(survivor_id: str) -> dict[str, str]:
    return redis_client.hgetall(_survivor_key(survivor_id))


def set_survivor(survivor_id: str, data: Mapping[str, Any]) -> None:
    if data:
        redis_client.hset(_survivor_key(survivor_id), mapping=data)


def _encode_agent_data(data: Mapping[str, Any]) -> dict[str, Any]:
    encoded = dict(data)

    if "path" in encoded and not isinstance(encoded["path"], str):
        encoded["path"] = json.dumps(encoded["path"])

    for key, value in encoded.items():
        if value is None:
            encoded[key] = ""

    return encoded


def _decode_agent_data(data: dict[str, str]) -> dict[str, Any]:
    if not data:
        return {}

    decoded: dict[str, Any] = dict(data)

    for key in ("x", "y", "cell"):
        if decoded.get(key) not in (None, ""):
            decoded[key] = int(decoded[key])

    if decoded.get("target_cell") in (None, ""):
        decoded["target_cell"] = None
    else:
        decoded["target_cell"] = int(decoded["target_cell"])

    path = decoded.get("path")
    if isinstance(path, str):
        decoded["path"] = json.loads(path) if path else []

    return decoded


def get_agent(agent_id: str) -> dict[str, Any]:
    return _decode_agent_data(redis_client.hgetall(_agent_key(agent_id)))


def set_agent(agent_id: str, data: Mapping[str, Any]) -> None:
    if data:
        redis_client.hset(_agent_key(agent_id), mapping=_encode_agent_data({"id": agent_id, **data}))


def get_all_agents() -> list[dict[str, Any]]:
    agents = []

    for key in redis_client.scan_iter(match="agent:*"):
        agent_id = key.replace("agent:", "", 1)
        agent = get_agent(agent_id)
        if agent:
            agents.append(agent)

    return sorted(agents, key=lambda agent: agent.get("id", ""))


def get_grid_node(x: int, y: int) -> dict[str, str]:
    return redis_client.hgetall(_grid_node_key(x, y))


def set_grid_node(x: int, y: int, data: Mapping[str, Any]) -> None:
    if data:
        redis_client.hset(_grid_node_key(x, y), mapping=data)


def render_grid() -> list[list[str]]:
    matrix = [["." for _ in range(GRID_SIZE_X)] for _ in range(GRID_SIZE_Y)]

    for y in range(GRID_SIZE_Y):
        for x in range(GRID_SIZE_X):
            node = get_grid_node(x, y)
            if node:
                node_type = node.get("type")
                if node_type == "rubble":
                    matrix[y][x] = "█"
                elif node_type == "survivor_visible":
                    matrix[y][x] = "V"
                elif node_type == "survivor_trapped":
                    matrix[y][x] = "T"

    return matrix


def clear_simulation() -> int:
    keys_to_delete = []
    for pattern in ("grid:node:*", "live:survivor:*", "agent:*", "mission:log:*", "hive:status"):
        keys_to_delete.extend(redis_client.scan_iter(match=pattern))

    if not keys_to_delete:
        return 0

    return redis_client.delete(*keys_to_delete)
