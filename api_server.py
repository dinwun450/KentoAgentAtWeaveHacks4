import json
import time

import weave
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.autonomous_hive import (
    get_hive_status,
    run_autonomous_hive_until_complete,
    run_autonomous_tick,
)
from agents.agent_spawner import ensure_default_agents, spawn_agents
from agents.coordinator import assign_best_agent
from agents.hive_orchestrator import HiveOrchestrator
from agents.movement_simulator import assign_agent_to_survivor
from agents.survivor_spawner import spawn_random_survivors
from memory.redis_iris import (
    GRID_SIZE_X,
    GRID_SIZE_Y,
    get_all_agents,
    get_grid_node,
    get_survivor,
    redis_client,
)

import os

if os.getenv("DISABLE_WEAVE", "").lower() not in ("1", "true", "yes"):
    weave.init("kento-agent-hive")

app = FastAPI()


class HiveDispatchRequest(BaseModel):
    survivor_id: str


class AssignAgentRequest(BaseModel):
    agent_id: str
    survivor_id: str


class AssignNearestAgentRequest(BaseModel):
    survivor_id: str


class AutonomousHiveRunRequest(BaseModel):
    max_ticks: int = 100
    tick_sleep_seconds: float = 0


class SpawnSurvivorsRequest(BaseModel):
    count: int


class SpawnAgentsRequest(BaseModel):
    agent_ids: list[str] | None = None


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _log_mission_event(event: str, data: dict) -> None:
    timestamp_ns = time.time_ns()
    redis_client.hset(
        f"mission:log:{timestamp_ns}",
        mapping={
            "event": event,
            "timestamp_ns": timestamp_ns,
            "data": json.dumps(data, default=str),
        },
    )


def _parse_int(value: str | int | None, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_survivors_from_redis():
    survivors = []

    for key in redis_client.scan_iter("live:survivor:*"):
        survivor_id = key.replace("live:survivor:", "", 1)
        data = get_survivor(survivor_id)
        x = _parse_int(data.get("x"))
        y = _parse_int(data.get("y"))
        survivors.append({
            "id": survivor_id,
            "x": x,
            "y": y,
            "cell": y * GRID_SIZE_X + x,
            "status": data.get("status", "unknown"),
            "data": data,
        })

    return sorted(survivors, key=lambda survivor: survivor["id"])


def _decode_mission_log_data(data: dict[str, str]) -> dict[str, str] | list | str:
    raw_data = data.get("data")
    if raw_data is None:
        return data

    try:
        return json.loads(raw_data)
    except json.JSONDecodeError:
        return raw_data


def _get_mission_logs_from_redis():
    logs = []

    for key in redis_client.scan_iter("mission:log:*"):
        data = redis_client.hgetall(key)
        timestamp_ns = _parse_int(data.get("timestamp_ns"))
        logs.append({
            "key": key,
            "event": data.get("event", "unknown"),
            "timestamp_ns": timestamp_ns,
            "data": _decode_mission_log_data(data),
            "raw": data,
        })

    return sorted(logs, key=lambda log: log["timestamp_ns"])


@app.get("/grid-state")
def grid_state():
    cells = []

    # Batch all grid-node reads into a single Redis pipeline round-trip.
    # (100 individual hgetall calls over Redis Cloud took ~13s; this is ~1.)
    coords = [(x, y) for y in range(GRID_SIZE_Y) for x in range(GRID_SIZE_X)]
    pipe = redis_client.pipeline()
    for x, y in coords:
        pipe.hgetall(f"grid:node:{x}:{y}")
    nodes = pipe.execute()

    for (x, y), node in zip(coords, nodes):
        symbol = "."

        if node:
            node_type = node.get("type")
            if node_type == "rubble":
                symbol = "█"
            elif node_type == "survivor_visible":
                symbol = "V"
            elif node_type == "survivor_trapped":
                symbol = "T"

        cells.append({
            "x": x,
            "y": y,
            "cell": y * GRID_SIZE_X + x,
            "symbol": symbol,
            "node": node,
        })

    return {
        "width": GRID_SIZE_X,
        "height": GRID_SIZE_Y,
        "cells": cells,
        "survivors": _get_survivors_from_redis(),
        "agents": get_all_agents(),
        "mission_logs": _get_mission_logs_from_redis(),
        "hive_status": get_hive_status(),
    }


@app.post("/orchestrate")
async def orchestrate():
    workflow = HiveOrchestrator(timeout=10)
    result = await workflow.run()
    _log_mission_event("api_orchestrate_completed", {"result": result})

    return {
        "result": result,
        "grid_state": grid_state(),
    }


@app.post("/assign-agent-to-survivor")
def assign_agent(request: AssignAgentRequest):
    agent_id = request.agent_id.strip()
    survivor_id = request.survivor_id.strip()

    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id is required")
    if not survivor_id:
        raise HTTPException(status_code=400, detail="survivor_id is required")

    try:
        agent = assign_agent_to_survivor(agent_id, survivor_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _log_mission_event(
        "api_agent_assigned",
        {
            "agent_id": agent_id,
            "survivor_id": survivor_id,
            "agent": agent,
        },
    )

    return {
        "agent": agent,
        "grid_state": grid_state(),
    }


@app.post("/spawn-survivors")
def spawn_survivors(request: SpawnSurvivorsRequest):
    if request.count < 1:
        raise HTTPException(status_code=400, detail="count must be at least 1")

    result = spawn_random_survivors(request.count)
    _log_mission_event("api_random_survivors_spawned", result)

    return {
        "result": result,
        "grid_state": grid_state(),
    }


@app.post("/spawn-agents")
def spawn_agents_endpoint(request: SpawnAgentsRequest):
    result = spawn_agents(request.agent_ids)
    _log_mission_event("api_rescue_agents_spawned", {"count": len(result["spawned"])})

    return {
        "result": result,
        "grid_state": grid_state(),
    }


@app.post("/assign-nearest-agent")
def assign_nearest_agent(request: AssignNearestAgentRequest):
    survivor_id = request.survivor_id.strip()

    if not survivor_id:
        raise HTTPException(status_code=400, detail="survivor_id is required")

    result = assign_best_agent(survivor_id)
    _log_mission_event("api_nearest_agent_assignment_completed", result)

    return {
        "result": result,
        "grid_state": grid_state(),
    }


@app.post("/tick-all-agents")
def tick_all_agents():
    tick = run_autonomous_tick()
    _log_mission_event("api_autonomous_simulation_tick_completed", tick)

    return {
        "tick": tick,
        "grid_state": grid_state(),
    }


@app.post("/autonomous-hive/tick")
def autonomous_hive_tick():
    tick = run_autonomous_tick()

    return {
        "tick": tick,
        "grid_state": grid_state(),
    }


@app.post("/autonomous-hive/run")
def autonomous_hive_run(request: AutonomousHiveRunRequest):
    if request.max_ticks < 1:
        raise HTTPException(status_code=400, detail="max_ticks must be at least 1")
    if request.tick_sleep_seconds < 0:
        raise HTTPException(status_code=400, detail="tick_sleep_seconds cannot be negative")

    result = run_autonomous_hive_until_complete(
        max_ticks=request.max_ticks,
        tick_sleep_seconds=request.tick_sleep_seconds,
    )

    return {
        "result": result,
        "grid_state": grid_state(),
    }


@app.get("/autonomous-hive/status")
def autonomous_hive_status():
    return {
        "status": get_hive_status(),
        "grid_state": grid_state(),
    }


@app.post("/mission-status")
def mission_status():
    current_grid_state = grid_state()
    status = {
        "agents": len(current_grid_state["agents"]),
        "survivors": len(current_grid_state["survivors"]),
        "cells": len(current_grid_state["cells"]),
        "mission_logs": len(current_grid_state["mission_logs"]),
        "hive_status": current_grid_state["hive_status"],
    }
    _log_mission_event("api_mission_status_requested", status)

    return {
        "status": status,
        "grid_state": grid_state(),
    }


@app.post("/run-hive-dispatch")
async def run_hive_dispatch(request: HiveDispatchRequest):
    survivor_id = request.survivor_id.strip()
    if not survivor_id:
        raise HTTPException(status_code=400, detail="survivor_id is required")

    workflow = HiveOrchestrator(timeout=10)
    result = await workflow.run()

    return {
        "survivor_id": survivor_id,
        "result": result,
    }


# Seed default rescue agents (A, B, C) on startup so they appear on the grid.
try:
    ensure_default_agents()
except Exception as exc:  # don't block API startup if Redis is briefly unavailable
    print(f"[api_server] agent seeding skipped: {exc}")