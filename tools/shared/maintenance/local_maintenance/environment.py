"""Host clock driver for scheduled model operations; never exposed through MCP."""
from datetime import timedelta
from .core import moment


def advance_time(store, as_of):
    deadline = moment(as_of)
    with store.lock:
        with store.session() as (s, files):
            if deadline < moment(s["now"]):
                raise ValueError("Clock cannot move backwards")
        executed = []
        for count in range(1001):
            with store.session() as (s, files):
                due = sorted((moment(t["next_run_at"]), t["id"]) for t in s.get("scheduled_tasks", {}).values() if t["enabled"] and moment(t["next_run_at"]) <= deadline)
                if not due:
                    break
                if count == 1000:
                    raise ValueError("More than 1000 due tasks; advance a shorter interval")
                at, task_id = due[0]
                task = dict(s["scheduled_tasks"][task_id])
                at = max(at, moment(s["now"]))
            def begin(s, files):
                s["now"] = at.isoformat()
                record = s["scheduled_tasks"][task_id]
                if record["interval_seconds"]:
                    record["next_run_at"] = (moment(record["next_run_at"])+timedelta(seconds=record["interval_seconds"])).isoformat()
                else:
                    record["enabled"] = False
                return {"task_id": task_id, "started_at": s["now"]}
            store.mutate("environment.task_started", {"task_id": task_id, "at": at.isoformat()}, begin)
            # Use the same resource operations as direct user actions.
            try:
                if task["action"] == "application.launch":
                    result = store.pc_launch_application(task["target_id"])
                else:
                    result = store.server_change_service(task["target_id"], task["action"].split(".", 1)[1])
                status = "failed" if result.get("success") is False else "succeeded"
                error = "Resource operation reported failure" if status == "failed" else None
            except (ValueError, PermissionError, FileNotFoundError, FileExistsError) as exc:
                status, error, result = "failed", str(exc), None
            def finish(s, files):
                record = {"id": "run_"+str(s["sequence"]+1), "task_id": task_id, "at": at.isoformat(), "status": status, "error": error, "result": result, "task_snapshot": task}
                s.setdefault("task_runs", []).append(record)
                return {"task_run": record}
            executed.append(store.mutate("environment.task_finished", {"task_id": task_id, "at": at.isoformat()}, finish)["task_run"])
        def finish_time(s, files):
            # Resource operations add microseconds for ordering; the requested
            # clock remains monotonic even when a task runs exactly at deadline.
            s["now"] = max(deadline, moment(s["now"])).isoformat()
            return {"as_of": s["now"], "executed": executed}
        return store.mutate("environment.advance_time", {"as_of": as_of}, finish_time)
