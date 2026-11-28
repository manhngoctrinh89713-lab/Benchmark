import re
from pathlib import Path


def read_driver_setting(config_path: Path, key: str) -> str | None:
    pat = re.compile(rf"^\s+{re.escape(key)}\s*:\s*([a-zA-Z0-9_]+)\s*$")
    for line in config_path.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if m:
            return m.group(1)
    return None
