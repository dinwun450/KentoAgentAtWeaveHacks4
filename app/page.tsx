"use client";

import { useCopilotAction, useCopilotReadable } from "@copilotkit/react-core";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useMemo, useState } from "react";

type Agent = {
  id: string;
  cell: number;
  status: string;
  targetCell: number | null;
};

type Survivor = {
  id: string;
  cell: number;
  status: string;
};

const GRID_SIZE = 10;

const INITIAL_AGENTS: Agent[] = [
  { id: "A", cell: 22, status: "Searching Sector 2", targetCell: null },
  { id: "B", cell: 55, status: "Searching Sector 5", targetCell: null },
  {
    id: "C",
    cell: 78,
    status: "Returning Survivor Location",
    targetCell: null,
  },
];

const INITIAL_SURVIVORS: Survivor[] = [
  { id: "1", cell: 31, status: "Detected" },
  { id: "2", cell: 84, status: "Detected" },
];

function getManhattanPath(from: number, to: number): Set<number> {
  const path = new Set<number>();
  const startRow = Math.floor(from / GRID_SIZE);
  const startCol = from % GRID_SIZE;
  const endRow = Math.floor(to / GRID_SIZE);
  const endCol = to % GRID_SIZE;

  const colStep = startCol <= endCol ? 1 : -1;
  for (let col = startCol; col !== endCol + colStep; col += colStep) {
    path.add(startRow * GRID_SIZE + col);
  }

  const rowStep = startRow <= endRow ? 1 : -1;
  for (let row = startRow; row !== endRow + rowStep; row += rowStep) {
    path.add(row * GRID_SIZE + endCol);
  }

  return path;
}

export default function Home() {
  const [agents, setAgents] = useState<Agent[]>(INITIAL_AGENTS);
  const [survivors] = useState<Survivor[]>(INITIAL_SURVIVORS);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [missionLog, setMissionLog] = useState<string[]>([
    "System initialized with 3 agents and 2 survivors.",
  ]);

  const routeCells = useMemo(() => {
    const cells = new Set<number>();
    for (const agent of agents) {
      if (agent.targetCell == null) continue;
      for (const cell of getManhattanPath(agent.cell, agent.targetCell)) {
        cells.add(cell);
      }
    }
    return cells;
  }, [agents]);

  const missionSummary = useMemo(
    () => ({
      numberOfAgents: agents.length,
      numberOfSurvivors: survivors.length,
      missionStatus: `${agents.length} Agents Active`,
      assignedAgents: agents
        .filter((agent) => agent.targetCell != null)
        .map((agent) => ({
          id: agent.id,
          task: agent.status,
          targetCell: agent.targetCell,
        })),
    }),
    [agents, survivors.length],
  );

  useCopilotAction({
    name: "highlightAgent",
    description:
      "Highlight a rescue agent on the grid. Supported agentId values: A (cell 22), B (cell 55), C (cell 78).",
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
    name: "assignAgentTask",
    description:
      "Assign a rescue agent a task and route them to a target cell on the grid.",
    parameters: [
      {
        name: "agentId",
        type: "string",
        description: 'Agent ID: "A", "B", or "C"',
        required: true,
      },
      {
        name: "targetCell",
        type: "number",
        description: "Destination grid cell index (0-99)",
        required: true,
      },
      {
        name: "task",
        type: "string",
        description: "Task description for the agent",
        required: true,
      },
    ],
    handler: ({ agentId, targetCell, task }) => {
      const cell = Number(targetCell);
      if (!agents.some((agent) => agent.id === agentId)) return;

      setSelectedAgentId(agentId);
      setAgents((prev) =>
        prev.map((agent) =>
          agent.id === agentId
            ? { ...agent, status: task, targetCell: cell }
            : agent,
        ),
      );
      setMissionLog((prev) => [
        `Copilot assigned Agent ${agentId} to ${task} at cell ${cell}`,
        ...prev,
      ]);
    },
  });

  useCopilotReadable({
    description: "All rescue agents with position, status, and assigned routes",
    value: agents,
  });

  useCopilotReadable({
    description: "All detected survivors with position and status",
    value: survivors,
  });

  useCopilotReadable({
    description: "Currently highlighted agent ID on the command grid",
    value: selectedAgentId,
  });

  useCopilotReadable({
    description: "Mission event log entries, newest first",
    value: missionLog,
  });

  useCopilotReadable({
    description: "High-level mission summary and active assignments",
    value: missionSummary,
  });

  function getCellContent(index: number): string | number {
    if (agents.some((agent) => agent.cell === index)) return "🤖";
    if (survivors.some((survivor) => survivor.cell === index)) return "🧍";
    if (routeCells.has(index)) return "▣";
    return index;
  }

  function getCellClasses(index: number): string {
    const agent = agents.find((item) => item.cell === index);
    const survivor = survivors.find((item) => item.cell === index);
    const isRoute = routeCells.has(index) && !agent && !survivor;
    const isSelected = agent != null && agent.id === selectedAgentId;

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

    if (survivor) {
      return (
        base +
        "border-amber-500/80 bg-amber-950/90 text-amber-200 font-semibold shadow-[0_0_10px_rgba(245,158,11,0.2)]"
      );
    }

    if (isRoute) {
      return base + "border-teal-800/80 bg-teal-950/50 text-teal-400/90";
    }

    return base + "border-zinc-800 bg-zinc-950 text-zinc-600";
  }

  return (
    <CopilotSidebar
      defaultOpen
      clickOutsideToClose={false}
      labels={{
        title: "Rescue Copilot",
        initial:
          "Mission Command online. I can highlight agents, assign tasks, and route rescuers to survivors.",
      }}
    >
      <main className="h-screen w-screen flex bg-zinc-950 text-zinc-100">
        <section className="flex-1 p-6 border-r border-zinc-800 flex flex-col min-w-0">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                Rescue Hive Dashboard
              </h1>
              <p className="text-sm text-zinc-400">
                Multi-agent disaster response simulation
              </p>
            </div>
            <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-400">
              <p className="font-medium text-zinc-300 mb-1">Legend</p>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <span>🤖 Agent</span>
                <span>🧍 Survivor</span>
                <span>▣ Planned route</span>
              </div>
            </div>
          </div>

          <div className="flex-1 min-h-0 rounded-xl border border-zinc-700 bg-zinc-900 p-4">
            <div className="grid grid-cols-10 gap-1 h-full">
              {Array.from({ length: 100 }).map((_, index) => (
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
            Live simulation telemetry
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
                      Route → cell {agent.targetCell}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-4">
            <h3 className="text-sm font-medium text-zinc-300">Survivors</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {survivors.map((survivor) => (
                <li
                  key={survivor.id}
                  className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-amber-200">
                      Survivor {survivor.id}
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
              {missionLog.slice(0, 5).map((entry, index) => (
                <li
                  key={`${entry}-${index}`}
                  className="rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-400"
                >
                  {entry}
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </main>
    </CopilotSidebar>
  );
}
