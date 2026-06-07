"""Agentic field rescue agents — an observe / think / act / report loop.

HiveOrchestrator stays the STRATEGIC commander (triage -> route -> dispatch).
Each FieldAgent makes TACTICAL decisions on the ground from live Redis state:

  observe  - read grid, own task, nearby cells, survivors, rubble, other agents
  think    - decide the next best action (no side effects)
  act      - move / reroute around rubble / rescue / request backup / report blocked
  report   - write mission logs to Redis

Behaviours:
  * if the next path cell is blocked, it reroutes automatically (obstacle-aware BFS)
  * if it reaches a (visible) survivor, it rescues them and clears V/T from the grid
  * if it reaches a TRAPPED survivor, it writes a backup request to Redis and waits;
    once a second agent is adjacent, the two perform the heavy rescue
  * an idle agent prefers answering an open backup request before taking a fresh target
"""

import json
import os
import time
import urllib.request
from collections import deque
from typing import Any, Literal, Optional

import weave
from pydantic import BaseModel, ValidationError

from memory.redis_iris import (
    GRID_SIZE_X,
    GRID_SIZE_Y,
    get_agent,
    get_all_agents,
    get_survivor,
    redis_client,
    set_agent,
    set_grid_node,
    set_survivor,
)

TRAPPED_STATUSES = {"trapped", "trapped_beneath"}
RESCUED_STATUS = "rescued"

LLM_MODEL = os.getenv("FIELD_AGENT_LLM_MODEL", "gpt-4o-mini")
LLM_TIMEOUT_SECONDS = float(os.getenv("FIELD_AGENT_LLM_TIMEOUT", "8"))


class LLMDecision(BaseModel):
    """The ONLY shape the LLM may return. `action` is constrained; the LLM never
    emits coordinates or paths — deterministic BFS computes those in act()."""

    action: Literal["engage", "request_backup", "wait", "idle"]
    survivor_id: Optional[str] = None
    reasoning: Optional[str] = None


def _use_llm() -> bool:
    return (
        os.getenv("FIELD_AGENT_USE_LLM", "0").lower() in ("1", "true", "yes")
        and bool(os.getenv("OPENAI_API_KEY"))
    )


def _build_llm_messages(obs: dict, agent_id: str) -> list[dict]:
    agent = obs["agent"]
    ax, ay = int(agent["x"]), int(agent["y"])
    survivors = [
        {"id": s["id"], "x": s["x"], "y": s["y"], "status": s["status"],
         "distance": abs(s["x"] - ax) + abs(s["y"] - ay)}
        for s in obs["survivors"].values() if s["status"] != RESCUED_STATUS
    ]
    others = [
        {"id": aid, "x": int(a["x"]), "y": int(a["y"]), "target": a.get("target_survivor_id", "")}
        for aid, a in obs.get("other_agents", {}).items()
    ]
    state = {
        "you": {"id": agent_id, "x": ax, "y": ay, "current_target": agent.get("target_survivor_id", "")},
        "survivors": survivors,
        "other_agents": others,
        "rubble_cell_count": len(obs.get("rubble_cells", [])),
    }
    system = (
        "You are a tactical search-and-rescue field agent on a 10x10 grid. Pick the "
        "single best next action for YOUR agent. Visible survivors can be rescued solo; "
        "trapped survivors need a backup agent. Prefer the most urgent reachable survivor "
        "and avoid a survivor another agent already covers unless it is trapped and needs "
        "backup. Respond with ONLY a JSON object of this exact shape: "
        '{"action": "engage"|"request_backup"|"wait"|"idle", '
        '"survivor_id": <survivor id string or null>, "reasoning": <short string>}. '
        "'engage' = pursue/rescue a survivor (movement is computed for you); "
        "'request_backup' = trapped survivor needs help; 'wait' = hold; 'idle' = nothing to do. "
        "Never output coordinates, paths, or any other fields."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Current situation:\n" + json.dumps(state)},
    ]


def _call_openai_json(messages: list[dict]) -> dict | None:
    """Call OpenAI chat completions forcing a JSON object. Returns the parsed
    dict, or None on any failure/timeout so the caller can fall back to rules."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 200,
    }).encode()
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read())
        return json.loads(data["choices"][0]["message"]["content"])
    except Exception:
        return None

# Actions worth recording to the mission log (routine moves/idle are skipped to
# avoid flooding mission:log:* and slowing /grid-state).
_SIGNIFICANT = {"self_assign", "respond_backup", "rescue", "request_backup", "reroute", "blocked", "drop_target"}


# --------------------------------------------------------------------------- #
# grid / geometry helpers
# --------------------------------------------------------------------------- #
def _cell_to_xy(cell: int) -> tuple[int, int]:
    return cell % GRID_SIZE_X, cell // GRID_SIZE_X


def _xy_to_cell(x: int, y: int) -> int:
    return y * GRID_SIZE_X + x


def _neighbors(cell: int) -> list[int]:
    x, y = _cell_to_xy(cell)
    out = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < GRID_SIZE_X and 0 <= ny < GRID_SIZE_Y:
            out.append(_xy_to_cell(nx, ny))
    return out


def _node_passable(node: dict | None) -> bool:
    if not node:
        return True  # empty cell == clear == passable
    return str(node.get("passable", "true")).lower() != "false"


def _snapshot_grid() -> dict[int, dict]:
    """One pipelined read of the whole grid: {cell -> node hash}."""
    coords = [(x, y) for y in range(GRID_SIZE_Y) for x in range(GRID_SIZE_X)]
    pipe = redis_client.pipeline()
    for x, y in coords:
        pipe.hgetall(f"grid:node:{x}:{y}")
    return {_xy_to_cell(x, y): node for (x, y), node in zip(coords, pipe.execute())}


def _live_survivors() -> dict[str, dict]:
    keys = list(redis_client.scan_iter(match="live:survivor:*"))
    if not keys:
        return {}
    pipe = redis_client.pipeline()
    for k in keys:
        pipe.hgetall(k)
    out: dict[str, dict] = {}
    for k, data in zip(keys, pipe.execute()):
        if not data:
            continue
        try:
            x, y = int(data["x"]), int(data["y"])
        except (KeyError, TypeError, ValueError):
            continue
        sid = k.split(":")[-1]
        out[sid] = {
            "id": sid, "x": x, "y": y, "cell": _xy_to_cell(x, y),
            "status": data.get("status", "unknown"),
        }
    return out


def _bfs_path(grid: dict[int, dict], start: int, goal: int, blocked: set[int] | None = None) -> list[int]:
    """Shortest path avoiding rubble (exclusive of start, inclusive of goal).

    Other agents are NOT treated as walls here — they are transient and would
    deadlock routing. Collisions are avoided at move time by waiting one tick if
    the next cell is occupied. `blocked` may still be passed for hard exclusions.
    """
    blocked = blocked or set()
    if start == goal:
        return []
    prev = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nb in _neighbors(cur):
            if nb in prev:
                continue
            if nb in blocked:
                continue
            if nb != goal and not _node_passable(grid.get(nb)):
                continue
            prev[nb] = cur
            if nb == goal:
                path = []
                node = nb
                while node != start:
                    path.append(node)
                    node = prev[node]
                return list(reversed(path))
            queue.append(nb)
    return []


def _approach_cell(grid: dict[int, dict], survivor: dict, agent_cell: int) -> int | None:
    """Where the agent should stand. Visible survivors: their cell. Trapped
    survivors (often on impassable rubble): the nearest passable neighbour."""
    scell = survivor["cell"]
    if survivor["status"] not in TRAPPED_STATUSES:
        return scell
    ax, ay = _cell_to_xy(agent_cell)
    options = [n for n in _neighbors(scell) if _node_passable(grid.get(n))]
    if not options:
        return None
    return min(options, key=lambda c: abs(_cell_to_xy(c)[0] - ax) + abs(_cell_to_xy(c)[1] - ay))


# --------------------------------------------------------------------------- #
# redis side-effects (mission log, backup, rescue)
# --------------------------------------------------------------------------- #
def _log(event: str, **data: Any) -> None:
    ts = time.time_ns()
    redis_client.hset(
        f"mission:log:{ts}",
        mapping={"event": event, "timestamp_ns": ts, "data": json.dumps(data, default=str)},
    )


def _backup_key(survivor_id: str) -> str:
    return f"backup:request:{survivor_id}"


def _request_backup(survivor: dict, agent_id: str, reason: str) -> None:
    redis_client.hset(
        _backup_key(survivor["id"]),
        mapping={
            "survivor_id": survivor["id"], "x": survivor["x"], "y": survivor["y"],
            "cell": survivor["cell"], "requested_by": agent_id, "reason": reason,
            "status": "open", "requested_at_ns": time.time_ns(),
        },
    )


def _open_backup_survivor(survivors: dict, agents: dict, self_id: str) -> dict | None:
    """A trapped survivor with an open backup request still needing a responder."""
    for key in redis_client.scan_iter(match="backup:request:*"):
        req = redis_client.hgetall(key)
        sid = key.split(":")[-1]
        survivor = survivors.get(sid)
        if not survivor or survivor["status"] == RESCUED_STATUS or req.get("status") != "open":
            redis_client.delete(key)
            continue
        responders = [a for aid, a in agents.items()
                      if aid != self_id and str(a.get("target_survivor_id")) == sid]
        if len(responders) < 2:
            return survivor
    return None


def _rescue(agent_id: str, survivor: dict) -> None:
    sx, sy = survivor["x"], survivor["y"]
    data = get_survivor(survivor["id"])
    if data:
        set_survivor(survivor["id"], {**data, "status": RESCUED_STATUS})
    # clear the V/T marker from the grid
    set_grid_node(sx, sy, {"type": "clear", "passable": "true"})
    redis_client.hdel(f"grid:node:{sx}:{sy}", "id")
    redis_client.delete(_backup_key(survivor["id"]))


def _other_agent_cells(agents: dict, self_id: str) -> set[int]:
    cells = set()
    for aid, a in agents.items():
        if aid == self_id:
            continue
        try:
            cells.add(int(a["cell"]))
        except (KeyError, TypeError, ValueError):
            pass
    return cells


def _agents_adjacent_to(agents: dict, self_id: str, cell: int) -> list[str]:
    cx, cy = _cell_to_xy(cell)
    out = []
    for aid, a in agents.items():
        if aid == self_id:
            continue
        try:
            if abs(int(a["x"]) - cx) + abs(int(a["y"]) - cy) == 1:
                out.append(aid)
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _targeted_survivor_ids(agents: dict, self_id: str) -> set[str]:
    return {
        str(a["target_survivor_id"])
        for aid, a in agents.items()
        if aid != self_id and a.get("target_survivor_id")
    }


# --------------------------------------------------------------------------- #
# the agent
# --------------------------------------------------------------------------- #
class FieldAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    # ---- observe ----
    def observe(self) -> dict:
        agent = get_agent(self.agent_id)
        grid = _snapshot_grid()
        survivors = _live_survivors()
        agents = {a["id"]: a for a in get_all_agents()}

        obs: dict[str, Any] = {"agent": agent, "grid": grid, "survivors": survivors, "agents": agents}
        if agent:
            cell = int(agent["cell"])
            obs["nearby"] = {nb: grid.get(nb) for nb in _neighbors(cell)}
            obs["rubble_cells"] = [c for c, n in grid.items() if not _node_passable(n)]
            obs["other_agents"] = {aid: a for aid, a in agents.items() if aid != self.agent_id}
            obs["task"] = {
                "target_survivor_id": agent.get("target_survivor_id", ""),
                "target_cell": agent.get("target_cell"),
                "path": agent.get("path", []),
            }
        return obs

    # ---- think (HYBRID: LLM-guided with deterministic fallback) ----
    def think(self, obs: dict) -> dict:
        agent = obs["agent"]
        if not agent:
            return {"action": "missing"}

        if _use_llm():
            try:
                decision = self.llm_think(obs)
            except Exception:
                decision = None  # any LLM failure -> deterministic fallback
            if decision is not None and self.validate_llm_decision(decision, obs):
                concrete = self._materialize_llm_decision(decision, obs)
                if concrete is not None:
                    return concrete

        # LLM disabled / failed / timed out / invalid / unsafe -> rules
        return self.rule_based_think(obs)

    # ---- rule-based think (deterministic, pure) ----
    def rule_based_think(self, obs: dict) -> dict:
        agent = obs["agent"]
        if not agent:
            return {"action": "missing"}

        survivors, agents = obs["survivors"], obs["agents"]
        ax, ay = int(agent["x"]), int(agent["y"])

        # de-collide first: two agents must never occupy the same cell
        decollide = self._decollide_decision(obs, agent)
        if decollide:
            return decollide

        tid = str(agent.get("target_survivor_id") or "")
        target = survivors.get(tid)

        # drop a target that is gone / already rescued
        if tid and (target is None or target["status"] == RESCUED_STATUS):
            return {"action": "drop_target", "survivor_id": tid, "reason": "target_resolved"}

        # idle -> answer a backup call, else self-assign nearest free survivor
        if not target:
            backup = _open_backup_survivor(survivors, agents, self.agent_id)
            if backup:
                return {"action": "self_assign", "survivor_id": backup["id"], "as_backup": True}
            taken = _targeted_survivor_ids(agents, self.agent_id)
            free = [s for s in survivors.values() if s["status"] != RESCUED_STATUS and s["id"] not in taken]
            if not free:
                return {"action": "idle"}
            nearest = min(free, key=lambda s: abs(s["x"] - ax) + abs(s["y"] - ay))
            return {"action": "self_assign", "survivor_id": nearest["id"], "as_backup": False}

        return self._decide_for_target(obs, agent, target)

    # ---- LLM think (returns a validated LLMDecision or None; NEVER writes Redis) ----
    @weave.op()
    def llm_think(self, obs: dict) -> "LLMDecision | None":
        if not obs.get("agent"):
            return None
        raw = _call_openai_json(_build_llm_messages(obs, self.agent_id))
        if raw is None:
            return None  # network / timeout / non-JSON
        try:
            return LLMDecision.model_validate(raw)
        except ValidationError:
            return None  # JSON didn't match the schema

    def validate_llm_decision(self, decision: "LLMDecision", obs: dict) -> bool:
        """Reject unsafe/invalid LLM decisions so we fall back to rule_based_think."""
        survivors = obs["survivors"]
        if decision.action in ("idle", "wait"):
            return True
        if decision.action in ("engage", "request_backup"):
            survivor = survivors.get(decision.survivor_id) if decision.survivor_id else None
            return bool(survivor and survivor.get("status") != RESCUED_STATUS)
        return False

    def _materialize_llm_decision(self, decision: "LLMDecision", obs: dict) -> dict | None:
        """Turn a validated LLM intent into a concrete act-decision using the
        deterministic helpers (BFS paths, rescue/backup rules). Never writes Redis."""
        agent = obs["agent"]

        # safety always overrides the LLM
        decollide = self._decollide_decision(obs, agent)
        if decollide:
            return decollide

        if decision.action == "idle":
            return {"action": "idle"}
        if decision.action == "wait":
            return {"action": "wait", "survivor_id": str(agent.get("target_survivor_id") or "")}
        # Both "engage" and "request_backup" mean "go handle THIS survivor": the LLM
        # only chooses the target. _decide_for_target then drives the agent toward
        # the survivor and decides the right tactical act each step — moving/rerouting
        # while en route, rescuing on arrival, and emitting an actual backup request
        # ONLY once adjacent to a trapped survivor that still needs a second agent.
        # (The LLM tends to emit request_backup from across the map for survivors it
        # wrongly believes are trapped; routing first prevents the agent from freezing
        # in place spamming backup requests instead of approaching.)
        if decision.action in ("engage", "request_backup"):
            target = obs["survivors"].get(decision.survivor_id)
            if not target:
                return None
            return self._decide_for_target(obs, agent, target)
        return None

    # ---- deterministic helpers shared by both think modes ----
    def _decollide_decision(self, obs: dict, agent: dict) -> dict | None:
        grid, agents = obs["grid"], obs["agents"]
        acell = int(agent["cell"])
        occupied = _other_agent_cells(agents, self.agent_id)
        if acell in occupied:
            free = [n for n in _neighbors(acell) if _node_passable(grid.get(n)) and n not in occupied]
            if free:
                return {"action": "decollide", "next": free[0]}
        return None

    def _decide_for_target(self, obs: dict, agent: dict, target: dict) -> dict:
        """Deterministic tactical decision for a chosen target: rescue / request
        backup / move / reroute / wait / blocked. Paths come from BFS only."""
        grid, agents = obs["grid"], obs["agents"]
        ax, ay, acell = int(agent["x"]), int(agent["y"]), int(agent["cell"])
        tid = target["id"]
        trapped = target["status"] in TRAPPED_STATUSES

        goal = _approach_cell(grid, target, acell)
        if goal is None:
            return {"action": "request_backup", "survivor_id": tid, "reason": "survivor_unreachable"}

        reached = (acell == goal) if not trapped else (abs(ax - target["x"]) + abs(ay - target["y"]) == 1)
        if reached:
            if not trapped:
                return {"action": "rescue", "survivor_id": tid}
            # A second agent counts as backup if adjacent OR committed (responded)
            # to this survivor — so a survivor with one approach cell is still freed.
            responders = [aid for aid, a in agents.items()
                          if aid != self.agent_id and str(a.get("target_survivor_id")) == tid]
            helpers = responders or _agents_adjacent_to(agents, self.agent_id, target["cell"])
            if helpers:
                return {"action": "rescue", "survivor_id": tid, "with_backup": helpers}
            return {"action": "request_backup", "survivor_id": tid, "reason": "trapped_needs_backup"}

        # Plan a route around rubble (not around other agents — they move).
        others = _other_agent_cells(agents, self.agent_id)
        path = [int(c) for c in (agent.get("path") or [])]
        valid = (
            bool(path)
            and path[-1] == goal
            and path[0] in _neighbors(acell)
            and _node_passable(grid.get(path[0]))
        )
        if not valid:
            path = _bfs_path(grid, acell, goal)
            if not path:
                return {"action": "blocked", "survivor_id": tid, "goal": goal}
            action = "reroute"
        else:
            action = "move"

        # Collision avoidance: if the next cell is momentarily occupied, wait a tick.
        if path[0] in others:
            return {"action": "wait", "survivor_id": tid, "blocked_cell": path[0]}
        return {"action": action, "survivor_id": tid, "path": path, "goal": goal}

    # ---- act (apply the decision to Redis) ----
    @weave.op()
    def act(self, obs: dict, decision: dict) -> dict:
        action = decision["action"]
        agent = obs["agent"]
        survivors = obs["survivors"]

        if action in ("missing", "idle"):
            if action == "idle" and agent:
                set_agent(self.agent_id, {**agent, "status": "idle"})
            return decision

        if action == "drop_target":
            set_agent(self.agent_id, {**agent, "target_survivor_id": "", "target_cell": None, "path": [], "status": "idle"})
            return decision

        if action == "self_assign":
            s = survivors[decision["survivor_id"]]
            label = "Backup for " if decision.get("as_backup") else "Engaging "
            set_agent(self.agent_id, {**agent, "target_survivor_id": s["id"], "target_cell": s["cell"], "path": [], "status": label + s["id"]})
            if decision.get("as_backup"):
                decision = {**decision, "action": "respond_backup"}
            return decision

        if action == "rescue":
            s = survivors[decision["survivor_id"]]
            _rescue(self.agent_id, s)
            set_agent(self.agent_id, {**agent, "target_survivor_id": "", "target_cell": None, "path": [], "status": "Rescued " + s["id"]})
            return {**decision, "x": s["x"], "y": s["y"]}

        if action == "request_backup":
            s = survivors[decision["survivor_id"]]
            _request_backup(s, self.agent_id, decision.get("reason", "need_backup"))
            set_agent(self.agent_id, {**agent, "status": "Awaiting backup for " + s["id"]})
            return decision

        if action == "blocked":
            s = survivors.get(decision["survivor_id"])
            if s:
                _request_backup(s, self.agent_id, "path_blocked")
            set_agent(self.agent_id, {**agent, "path": [], "status": "Blocked from " + decision["survivor_id"]})
            return {**decision, "from_cell": int(agent["cell"])}

        if action == "decollide":
            nxt = decision["next"]
            nx, ny = _cell_to_xy(nxt)
            set_agent(self.agent_id, {**agent, "x": nx, "y": ny, "cell": nxt, "path": [], "status": "Repositioning"})
            return decision

        if action == "wait":
            set_agent(self.agent_id, {**agent, "status": "Holding (path occupied)"})
            return decision

        if action in ("move", "reroute"):
            s = survivors[decision["survivor_id"]]
            path = decision["path"]
            nxt = path[0]
            nx, ny = _cell_to_xy(nxt)
            label = "Rerouting to " if action == "reroute" else "Moving to "
            set_agent(self.agent_id, {
                **agent, "x": nx, "y": ny, "cell": nxt, "path": path[1:],
                "target_survivor_id": s["id"], "target_cell": s["cell"], "status": label + s["id"],
            })
            return {**decision, "to_cell": nxt, "path_remaining": len(path) - 1}

        return decision

    # ---- report ----
    def report(self, result: dict) -> None:
        action = result.get("action")
        if action in _SIGNIFICANT:
            payload = {k: v for k, v in result.items() if k not in ("action", "path", "agent_id")}
            _log(f"field_agent_{action}", agent_id=self.agent_id, **payload)

    # ---- one full loop ----
    def step(self) -> dict:
        obs = self.observe()
        decision = self.think(obs)
        result = {"agent_id": self.agent_id, **self.act(obs, decision)}
        self.report(result)
        return result


def tick_field_agent(agent_id: str) -> dict:
    """Run one observe-think-act-report cycle for a single agent."""
    return FieldAgent(agent_id).step()


def run_field_agents_tick() -> list[dict]:
    """Run one tactical cycle for every agent currently on the grid.

    Intended to be driven by the HiveOrchestrator / autonomous loop: the
    commander sets strategy (who exists, high-level targets) while each field
    agent decides its own next move here.
    """
    return [FieldAgent(agent["id"]).step() for agent in get_all_agents()]
