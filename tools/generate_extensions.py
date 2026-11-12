"""Register additive workbench operations and regenerate schemas without opening environments."""
import ast
import asyncio
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
for shared in ("repos", "maintenance", "commerce"):
    sys.path.insert(0, str(ROOT/"shared"/shared))
GROUPS = {
    "files": ("local_files", "FileStore", "FileWorkbench"),
    "database": ("local_sqlite", "SQLiteStore", "DatabaseWorkbench"),
    "code": ("local_code", "CodeStore", "CodeWorkbench"),
    "git": ("local_git", "GitStore", "GitWorkbench"),
    "github": ("local_github", "GitHubStore", "GitHubWorkbench"),
    "pc": ("local_pc", "PCStore", "PCWorkbench"),
    "server": ("local_server", "ServerStore", "ServerWorkbench"),
}


async def main():
    from mcp.server.fastmcp import FastMCP
    for group, (package, cls_name, mixin) in GROUPS.items():
        folder = ROOT/group
        sys.path.insert(0, str(folder/"公用代码"))
        backend = importlib.import_module(package+".backend")
        cls = getattr(backend, cls_name)
        source = ROOT/"shared/repos/local_repos/workbench.py" if group == "git" else folder/"公用代码"/package/"workbench.py"
        node = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef) and n.name == mixin)
        added = [n.name for n in node.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
        api = folder/"工具调用API"
        for name in added:
            target = api/name
            target.mkdir(exist_ok=True)
            (target/"__init__.py").write_text("from .tool import register\n", encoding="utf-8")
            readonly = name.startswith(("get_", "list_", "read_", "search_", "compare_", "diagnose_", "pc_get_", "pc_list_", "server_list_", "git_blame", "git_file_history", "git_reflog", "git_tags"))
            description = getattr(cls, name).__doc__
            code = f'''from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name={name!r}, description={description!r}, annotations=ToolAnnotations(readOnlyHint={readonly!r}, destructiveHint={not readonly!r}, idempotentHint={readonly!r}, openWorldHint=False))(store.{name})
'''
            (target/"tool.py").write_text(code, encoding="utf-8")
        # Build from entrypoint registrations, without create_server's optional
        # runtime capability filtering and without invoking any store constructor.
        server = FastMCP("Static "+group)
        store = cls.__new__(cls)
        for entry in sorted(api.glob("*/tool.py")):
            spec = importlib.util.spec_from_file_location("static_"+group+"_"+entry.parent.name, entry)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.register(server, store)
        schemas = await server.list_tools()
        for tool in schemas:
            schema = tool.model_dump(mode="json", exclude_none=True, include={"name", "description", "inputSchema", "annotations"})
            (api/tool.name/"schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        project = folder/"pyproject.toml"
        names = sorted(t.name for t in schemas)
        packages = [package, package+".api", *[package+".api."+n for n in names]]
        t = re.sub(r"(?m)^packages = .*", "packages = "+json.dumps(packages), project.read_text(encoding="utf-8"))
        project.write_text(t.replace('version = "0.1.0"', 'version = "0.2.0"'), encoding="utf-8")
        print(f"{group}: +{len(added)} operations, {len(schemas)} signatures registered; no environment opened")


if __name__ == "__main__":
    asyncio.run(main())
