def record_export_event(branch_id: str, count: int) -> dict:
    return {'branch': branch_id, 'rows': count}
