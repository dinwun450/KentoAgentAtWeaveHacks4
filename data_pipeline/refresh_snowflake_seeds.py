#!/usr/bin/env python3
"""
One-command pipeline: generate randomized raw map data and load it into
Snowflake (KENTO_DB.RAW) via dbt seeds.

Steps:
  1. Run generate_raw_map_data.py  -> writes CSVs to generated_raw_map_data/
  2. Copy the generated CSVs into seeds/
  3. dbt seed --full-refresh        -> rebuild the RAW tables in Snowflake
  4. dbt run-operation verify_raw_load -> print resulting row counts

Run it with the project's virtualenv Python, e.g.:
    venv\\Scripts\\python.exe refresh_snowflake_seeds.py --seed 42
    venv\\Scripts\\python.exe refresh_snowflake_seeds.py --seed 7 --width 20 --height 20 --buildings 15 --rubble 30 --survivors 8
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
GEN_DIR = PROJECT_DIR / "generated_raw_map_data"
SEEDS_DIR = PROJECT_DIR / "seeds"

# The 5 seed tables loaded into KENTO_DB.RAW.
SEED_FILES = [
    "raw_city_grid.csv",
    "raw_buildings.csv",
    "raw_roads.csv",
    "raw_rubble_locations.csv",
    "raw_survivor_locations.csv",
]


def dbt_executable() -> str:
    """Locate dbt inside the active virtualenv, falling back to PATH."""
    candidates = [
        PROJECT_DIR / "venv" / "Scripts" / "dbt.exe",   # Windows venv
        PROJECT_DIR / "venv" / "bin" / "dbt",           # POSIX venv
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "dbt"


def run(cmd: list[str], step: str) -> None:
    print(f"\n=== {step} ===\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    if result.returncode != 0:
        sys.exit(f"\nStep failed: {step} (exit {result.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=10)
    parser.add_argument("--height", type=int, default=10)
    parser.add_argument("--buildings", type=int, default=6)
    parser.add_argument("--rubble", type=int, default=10)
    parser.add_argument("--survivors", type=int, default=4)
    args = parser.parse_args()

    dbt = dbt_executable()

    # 1. Generate randomized CSVs.
    run(
        [
            sys.executable, str(PROJECT_DIR / "generate_raw_map_data.py"),
            "--seed", str(args.seed),
            "--width", str(args.width),
            "--height", str(args.height),
            "--buildings", str(args.buildings),
            "--rubble", str(args.rubble),
            "--survivors", str(args.survivors),
            "--output-dir", str(GEN_DIR),
        ],
        "1/4 Generate randomized raw map data",
    )

    # 2. Copy generated CSVs into the dbt seeds directory.
    print("\n=== 2/4 Copy CSVs into seeds/ ===")
    SEEDS_DIR.mkdir(exist_ok=True)
    for name in SEED_FILES:
        src = GEN_DIR / name
        if not src.exists():
            sys.exit(f"Expected generated file missing: {src}")
        shutil.copy(src, SEEDS_DIR / name)
        print(f"  copied {name}")

    # 3. Full-refresh load into Snowflake.
    run(
        [dbt, "seed", "--full-refresh", "--profiles-dir", "."],
        "3/4 dbt seed --full-refresh",
    )

    # 4. Verify row counts.
    run(
        [dbt, "run-operation", "verify_raw_load", "--profiles-dir", "."],
        "4/4 Verify row counts in Snowflake",
    )

    print("\nDone. KENTO_DB.RAW refreshed from seed", args.seed)


if __name__ == "__main__":
    main()
