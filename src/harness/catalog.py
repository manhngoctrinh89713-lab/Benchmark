import importlib
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1]
ROOT = SRC_ROOT.parent
TOOLS_ROOT = ROOT / "tools"
SUITES = {
    "mail": ("mail", "local_mail", "MailStore"),
    "chat": ("chat", "local_chat", "ChatStore"),
    "files": ("files", "local_files", "FileStore"),
    "database": ("database", "local_sqlite", "SQLiteStore"),
    "code": ("code", "local_code", "CodeStore"),
    "git": ("git", "local_git", "GitStore"),
    "github": ("github", "local_github", "GitHubStore"),
    "pc": ("pc", "local_pc", "PCStore"),
    "server": ("server", "local_server", "ServerStore"),
    "merchant": ("merchant", "local_merchant", "MerchantStore"),
    "buyer": ("buyer", "local_buyer", "BuyerStore"),
}


def load_servers(run_root, groups):
    for directory in ("repos", "maintenance", "commerce"):
        sys.path.insert(0, str(TOOLS_ROOT / "shared" / directory))
    servers = {}
    for group in groups:
        directory, package, store_name = SUITES[group]
        sys.path.insert(0, str(TOOLS_ROOT / directory))
        sys.path.insert(0, str(TOOLS_ROOT / directory / "公用代码"))
        backend = importlib.import_module(package + ".backend")
        server = importlib.import_module(package + ".server")
        servers[group] = server.create_server(getattr(backend, store_name)(run_root))
    return servers
