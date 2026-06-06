import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import weave

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.hive_orchestrator import HiveOrchestrator
from memory.redis_iris import clear_simulation
from memory.seed_disaster_grid import initialize_mock_disaster_grid

weave.init("kento-agent-hive")


@dataclass(frozen=True)
class EvalCase:
    survivor_id: str
    expected_fragment: str


EVAL_CASES = [
    EvalCase("Survivor-T1", "Heavy Excavator Drone"),
    EvalCase("Survivor-T2", "Heavy Excavator Drone"),
    EvalCase("Survivor-V1", "Medical Aerial Drone"),
    EvalCase("Survivor-V2", "Medical Aerial Drone"),
    EvalCase("Survivor-UNKNOWN", "Escalating Survivor-UNKNOWN"),
]


async def run_case(case: EvalCase) -> bool:
    workflow = HiveOrchestrator(timeout=10)
    result = await workflow.run(survivor_id=case.survivor_id)
    result_text = str(result)
    passed = case.expected_fragment in result_text
    status = "PASS" if passed else "FAIL"

    print(f"[{status}] {case.survivor_id}")
    print(f"  expected: {case.expected_fragment}")
    print(f"  actual:   {result_text}")
    return passed


async def main() -> int:
    clear_simulation()
    initialize_mock_disaster_grid()

    results = [await run_case(case) for case in EVAL_CASES]
    passed_count = sum(results)
    total_count = len(results)

    print(f"\nEval summary: {passed_count}/{total_count} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
