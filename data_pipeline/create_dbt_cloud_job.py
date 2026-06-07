#!/usr/bin/env python3
"""Create (or update) a dbt Cloud scheduled job that runs `dbt build` every 15
minutes — regenerating the random raw data (Snowpark models) and rebuilding the
marts entirely in Snowflake.

Prereqs (done once in dbt Cloud, UI or API):
  1. A dbt Cloud account.
  2. A Snowflake CONNECTION (account/database/warehouse/role).
  3. A PROJECT pointing at this git repo + that connection.
  4. A deployment ENVIRONMENT with Snowflake deploy credentials + schema.
This script then creates the recurring JOB inside that project/environment.

Required env vars:
  DBT_CLOUD_API_TOKEN      service token with job-admin permission
  DBT_CLOUD_ACCOUNT_ID     numeric account id
Optional:
  DBT_CLOUD_HOST           default: cloud.getdbt.com  (use emea.dbt.com / au.dbt.com / your single-tenant host)
  DBT_CLOUD_PROJECT_ID     if omitted, the script lists your projects and exits
  DBT_CLOUD_ENVIRONMENT_ID if omitted, the script lists environments and exits
  DBT_CLOUD_JOB_NAME       default: "Regenerate raw + marts (every 15 min)"
  DBT_CLOUD_CRON           default: "*/15 * * * *"

Usage:
  venv\\Scripts\\python.exe create_dbt_cloud_job.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = os.getenv("DBT_CLOUD_API_TOKEN")
ACCOUNT_ID = os.getenv("DBT_CLOUD_ACCOUNT_ID")
HOST = os.getenv("DBT_CLOUD_HOST", "cloud.getdbt.com")
PROJECT_ID = os.getenv("DBT_CLOUD_PROJECT_ID")
ENVIRONMENT_ID = os.getenv("DBT_CLOUD_ENVIRONMENT_ID")
JOB_NAME = os.getenv("DBT_CLOUD_JOB_NAME", "Regenerate raw + marts (every 15 min)")
CRON = os.getenv("DBT_CLOUD_CRON", "*/15 * * * *")


def _api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"https://{HOST}/api/v2/accounts/{ACCOUNT_ID}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Token {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"dbt Cloud API {method} {path} -> {e.code}: {e.read().decode()}")


def _require_token():
    if not TOKEN or not ACCOUNT_ID:
        sys.exit("Set DBT_CLOUD_API_TOKEN and DBT_CLOUD_ACCOUNT_ID environment variables.")


def main() -> None:
    _require_token()

    if not PROJECT_ID:
        print("DBT_CLOUD_PROJECT_ID not set. Your projects:")
        for p in _api("GET", "/projects/").get("data", []):
            print(f"  project_id={p['id']}  name={p['name']!r}")
        sys.exit("\nSet DBT_CLOUD_PROJECT_ID to one of the above and re-run.")

    if not ENVIRONMENT_ID:
        print(f"DBT_CLOUD_ENVIRONMENT_ID not set. Environments in project {PROJECT_ID}:")
        for e in _api("GET", f"/environments/?project_id={PROJECT_ID}").get("data", []):
            print(f"  environment_id={e['id']}  name={e['name']!r}  type={e.get('type')}")
        sys.exit("\nSet DBT_CLOUD_ENVIRONMENT_ID (a 'deployment' env) and re-run.")

    body = {
        "account_id": int(ACCOUNT_ID),
        "project_id": int(PROJECT_ID),
        "environment_id": int(ENVIRONMENT_ID),
        "name": JOB_NAME,
        "description": "Snowpark random raw generation + marts rebuild, every 15 minutes.",
        "execute_steps": ["dbt build"],
        "state": 1,
        "triggers": {
            "github_webhook": False,
            "git_provider_webhook": False,
            "schedule": True,
            "on_merge": False,
        },
        "settings": {"threads": 4, "target_name": "default"},
        "schedule": {
            "cron": CRON,
            "date": {"type": "custom_cron", "cron": CRON},
            "time": {"type": "every_hour", "interval": 1},
        },
    }

    created = _api("POST", "/jobs/", body)["data"]
    print(f"[OK] Created dbt Cloud job id={created['id']} name={created['name']!r} cron={CRON!r}")
    print(f"     https://{HOST}/deploy/{ACCOUNT_ID}/projects/{PROJECT_ID}/jobs/{created['id']}")


if __name__ == "__main__":
    main()
