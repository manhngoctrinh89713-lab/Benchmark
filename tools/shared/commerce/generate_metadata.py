"""Generate commerce schemas from signatures without constructing a store."""
import asyncio
import importlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))


async def main():
    for group in ("buyer", "merchant"):
        folder = ROOT / group
        sys.path.insert(0, str(folder / "公用代码"))
        package = "local_"+group
        backend = importlib.import_module(package+".backend")
        cls = getattr(backend, group.title()+"Store")
        names = set()
        for base in cls.__mro__:
            if base.__module__.startswith(package):
                names.update(n for n, fn in vars(base).items() if callable(fn) and not n.startswith("_") and n not in {"check_policy", "check_options", "delivery_view", "cart_view"})
        names -= {"process_subscription_renewals"}
        entries = []
        for name in sorted(names):
            fn = getattr(cls, name)
            description = fn.__doc__ or name.replace("_", " ")
            readonly = name.startswith(("get_", "list_", "search_"))
            entries.append(f"    {name!r}: ({description!r}, {readonly!r}),")
        catalog = '"""Explicit public commerce tool catalog."""\nfrom mcp.types import ToolAnnotations\n\nTOOLS = {\n'+"\n".join(entries)+'\n}\n\n\ndef register_tool(server, store, name):\n    description, readonly = TOOLS[name]\n    server.tool(name=name, description=description, annotations=ToolAnnotations(readOnlyHint=readonly, destructiveHint=not readonly, idempotentHint=readonly, openWorldHint=False))(getattr(store, name))\n\n\ndef register_tools(server, store):\n    for name in TOOLS:\n        register_tool(server, store, name)\n'
        (folder / "公用代码" / package / "catalog.py").write_text(catalog, encoding="utf-8")
        server_code = f'from mcp.server.fastmcp import FastMCP\nfrom .catalog import register_tools\n\n\ndef create_server(store):\n    server = FastMCP("Local {group.title()}")\n    register_tools(server, store)\n    return server\n'
        (folder / "公用代码" / package / "server.py").write_text(server_code, encoding="utf-8")
        module = importlib.import_module(package+".server")
        schemas = await module.create_server(cls.__new__(cls)).list_tools()
        api = folder / "工具调用API"
        for obsolete in api.glob("*/tool.py"):
            if obsolete.parent.name not in names:
                for filename in ("tool.py", "schema.json", "__init__.py"):
                    (obsolete.parent/filename).unlink(missing_ok=True)
        (api/"__init__.py").write_text(f"from {package}.catalog import register_tools\n", encoding="utf-8")
        for tool in schemas:
            target = api/tool.name
            target.mkdir(exist_ok=True)
            (target/"__init__.py").write_text("from .tool import register\n", encoding="utf-8")
            (target/"tool.py").write_text(f'from {package}.catalog import register_tool\n\n\ndef register(server, store):\n    register_tool(server, store, {tool.name!r})\n', encoding="utf-8")
            schema = tool.model_dump(mode="json", exclude_none=True, include={"name", "description", "inputSchema", "annotations"})
            (target/"schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        project = folder/"pyproject.toml"
        packages = [package, package+".api", *[package+".api."+n for n in sorted(names)]]
        content = re.sub(r"(?m)^packages = .*", "packages = "+json.dumps(packages), project.read_text(encoding="utf-8"))
        content = content.replace('version = "0.1.0"', 'version = "0.2.0"').replace('benchmark-local-commerce==0.1.0', 'benchmark-local-commerce==0.2.0')
        project.write_text(content, encoding="utf-8")
        lines = [f"## {group} 工具组", "", "金额使用整数最小货币单位；账户由环境绑定。支付、退款、物流、履约和订阅账期各有独立状态。", "", "可用工具（参数见函数定义）：", ""]
        lines.extend(f"- `{group}__{t.name}`：{t.description}" for t in schemas)
        (ROOT.parent/"prompt/tools"/(group+".md")).write_text("\n".join(lines)+"\n", encoding="utf-8")
        print(f"{group}: {len(schemas)} schemas generated from signatures; no environment opened")


if __name__ == "__main__":
    asyncio.run(main())
