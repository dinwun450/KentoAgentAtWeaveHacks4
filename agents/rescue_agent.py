import weave

from evals.weave_scorers import evaluate_routing, reject_unsafe_dispatch_action


@weave.op()
async def dispatch_rescue(
    survivor_id: str,
    x: int,
    y: int,
    status: str,
    resource_type: str,
) -> str:
    reject_unsafe_dispatch_action(status, resource_type)
    return await evaluate_routing(survivor_id=survivor_id, x=x, y=y, status=status)
