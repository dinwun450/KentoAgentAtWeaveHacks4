import json
import time
from typing import Any

import weave
from llama_index.core.workflow import Event, StartEvent, StopEvent, Workflow, step

from agents.coordinator import orchestrate_rescue_operations
from agents.movement_simulator import move_all_agents
from agents.rescue_agent import dispatch_rescue
from agents.route_agent import plan_route
from memory.redis_iris import redis_client


class CoordinatorEvent(Event):
    summary: dict[str, Any]


class RoutePlanEvent(Event):
    summary: dict[str, Any]


class RescueDispatchEvent(Event):
    summary: dict[str, Any]


def _log_mission_event(event: str, data: dict[str, Any]) -> None:
    timestamp_ns = time.time_ns()
    redis_client.hset(
        f"mission:log:{timestamp_ns}",
        mapping={
            "event": event,
            "timestamp_ns": timestamp_ns,
            "data": json.dumps(data, default=str),
        },
    )


def _survivors_by_id(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {survivor["id"]: survivor for survivor in summary.get("active_survivors", [])}


class HiveOrchestrator(Workflow):

    @step
    @weave.op()
    async def coordinate(self, ev: StartEvent) -> CoordinatorEvent:
        summary = orchestrate_rescue_operations()
        _log_mission_event("coordination_completed", summary)

        return CoordinatorEvent(summary=summary)

    @step
    @weave.op()
    async def route_planning(self, ev: CoordinatorEvent) -> RoutePlanEvent:
        survivors_by_id = _survivors_by_id(ev.summary)
        route_plans = []
        route_errors = []

        for assignment in ev.summary.get("assignments", []):
            survivor = survivors_by_id.get(assignment["survivor_id"])
            if survivor is None:
                route_errors.append(
                    {
                        "survivor_id": assignment["survivor_id"],
                        "reason": "assigned survivor missing from active survivor list",
                    }
                )
                continue

            try:
                route = await plan_route(survivor["status"])
            except ValueError as exc:
                route_errors.append(
                    {
                        "survivor_id": survivor["id"],
                        "agent_id": assignment["agent_id"],
                        "reason": str(exc),
                    }
                )
                continue

            route_plans.append(
                {
                    **assignment,
                    "survivor": survivor,
                    "resource_type": route["resource_type"],
                    "priority": route["priority"],
                }
            )

        summary = {
            **ev.summary,
            "route_plans": route_plans,
            "route_errors": route_errors,
        }
        _log_mission_event("route_planning_completed", summary)

        return RoutePlanEvent(summary=summary)

    @step
    @weave.op()
    async def dispatch_resource(self, ev: RoutePlanEvent) -> RescueDispatchEvent:
        dispatches = []
        dispatch_errors = []

        for route_plan in ev.summary.get("route_plans", []):
            survivor = route_plan["survivor"]

            try:
                dispatch_result = await dispatch_rescue(
                    survivor_id=survivor["id"],
                    x=survivor["x"],
                    y=survivor["y"],
                    status=survivor["status"],
                    resource_type=route_plan["resource_type"],
                )
            except ValueError as exc:
                dispatch_errors.append(
                    {
                        "survivor_id": survivor["id"],
                        "agent_id": route_plan["agent_id"],
                        "reason": str(exc),
                    }
                )
                continue

            dispatches.append(
                {
                    **route_plan,
                    "dispatch_result": dispatch_result,
                }
            )

        summary = {
            **ev.summary,
            "dispatches": dispatches,
            "dispatch_errors": dispatch_errors,
        }
        _log_mission_event("rescue_dispatch_completed", summary)

        return RescueDispatchEvent(summary=summary)

    @step
    @weave.op()
    async def start_movement(self, ev: RescueDispatchEvent) -> StopEvent:
        moved_agents = move_all_agents()
        summary = {
            **ev.summary,
            "moved_agents": moved_agents,
        }
        _log_mission_event("movement_tick_completed", summary)

        return StopEvent(result=summary)
