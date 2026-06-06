import weave
from llama_index.core.workflow import Event, StartEvent, StopEvent, Workflow, step

from agents.rescue_agent import dispatch_rescue
from agents.route_agent import plan_route
from agents.triage_agent import triage_survivor


class TriageEvent(Event):
    survivor_id: str
    x: int
    y: int
    status: str


class RoutePlanEvent(Event):
    survivor_id: str
    x: int
    y: int
    status: str
    resource_type: str
    priority: str


class EscalationEvent(Event):
    survivor_id: str
    x: int
    y: int
    status: str
    reason: str


class HiveOrchestrator(Workflow):

    @step
    @weave.op()
    async def triage(self, ev: StartEvent) -> TriageEvent | EscalationEvent:
        survivor_id = ev.get("survivor_id")

        try:
            telemetry = await triage_survivor(survivor_id)
        except ValueError as exc:
            return EscalationEvent(
                survivor_id=survivor_id or "unknown",
                x=0,
                y=0,
                status="unknown",
                reason=str(exc),
            )

        return TriageEvent(
            survivor_id=telemetry["survivor_id"],
            x=telemetry["x"],
            y=telemetry["y"],
            status=telemetry["status"],
        )

    @step
    @weave.op()
    async def route_planning(self, ev: TriageEvent) -> RoutePlanEvent | EscalationEvent:
        try:
            route = await plan_route(ev.status)
        except ValueError as exc:
            return EscalationEvent(
                survivor_id=ev.survivor_id,
                x=ev.x,
                y=ev.y,
                status=ev.status,
                reason=str(exc),
            )

        return RoutePlanEvent(
            survivor_id=ev.survivor_id,
            x=ev.x,
            y=ev.y,
            status=ev.status,
            resource_type=route["resource_type"],
            priority=route["priority"],
        )

    @step
    @weave.op()
    async def dispatch_resource(self, ev: RoutePlanEvent) -> StopEvent | EscalationEvent:
        try:
            action = await dispatch_rescue(
                survivor_id=ev.survivor_id,
                x=ev.x,
                y=ev.y,
                status=ev.status,
                resource_type=ev.resource_type,
            )
        except ValueError as exc:
            return EscalationEvent(
                survivor_id=ev.survivor_id,
                x=ev.x,
                y=ev.y,
                status=ev.status,
                reason=str(exc),
            )

        return StopEvent(result=action)

    @step
    @weave.op()
    async def escalation(self, ev: EscalationEvent) -> StopEvent:
        return StopEvent(
            result=(
                f"⚠️ Escalating {ev.survivor_id} at coordinate Grid ({ev.x}, {ev.y}): "
                f"{ev.reason}"
            )
        )
