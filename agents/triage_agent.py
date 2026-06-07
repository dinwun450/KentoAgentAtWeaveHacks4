from typing import Any

import weave

from evals.weave_scorers import reject_missing_survivor_id, reject_unknown_coordinates
from memory.redis_iris import get_survivor


@weave.op()
async def triage_survivor(survivor_id: str | None) -> dict[str, Any]:
    survivor_id = reject_missing_survivor_id(survivor_id)

    survivor_data = get_survivor(survivor_id)
    if not survivor_data:
        raise ValueError("Survivor telemetry missing from Redis working memory.")

    x, y = reject_unknown_coordinates(survivor_data.get("x"), survivor_data.get("y"))

    return {
        "survivor_id": survivor_id,
        "x": x,
        "y": y,
        "status": survivor_data.get("status", "unknown"),
    }
