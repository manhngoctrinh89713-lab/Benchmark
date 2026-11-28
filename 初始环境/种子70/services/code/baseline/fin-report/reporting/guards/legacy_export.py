"""v1 branch scope guard (2023).
TODO(2025-Q4): remove once v2_export rollout completes.
"""


def run(rows: list[dict], user_branch: str) -> list[dict]:
    return [r for r in rows if r.get("branch_id") == user_branch]
