import weave

from memory.redis_iris import GRID_SIZE_X, GRID_SIZE_Y

SAFE_DISPATCH_ACTIONS = {
    "trapped_beneath": "heavy_excavator_drone",
    "trapped": "heavy_excavator_drone",
    "injured_visible": "medical_aerial_drone",
}


def reject_missing_survivor_id(survivor_id: str | None) -> str:
    if not survivor_id:
        raise ValueError("Missing survivor ID.")
    return survivor_id


def reject_unknown_coordinates(x: int | str | None, y: int | str | None) -> tuple[int, int]:
    try:
        parsed_x = int(x)
        parsed_y = int(y)
    except (TypeError, ValueError) as exc:
        raise ValueError("Unknown survivor coordinates.") from exc

    if not (0 <= parsed_x < GRID_SIZE_X and 0 <= parsed_y < GRID_SIZE_Y):
        raise ValueError(
            f"Unknown survivor coordinates ({parsed_x}, {parsed_y}) outside grid bounds."
        )

    return parsed_x, parsed_y


def reject_unsafe_dispatch_action(status: str, resource_type: str) -> str:
    expected_resource = SAFE_DISPATCH_ACTIONS.get(status)
    if expected_resource != resource_type:
        raise ValueError(
            f"Unsafe dispatch action '{resource_type}' for survivor status '{status}'."
        )
    return resource_type


@weave.op()
async def evaluate_routing(survivor_id: str, x: int, y: int, status: str) -> str:
    """Evaluates tactical routing choices based on x, y coordinates."""
    if status in ("trapped_beneath", "trapped"):
        return (
            f"🚨 Dispatching Heavy Excavator Drone to coordinate Grid ({x}, {y}) "
            f"for buried target {survivor_id}."
        )
    return (
        f"🚁 Dispatching Medical Aerial Drone to coordinate Grid ({x}, {y}) "
        f"for visible target {survivor_id}."
    )
