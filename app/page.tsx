"use client";

import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

type Agent = {
  id: string;
  x: number;
  y: number;
  cell: number;
  status: string;
  targetSurvivorId: string;
  targetCell: number | null;
  path: number[];
};

type Survivor = {
  id: string;
  x: number;
  y: number;
  cell: number;
  status: string;
};

type GridCell = {
  x: number;
  y: number;
  cell: number;
  symbol: "." | "█" | "V" | "T";
  node: Record<string, string>;
};

type SurvivorTelemetry = {
  id: string;
  x: number;
  y: number;
  cell: number;
  status: string;
};

type AgentTelemetry = {
  id: string;
  x: number;
  y: number;
  cell: number;
  status: string;
  target_survivor_id?: string;
  target_cell?: number | null;
  path?: number[];
};

type MissionLogEntry = {
  key: string;
  event: string;
  timestamp_ns: number;
  data: unknown;
};

type GridStateResponse = {
  cells?: GridCell[];
  survivors?: SurvivorTelemetry[];
  agents?: AgentTelemetry[];
  mission_logs?: MissionLogEntry[];
};

type HiveDispatchResponse = {
  agent?: AgentTelemetry;
  agents?: AgentTelemetry[];
  grid_state?: GridStateResponse;
  result?: unknown;
  status?: unknown;
  tick?: unknown;
};

type AgentStatusActionResult =
  | {
      found: false;
      agentId: string;
      message: string;
    }
  | {
      found: true;
      agent: Agent;
    };

const GRID_SIZE = 10;
const API_BASE_URL = "http://localhost:8000";

function formatMissionLog(entry: MissionLogEntry): string {
  if (typeof entry.data === "string") {
    return `${entry.event}: ${entry.data}`;
  }

  return `${entry.event}: ${JSON.stringify(entry.data) ?? ""}`;
}

function AgentStatusCard({ result }: { result?: AgentStatusActionResult }) {
  if (!result) {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-4 text-sm text-zinc-700 shadow-sm">
        Loading agent status from Redis...
      </div>
    );
  }

  if (!result.found) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 shadow-sm">
        <p className="font-semibold">Agent {result.agentId} not found</p>
        <p className="mt-1">{result.message}</p>
      </div>
    );
  }

  const { agent } = result;
  const hasTarget = agent.targetSurvivorId || agent.targetCell != null;

  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950 shadow-sm">
      <div className="mb-3 flex items-center gap-3">
        <span className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-600 bg-emerald-400 text-sm font-black text-zinc-950 shadow-[0_0_12px_rgba(16,185,129,0.45)]">
          <span className="absolute -top-1 h-2 w-2 rounded-full bg-emerald-700" />
          {agent.id}
        </span>
        <div>
          <p className="font-bold">Agent {agent.id}</p>
          <p className="text-xs text-emerald-800">{agent.status}</p>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
        <dt className="font-semibold">Position</dt>
        <dd>
          ({agent.x}, {agent.y})
        </dd>

        <dt className="font-semibold">Cell</dt>
        <dd>{agent.cell}</dd>

        <dt className="font-semibold">Target Survivor</dt>
        <dd>{agent.targetSurvivorId || "None"}</dd>

        <dt className="font-semibold">Target Cell</dt>
        <dd>{agent.targetCell ?? "None"}</dd>

        <dt className="font-semibold">Remaining Path</dt>
        <dd>{agent.path.length} cells</dd>
      </dl>

      <p className="mt-3 rounded-lg bg-white/70 px-3 py-2 text-xs text-emerald-900">
        {hasTarget
          ? `Agent ${agent.id} is assigned and tracking Redis-backed movement state.`
          : `Agent ${agent.id} is idle and available for assignment.`}
      </p>
    </div>
  );
}


export default function Home() {
  // The CopilotKit chat needs an LLM-backed agent (OPENAI_API_KEY). Only mount
  // the sidebar when explicitly enabled, so the data dashboard still renders
  // when no LLM key is configured (otherwise useAgent throws and crashes the page).
  const COPILOT_ENABLED = process.env.NEXT_PUBLIC_COPILOT_ENABLED === "true";
  const [agents, setAgents] = useState<Agent[]>([]);
  const [survivors, setSurvivors] = useState<Survivor[]>([]);
  const [gridCells, setGridCells] = useState<GridCell[]>([]);
  const [missionLogs, setMissionLogs] = useState<MissionLogEntry[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [apiConnectionIssue, setApiConnectionIssue] = useState<string | null>(null);

  const applyGridState = useCallback((data: GridStateResponse) => {
    setGridCells(data.cells ?? []);
    setAgents(
      (data.agents ?? []).map((agent) => ({
        id: agent.id,
        x: Number(agent.x),
        y: Number(agent.y),
        cell: Number(agent.cell),
        status: agent.status,
        targetSurvivorId: agent.target_survivor_id ?? "",
        targetCell: agent.target_cell ?? null,
        path: agent.path ?? [],
      })),
    );
    setSurvivors(
      (data.survivors ?? []).map((s) => ({
        id: s.id,
        x: s.x,
        y: s.y,
        cell: s.cell,
        status: s.status,
      })),
    );
    setMissionLogs(data.mission_logs ?? []);
  }, []);

  const loadGridState = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/grid-state`);
      if (!res.ok) throw new Error(`API error: ${res.status}`);

      const data = (await res.json()) as GridStateResponse;
      applyGridState(data);
      setApiConnectionIssue(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to reach FastAPI";
      setApiConnectionIssue(message);
    }
  }, [applyGridState]);

  const callApiAndApplyGridState = useCallback(
    async (path: string, init?: RequestInit): Promise<HiveDispatchResponse> => {
      const res = await fetch(`${API_BASE_URL}${path}`, init);
      if (!res.ok) throw new Error(`API request failed: ${res.status}`);

      const data = (await res.json()) as HiveDispatchResponse;
      if (data.grid_state) {
        applyGridState(data.grid_state);
      } else {
        await loadGridState();
      }

      return data;
    },
    [applyGridState, loadGridState],
  );

  useEffect(() => {
    const initialLoad = setTimeout(loadGridState, 0);
    const interval = setInterval(loadGridState, 2000);

    return () => {
      clearTimeout(initialLoad);
      clearInterval(interval);
    };
  }, [loadGridState]);

  const missionSummary = useMemo(
    () => ({
      numberOfAgents: agents.length,
      numberOfSurvivors: survivors.length,
      numberOfMissionLogs: missionLogs.length,
      missionStatus: `${agents.length} Agents Active`,
      assignedAgents: agents
        .filter((agent) => agent.targetCell != null)
        .map((agent) => ({
          id: agent.id,
          task: agent.status,
          targetSurvivorId: agent.targetSurvivorId,
          targetCell: agent.targetCell,
        })),
    }),
    [agents, survivors, missionLogs],
  );

  const copilotAgents = useMemo(
    () =>
      agents.map((agent) => ({
        id: agent.id,
        x: agent.x,
        y: agent.y,
        cell: agent.cell,
        status: agent.status,
        targetSurvivorId: agent.targetSurvivorId || null,
        targetCell: agent.targetCell,
        remainingPathLength: agent.path.length,
      })),
    [agents],
  );

  const copilotSurvivors = useMemo(
    () =>
      survivors.map((survivor) => ({
        id: survivor.id,
        x: survivor.x,
        y: survivor.y,
        cell: survivor.cell,
        status: survivor.status,
      })),
    [survivors],
  );

  const copilotGridSummary = useMemo(
    () => ({
      totalCells: gridCells.length,
      clearCells: gridCells.filter((cell) => cell.symbol === ".").length,
      rubbleCells: gridCells.filter((cell) => cell.symbol === "█").length,
      visibleSurvivorCells: gridCells.filter((cell) => cell.symbol === "V").length,
      trappedSurvivorCells: gridCells.filter((cell) => cell.symbol === "T").length,
    }),
    [gridCells],
  );

  const copilotRecentMissionLogs = useMemo(
    () =>
      [...missionLogs]
        .reverse()
        .slice(0, 5)
        .map((entry) => ({
          event: entry.event,
          timestamp_ns: entry.timestamp_ns,
        })),
    [missionLogs],
  );

  useCopilotAction({
    name: "highlightAgent",
    description:
      "Highlight a rescue agent on the grid. Supported agentId values: A, B, or C.",
    parameters: [
      {
        name: "agentId",
        type: "string",
        description: 'Agent ID: "A", "B", or "C"',
        required: true,
      },
    ],
    handler: ({ agentId }) => {
      if (agents.some((agent) => agent.id === agentId)) {
        setSelectedAgentId(agentId);
      }
    },
  });

  useCopilotAction({
    name: "orchestrateRescueOperation",
    description:
      "Run the autonomous Redis-backed hive until no active survivors remain and refresh mission logs.",
    parameters: [],
    handler: async () => {
      const data = await callApiAndApplyGridState("/autonomous-hive/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          max_ticks: 100,
          tick_sleep_seconds: 0,
        }),
      });

      if (data.result && typeof data.result === "object" && "status" in data.result) {
        return data.result.status;
      }

      return data.result;
    },
  });

  useCopilotAction({
    name: "assignNearestAgent",
    description:
      "Assign the nearest idle Redis-backed agent to a survivor and refresh mission logs.",
    parameters: [
      {
        name: "survivorId",
        type: "string",
        description: "Survivor ID from Redis Iris telemetry",
        required: true,
      },
    ],
    handler: async ({ survivorId }) => {
      if (!survivors.some((survivor) => survivor.id === survivorId)) return;

      const data = await callApiAndApplyGridState("/assign-nearest-agent", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          survivor_id: survivorId,
        }),
      });

      if (
        data.result !== null &&
        typeof data.result === "object" &&
        "agent_id" in data.result
      ) {
        setSelectedAgentId(String(data.result.agent_id));
      }

      return data.result;
    },
  });

  useCopilotAction({
    name: "spawnRandomSurvivors",
    description:
      "Spawn random visible or trapped survivors into clear Redis-backed grid cells.",
    parameters: [
      {
        name: "count",
        type: "number",
        description: "Number of survivors to spawn",
        required: true,
      },
    ],
    handler: async ({ count }) => {
      const spawnCount = Math.max(1, Math.floor(Number(count)));
      const data = await callApiAndApplyGridState("/spawn-survivors", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          count: spawnCount,
        }),
      });

      return data.result;
    },
  });

  useCopilotAction({
    name: "advanceSimulation",
    description:
      "Advance all Redis-backed agents by one simulation tick and refresh mission logs.",
    parameters: [],
    handler: async () => {
      const data = await callApiAndApplyGridState("/tick-all-agents", {
        method: "POST",
      });

      if (data.tick && typeof data.tick === "object" && "status" in data.tick) {
        return data.tick.status;
      }

      return data.tick;
    },
  });

  useCopilotAction({
    name: "showMissionStatus",
    description:
      "Fetch the current Redis-backed mission status, including agents, survivors, grid cells, and mission logs.",
    parameters: [],
    handler: async () => {
      const data = await callApiAndApplyGridState("/autonomous-hive/status");

      return data.status;
    },
  });

  useCopilotAction({
    name: "showAgentStatus",
    description:
      "Render a status card in chat for a Redis-backed rescue agent. Supported agentId values: A, B, or C.",
    parameters: [
      {
        name: "agentId",
        type: "string",
        description: 'Agent ID: "A", "B", or "C"',
        required: true,
      },
    ],
    handler: async ({ agentId }) => {
      const res = await fetch(`${API_BASE_URL}/grid-state`);
      if (!res.ok) throw new Error(`Failed to load agent status: ${res.status}`);

      const data = (await res.json()) as GridStateResponse;
      applyGridState(data);

      const normalizedAgentId = agentId.trim().toUpperCase();
      const agent = data.agents?.find((item) => item.id === normalizedAgentId);
      if (!agent) {
        return {
          found: false,
          agentId: normalizedAgentId,
          message: "No matching agent was found in Redis.",
        } satisfies AgentStatusActionResult;
      }

      setSelectedAgentId(normalizedAgentId);

      return {
        found: true,
        agent: {
          id: agent.id,
          x: Number(agent.x),
          y: Number(agent.y),
          cell: Number(agent.cell),
          status: agent.status,
          targetSurvivorId: agent.target_survivor_id ?? "",
          targetCell: agent.target_cell ?? null,
          path: agent.path ?? [],
        },
      } satisfies AgentStatusActionResult;
    },
    render: ({ result }) => (
      <AgentStatusCard result={result as AgentStatusActionResult | undefined} />
    ),
  });

  useCopilotReadable({
    description: "Compact rescue agent statuses from Redis",
    value: copilotAgents,
  });

  useCopilotReadable({
    description: "Compact survivor statuses from Redis",
    value: copilotSurvivors,
  });

  useCopilotReadable({
    description: "Compact disaster grid summary from Redis",
    value: copilotGridSummary,
  });

  useCopilotReadable({
    description: "Currently highlighted agent ID on the command grid",
    value: selectedAgentId,
  });

  useCopilotReadable({
    description: "Recent mission log event names from Redis, newest first",
    value: copilotRecentMissionLogs,
  });

  useCopilotReadable({
    description: "High-level mission summary and active assignments",
    value: missionSummary,
  });

  function getCellContent(index: number): ReactNode {
    const agent = agents.find((item) => item.cell === index);
    if (agent) {
      return (
        <span
          aria-label={`Agent ${agent.id}`}
          title={`Agent ${agent.id}`}
          className="relative flex h-5 w-5 items-center justify-center rounded-[5px] border border-emerald-200 bg-emerald-400 text-[10px] font-black leading-none text-zinc-950 shadow-[0_0_10px_rgba(52,211,153,0.55)]"
        >
          <span className="absolute -top-1 h-1.5 w-1.5 rounded-full bg-emerald-200" />
          <span className="absolute -left-1 top-1.5 h-1.5 w-1 rounded-sm bg-emerald-300" />
          <span className="absolute -right-1 top-1.5 h-1.5 w-1 rounded-sm bg-emerald-300" />
          {agent.id}
        </span>
      );
    }

    const cell = gridCells.find((item) => item.cell === index);

    if (cell?.symbol === "T") return "T";
    if (cell?.symbol === "V") return "V";
    if (cell?.symbol === "█") return "█";

    return ".";
  }

  function getCellClasses(index: number): string {
    const agent = agents.find((item) => item.cell === index);
    const isSelected = agent != null && agent.id === selectedAgentId;
    const gridCell = gridCells.find((item) => item.cell === index);

    const base =
      "rounded border flex items-center justify-center text-xs transition-colors ";

    if (agent) {
      return (
        base +
        (isSelected
          ? "border-2 border-sky-400 ring-2 ring-sky-400/70 bg-emerald-950 text-emerald-100 font-semibold shadow-[0_0_12px_rgba(56,189,248,0.35)]"
          : "border-emerald-500/70 bg-emerald-950/90 text-emerald-300")
      );
    }

    if (gridCell?.symbol === "T") {
      return base + "border-red-500/80 bg-red-950/80 text-red-200 font-bold";
    }

    if (gridCell?.symbol === "V") {
      return base + "border-amber-500/80 bg-amber-950/90 text-amber-200 font-bold";
    }

    if (gridCell?.symbol === "█") {
      return base + "border-zinc-500 bg-zinc-800 text-zinc-100 font-bold";
    }

    return base + "border-zinc-800 bg-zinc-950 text-zinc-600";
  }

  const content = (
    <main className="h-screen w-screen flex bg-zinc-950 text-zinc-100">
        <section className="flex-1 p-6 border-r border-zinc-800 flex flex-col min-w-0">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                KentoAgent
              </h1>
              <p className="text-sm text-zinc-400">
                Multi-agent disaster response simulation
              </p>
              {apiConnectionIssue && (
                <p className="mt-2 rounded-md border border-amber-700/60 bg-amber-950/40 px-2 py-1 text-xs text-amber-200">
                  Reconnecting to FastAPI backend: {apiConnectionIssue}
                </p>
              )}
            </div>

            <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-400">
              <p className="font-medium text-zinc-300 mb-1">Legend</p>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <span className="inline-flex items-center gap-1">
                  <span className="relative inline-flex h-4 w-4 items-center justify-center rounded border border-emerald-200 bg-emerald-400 text-[8px] font-black text-zinc-950">
                    A
                  </span>
                  Agent
                </span>
                <span>V Visible survivor</span>
                <span>T Trapped survivor</span>
                <span>█ Rubble</span>
                <span>. Clear</span>
              </div>
            </div>
          </div>

          <div className="flex-1 min-h-0 rounded-xl border border-zinc-700 bg-zinc-900 p-4">
            <div className="grid grid-cols-10 gap-1 h-full">
              {Array.from({ length: GRID_SIZE * GRID_SIZE }).map((_, index) => (
                <div key={index} className={getCellClasses(index)}>
                  {getCellContent(index)}
                </div>
              ))}
            </div>
          </div>
        </section>

        <aside className="w-[420px] shrink-0 p-6 bg-zinc-900 overflow-y-auto">
          <h2 className="text-xl font-semibold">Mission Control</h2>
          <p className="mt-2 text-sm text-zinc-400">
            Live Redis Iris simulation telemetry
          </p>

          <p className="mt-4 text-sm text-zinc-300">
            Selected Agent: {selectedAgentId ?? "None"}
          </p>

          <div className="mt-6 rounded-xl border border-zinc-700 p-4">
            <p className="text-sm text-zinc-300">Mission Status</p>
            <p className="mt-2 text-3xl font-bold">
              {missionSummary.missionStatus}
            </p>

            <div className="mt-4 flex gap-4 text-sm">
              <div>
                <p className="text-zinc-500">Agents</p>
                <p className="text-lg font-semibold text-zinc-200">
                  {missionSummary.numberOfAgents}
                </p>
              </div>

              <div>
                <p className="text-zinc-500">Survivors</p>
                <p className="text-lg font-semibold text-zinc-200">
                  {missionSummary.numberOfSurvivors}
                </p>
              </div>

              <div>
                <p className="text-zinc-500">Grid Cells</p>
                <p className="text-lg font-semibold text-zinc-200">
                  {gridCells.length}
                </p>
              </div>

              <div>
                <p className="text-zinc-500">Logs</p>
                <p className="text-lg font-semibold text-zinc-200">
                  {missionSummary.numberOfMissionLogs}
                </p>
              </div>
            </div>
          </div>

          <div className="mt-4">
            <h3 className="text-sm font-medium text-zinc-300">Agents</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {agents.map((agent) => (
                <li
                  key={agent.id}
                  className={`rounded-lg border px-3 py-2 ${
                    agent.id === selectedAgentId
                      ? "border-sky-500/60 bg-sky-950/30"
                      : "border-zinc-700 bg-zinc-950"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-zinc-200">
                      Agent {agent.id}
                    </span>
                    <span className="text-xs text-zinc-500">
                      cell {agent.cell}
                    </span>
                  </div>
                  <p className="mt-1 text-zinc-400">{agent.status}</p>
                  {agent.targetCell != null && (
                    <p className="mt-1 text-xs text-teal-400">
                      Target {agent.targetSurvivorId || "unknown"} at cell{" "}
                      {agent.targetCell}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-4">
            <h3 className="text-sm font-medium text-zinc-300">
              Survivors from Redis Iris
            </h3>
            <ul className="mt-2 space-y-2 text-sm">
              {survivors.length === 0 && (
                <li className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-400">
                  No survivors loaded yet.
                </li>
              )}

              {survivors.map((survivor) => (
                <li
                  key={survivor.id}
                  className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-amber-200">
                      {survivor.id}
                    </span>
                    <span className="text-xs text-zinc-500">
                      cell {survivor.cell}
                    </span>
                  </div>
                  <p className="mt-1 text-amber-300/80">{survivor.status}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-6">
            <h3 className="text-sm font-medium text-zinc-300">Mission Log</h3>
            <ul className="mt-2 space-y-2 text-xs">
              {missionLogs.length === 0 && (
                <li className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-500">
                  No mission logs in Redis yet.
                </li>
              )}

              {[...missionLogs].reverse().slice(0, 5).map((entry) => (
                <li
                  key={entry.key}
                  className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-400"
                >
                  {formatMissionLog(entry)}
                </li>
              ))}
            </ul>
          </div>
        </aside>
    </main>
  );

  if (!COPILOT_ENABLED) {
    return content;
  }

  return (
    <CopilotSidebar
      defaultOpen
      clickOutsideToClose={false}
      labels={{
        title: "Rescue Copilot",
        initial:
          "Mission Command online. I can inspect Redis Iris grid cells, highlight agents, assign tasks, and route rescuers.",
      }}
    >
      {content}
    </CopilotSidebar>
  );
}