"""Generate chat tool entrypoints and schemas without opening a chat environment."""
import asyncio
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "公用代码"))
from local_chat.backend import ChatStore
from local_chat.catalog import TOOLS
from local_chat.server import create_server


async def main():
    # Registration reads Python signatures only; no constructor or chat action runs.
    server = create_server(ChatStore.__new__(ChatStore))
    schemas = await server.list_tools()
    if {t.name for t in schemas} != set(TOOLS):
        raise ValueError("Chat registration differs from catalog")
    project = ROOT / "pyproject.toml"
    package_names = ["local_chat", "local_chat.api", *["local_chat.api." + name for name in sorted(TOOLS)]]
    project.write_text(re.sub(r"(?m)^packages = .*", "packages = " + json.dumps(package_names), project.read_text(encoding="utf-8")), encoding="utf-8")
    target = ROOT / "工具调用API"
    target.mkdir(exist_ok=True)
    (target / "__init__.py").write_text('"""Public chat tool catalog."""\nfrom local_chat.catalog import register_tools\n', encoding="utf-8")
    for tool in schemas:
        folder = target / tool.name
        folder.mkdir(exist_ok=True)
        (folder / "__init__.py").write_text("from .tool import register\n", encoding="utf-8")
        (folder / "tool.py").write_text(
            '"""MCP registration for ' + tool.name + '."""\nfrom local_chat.catalog import register_tool\n\n\n'
            'def register(mcp, store):\n    register_tool(mcp, store, "' + tool.name + '")\n', encoding="utf-8")
        # The repository's schema contract excludes MCP outputSchema metadata.
        schema = tool.model_dump(mode="json", exclude_none=True, include={"name", "description", "inputSchema", "annotations"})
        (folder / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(ROOT.parents[1] / "src"))
    from harness.interface import public_description
    from harness.prepare import GUIDES
    lines = ["## chat 工具组", "", GUIDES["chat"], "", "可用工具（参数见函数定义）：", ""]
    for tool in sorted(schemas, key=lambda t: t.name):
        lines.append(f"- `chat__{tool.name}`：{public_description(tool.description)}")
    (ROOT.parents[1] / "prompt/tools/chat.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated {len(schemas)} chat tool schemas and chat instructions; no chat environment opened.")


if __name__ == "__main__":
    asyncio.run(main())
