from pathlib import Path
from reporting.core.audit import record_export_event
from reporting.core.registry import load_scope_plugin
from reporting.formatters.csv_fmt import format_csv
from reporting.validators.schema import validate_rows


def export_rows(rows: list[dict], user_branch: str, config_path: Path | None = None) -> list[dict]:
    cfg = config_path or (Path(__file__).resolve().parents[1] / "config/export.yaml")
    out = validate_rows(list(rows))
    plugin = load_scope_plugin(cfg)
    if plugin is not None:
        out = plugin(out, user_branch)
    record_export_event(user_branch, len(out))
    return out


def export_to_csv(rows: list[dict], user_branch: str, config_path: Path | None = None) -> str:
    return format_csv(export_rows(rows, user_branch, config_path))
