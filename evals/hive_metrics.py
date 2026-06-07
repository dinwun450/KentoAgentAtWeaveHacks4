from typing import Any

import weave


def _agent_by_id(agents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(agent["id"]): agent for agent in agents}


def _distance_between_agents(before: dict[str, Any], after: dict[str, Any]) -> int:
    return abs(int(before["x"]) - int(after["x"])) + abs(int(before["y"]) - int(after["y"]))


def _agent_has_assignment(agent: dict[str, Any]) -> bool:
    return bool(agent.get("target_survivor_id"))


def calculate_hive_cycle_metrics(
    *,
    started_at_ns: int,
    cycle_started_at_ns: int,
    cycle_finished_at_ns: int,
    active_survivors_before: list[dict[str, Any]],
    active_survivors_after: list[dict[str, Any]],
    idle_agents_before: list[dict[str, Any]],
    agents_before: list[dict[str, Any]],
    agents_after: list[dict[str, Any]],
    coordination: dict[str, Any],
) -> dict[str, Any]:
    agents_before_by_id = _agent_by_id(agents_before)
    distance_traveled = sum(
        _distance_between_agents(agents_before_by_id[str(agent["id"])], agent)
        for agent in agents_after
        if str(agent["id"]) in agents_before_by_id
    )

    total_agents = len(agents_after)
    utilized_agents = sum(1 for agent in agents_after if _agent_has_assignment(agent))
    assignment_capacity = min(len(active_survivors_before), len(idle_agents_before))
    assignments = coordination.get("assignments", [])

    return {
        "response_time": (cycle_finished_at_ns - cycle_started_at_ns) / 1_000_000_000,
        "rescue_completion_time": (
            (cycle_finished_at_ns - started_at_ns) / 1_000_000_000
            if not active_survivors_after
            else None
        ),
        "distance_traveled": distance_traveled,
        "survivors_rescued": max(0, len(active_survivors_before) - len(active_survivors_after)),
        "agent_utilization": utilized_agents / total_agents if total_agents else 0,
        "coordination_efficiency": len(assignments) / assignment_capacity if assignment_capacity else 1,
    }


@weave.op()
def log_hive_cycle_evaluation(
    tick: int,
    metrics: dict[str, Any],
    cycle: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tick": tick,
        "metrics": metrics,
        "cycle": cycle,
    }
