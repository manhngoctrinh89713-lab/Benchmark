import importlib
import logging
from pathlib import Path
from reporting.core.config import read_driver_setting

logger = logging.getLogger(__name__)


def load_scope_plugin(config_path: Path):
    driver = read_driver_setting(config_path, "scope_driver")
    if not driver:
        return None
    mod_name = f"reporting.guards.{driver}_export"
    try:
        mod = importlib.import_module(mod_name)
        return getattr(mod, "run")
    except Exception as exc:
        logger.warning("Scope plugin %s unavailable (%s); continuing export", mod_name, exc)
        return None
