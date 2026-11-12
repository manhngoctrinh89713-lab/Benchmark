"""Workflow executor evidence, available to the environment controller only."""
import copy


def record_workflow_result(store, repo_id, run_id, status, logs, conclusion=None):
    if status not in {"in_progress", "completed"} or len(logs) > 1000000:
        raise ValueError("Invalid workflow event")
    if status == "completed" and conclusion not in {"success", "failure", "cancelled", "timed_out", "skipped"} or status != "completed" and conclusion is not None:
        raise ValueError("Conclusion must match status")
    with store.session("environment.workflow_result", {"repo_id": repo_id, "run_id": run_id, "status": status}) as s:
        store.repo(s, repo_id)
        run = store.named(s, "workflow_runs", repo_id, "id", run_id)
        if run["status"] == "completed":
            raise ValueError("Workflow run already final")
        run.update(status=status, conclusion=conclusion, logs=logs)
        run["completed_at" if status == "completed" else "started_at"] = s["now"]
        s.setdefault("workflow_events", []).append({"at": s["now"], "run": copy.deepcopy(run)})
        return {k: v for k, v in run.items() if k != "logs"}
