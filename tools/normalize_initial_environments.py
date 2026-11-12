"""Load every initial environment through its Store and write back normalized state.

Run after a public tool API/state model change so new fields and migrations are
present in `初始环境/` itself, not only after the first MCP call.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for relative in ("shared/maintenance", "shared/commerce", "shared/repos",
                 "chat/公用代码", "mail/公用代码", "files/公用代码", "database/公用代码",
                 "code/公用代码", "git/公用代码", "github/公用代码", "pc/公用代码",
                 "server/公用代码", "buyer/公用代码", "merchant/公用代码"):
    sys.path.insert(0, str(ROOT / "tools" / relative))

from local_chat.backend import ChatStore
from local_mail.backend import MailStore
from local_files.backend import FileStore
from local_sqlite.backend import SQLiteStore
from local_code.backend import CodeStore
from local_git.backend import GitStore
from local_github.backend import GitHubStore
from local_pc.backend import PCStore
from local_server.backend import ServerStore
from local_commerce.core import CommerceStore

STORES = {"commerce": CommerceStore, "chat": ChatStore, "mail": MailStore, "files": FileStore,
          "database": SQLiteStore, "code": CodeStore, "git": GitStore, "github": GitHubStore,
          "pc": PCStore, "server": ServerStore}


def normalize(seed):
    changed = []
    for group, store in STORES.items():
        state = seed / "services" / group / "state.json"
        if not state.exists():
            continue
        before = state.read_bytes()
        try:
            store(seed)
        except Exception as error:
            print(f"{seed.name} {group}: ERROR {type(error).__name__}: {error}")
            continue
        if state.read_bytes() != before:
            changed.append(group)
    return changed


def main():
    for seed in sorted((ROOT / "初始环境").iterdir(), key=lambda path: path.name):
        if seed.is_dir():
            changed = normalize(seed)
            print(seed.name, "updated:" + (",".join(changed) if changed else "none"))


if __name__ == "__main__":
    main()
