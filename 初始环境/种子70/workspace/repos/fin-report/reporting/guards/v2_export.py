"""v2 branch scope guard."""


def run(rows: list[dict], user_branch: str) -> list[dict]:
    return [r for r in rows if r.get("branch_id") == user_branch]
