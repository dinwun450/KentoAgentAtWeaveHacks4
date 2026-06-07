import weave


@weave.op()
async def plan_route(status: str) -> dict[str, str]:
    if status == "unknown":
        raise ValueError("Survivor telemetry missing from Redis working memory.")

    if status in ("trapped_beneath", "trapped"):
        return {
            "resource_type": "heavy_excavator_drone",
            "priority": "critical",
        }

    return {
        "resource_type": "medical_aerial_drone",
        "priority": "standard",
    }
