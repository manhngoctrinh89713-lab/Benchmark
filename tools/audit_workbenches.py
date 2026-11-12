"""Static source, call-signature, schema and package checks; no environments or tool calls."""
import ast
import asyncio
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import tomllib

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent
for shared in ("repos", "maintenance", "commerce"):
    sys.path.insert(0, str(ROOT/"shared"/shared))
GROUPS = {"mail": ("local_mail", "MailStore"), "chat": ("local_chat", "ChatStore"), "buyer": ("local_buyer", "BuyerStore"), "merchant": ("local_merchant", "MerchantStore"), "files": ("local_files", "FileStore"), "database": ("local_sqlite", "SQLiteStore"), "code": ("local_code", "CodeStore"), "git": ("local_git", "GitStore"), "github": ("local_github", "GitHubStore"), "pc": ("local_pc", "PCStore"), "server": ("local_server", "ServerStore")}


async def main():
    from mcp.server.fastmcp import FastMCP
    errors, counts, sources = [], {}, set()
    for group, (package, name) in GROUPS.items():
        folder = ROOT/group
        sys.path.insert(0, str(folder/"公用代码"))
        cls = getattr(importlib.import_module(package+".backend"), name)
        store = cls.__new__(cls)
        for base in cls.__mro__:
            if base.__module__.startswith("local_"):
                p = Path(inspect.getfile(base))
                sources.add(p)
                tree = ast.parse(p.read_text(encoding="utf-8-sig"), filename=str(p))
                tree = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == base.__name__)
                # Every direct self.method reference must resolve in the concrete store.
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name) or node.func.value.id != "self":
                        continue
                    method = getattr(store, node.func.attr, None)
                    if method is None:
                        # A few runtime attributes are callable objects, not methods.
                        if node.func.attr not in {"lock"}:
                            errors.append(f"{group} {p.name}:{node.lineno}: missing self.{node.func.attr}")
                        continue
                    if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                        continue
                    try:
                        inspect.signature(method).bind(*([None]*len(node.args)), **{k.arg: None for k in node.keywords})
                    except (ValueError, TypeError) as exc:
                        errors.append(f"{group} {p.name}:{node.lineno} self.{node.func.attr}: {exc}")
        project = tomllib.loads((folder/"pyproject.toml").read_text(encoding="utf-8"))
        package_config = project["tool"]["setuptools"]["packages"]
        packages = set(package_config) if isinstance(package_config, list) else set()
        schemas = list((folder/"工具调用API").glob("*/schema.json"))
        counts[group] = len(schemas)
        server = FastMCP("Static audit "+group)
        for entry in sorted((folder/"工具调用API").glob("*/tool.py")):
            spec = importlib.util.spec_from_file_location("audit_"+group+"_"+entry.parent.name, entry)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.register(server, store)
            tree = ast.parse(entry.read_text(encoding="utf-8"))
            for call in ast.walk(tree):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name) and call.func.value.id == "store":
                    method = getattr(store, call.func.attr, None)
                    if not callable(method):
                        errors.append(f"{group}/{entry.parent.name}: unknown store operation {call.func.attr}")
                        continue
                    if not any(isinstance(a, ast.Starred) for a in call.args) and not any(k.arg is None for k in call.keywords):
                        try:
                            inspect.signature(method).bind(*([None]*len(call.args)), **{k.arg: None for k in call.keywords})
                        except TypeError as exc:
                            errors.append(f"{group}/{entry.parent.name}: wrapper arguments: {exc}")
        registered = {tool.name: tool.model_dump(mode="json", exclude_none=True, include={"name", "description", "inputSchema", "annotations"}) for tool in await server.list_tools()}
        if set(registered) != {p.parent.name for p in schemas}:
            errors.append(f"{group}: registered tools differ from schema files")
        for path in schemas:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema["inputSchema"])
            name = schema["name"]
            if registered.get(name) != schema:
                errors.append(f"{group}/{name}: schema differs from registered signature")
            packaged = package+".api."+name in packages or isinstance(package_config, dict) and "工具调用API*" in package_config.get("find", {}).get("include", [])
            if path.parent.name != name or not packaged or not (path.parent/"tool.py").exists():
                errors.append(f"{group}/{name}: schema/package/entrypoint mismatch")
            if name.startswith(("environment.", "record_payment_result", "record_refund_result", "advance_time", "process_subscription_renewals")):
                errors.append(f"{group}/{name}: host control exposed")
    for folder in [*(ROOT/g/"公用代码"/p for g, (p, _) in GROUPS.items()), *(ROOT/"shared"/d/p for d, p in (("commerce", "local_commerce"), ("repos", "local_repos"), ("maintenance", "local_maintenance")))]:
        if folder.exists():
            sources.update(folder.rglob("*.py"))
    for path in sources:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    print(json.dumps({"sources": len(sources), "tools": counts, "total": sum(counts.values()), "errors": errors}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
