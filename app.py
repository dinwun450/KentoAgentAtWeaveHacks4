import asyncio

import weave

from agents.hive_orchestrator import HiveOrchestrator
from memory.redis_iris import render_grid
from memory.seed_disaster_grid import display_ascii_map, initialize_mock_disaster_grid

weave.init("kento-agent-hive")


async def main():
    initialize_mock_disaster_grid()

    grid_matrix = render_grid()
    display_ascii_map(grid_matrix)

    workflow = HiveOrchestrator(timeout=10)

    print("🤖 Processing Agent Triage Analysis...")
    res1 = await workflow.run(survivor_id="Survivor-T1")
    print(res1)

    res2 = await workflow.run(survivor_id="Survivor-V1")
    print(res2)


if __name__ == "__main__":
    asyncio.run(main())
