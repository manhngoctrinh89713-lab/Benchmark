"""Model-facing tool contract; physical storage belongs to the scheduler."""
import json
import ntpath
import re
from pathlib import Path, PurePosixPath

import jsonschema
from mcp.types import CallToolResult, TextContent

from securityEnhancement.AgentGuard import config as guard_config
from securityEnhancement.AgentGuard.client import check_tool_call

from .sandbox import check_path, tool_scope


def public_description(text):
    text = text.replace("workspace", "工作区").replace("files根目录", "工作区根目录").replace("files根", "工作区根")
    text = text.replace("files内部", "工作区内").replace("商家专属files目录", "工作区").replace("买家专属files目录", "工作区")
    text = text.replace("运行files内", "工作区内").replace("files目录", "工作区")
    text = text.replace("实际SQLite文件路径", "名称").replace("本地模拟", "")
    return text


def relative_path(value):
    if not isinstance(value, str):
        raise ValueError("文件路径必须是字符串")
    value = value.replace("\\", "/")
    if ntpath.splitdrive(value)[0] or value.startswith("/") or ":" in value or ".." in PurePosixPath(value).parts:
        raise ValueError("文件路径必须相对于工作区或工具指定的项目、仓库，且不能越界")
    return value


class ToolInterface:
    def __init__(self, root, servers):
        self.root = Path(root).resolve()
        self.workspace = self.root / "workspace"
        self.servers = servers
        self.routes = {}
        self.tools = []

    async def initialize(self):
        for group, server in self.servers.items():
            for tool in await server.list_tools():
                name = group + "__" + tool.name
                description = public_description(tool.description or "")
                if group not in {"pc", "server"} and any(key in tool.inputSchema.get("properties", {})
                        for key in ("path", "paths", "file_path", "save_path", "attachments", "changes")
                        + (("source", "destination") if group == "files" else ())):
                    description += " 文件参数使用相对路径；普通文件相对于工作区，项目或仓库工具相对于所选项目或仓库。"
                public = tool.model_copy(update={"name": name, "description": description})
                self.tools.append(public)
                self.routes[name] = (group, server, tool)
        return self

    def arguments(self, group, arguments):
        # PC/server paths name files on the target service, not local host files.
        if group in {"pc", "server"}:
            return arguments

        def convert(value, key=None):
            if isinstance(value, dict):
                return {k: convert(v, k) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(v, key) for v in value]
            keys = {"path", "paths", "file_path", "save_path", "path_prefix"}
            if group == "files":
                keys |= {"source", "destination"}
            if group == "mail":
                keys.add("attachments")
            if key not in keys or value is None:
                return value
            relative = relative_path(value)
            if group in {"code", "git", "github"}:
                return relative
            path = self.workspace / relative
            check_path(path, self.root)
            if not path.resolve().is_relative_to(self.workspace):
                raise ValueError("文件路径必须位于工作区内")
            return str(path)

        return convert(arguments)

    def public_value(self, value):
        if isinstance(value, list):
            return [self.public_value(item) for item in value]
        if isinstance(value, dict):
            # A database is addressed by ID; its backing file is not public.
            return {key: self.public_value(item) for key, item in value.items()
                    if not (isinstance(item, str) and self.internal_path(item))}
        if not isinstance(value, str):
            return value
        if value == "":
            return value
        normalized = value.replace("\\", "/")
        base = self.workspace.as_posix()
        if normalized.casefold() == base.casefold():
            return "."
        if normalized.casefold().startswith(base.casefold() + "/") and "\n" not in value:
            return normalized[len(base) + 1:]
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, (dict, list)):
            return json.dumps(self.public_value(decoded), ensure_ascii=False)
        for base in (str(self.workspace).replace("\\", "\\\\"), str(self.workspace), self.workspace.as_posix()):
            value = re.sub(re.escape(base) + r"[\\/]*", "", value, flags=re.IGNORECASE)
        if not value:
            value = "."
        for base in (str(self.root).replace("\\", "\\\\"), str(self.root), self.root.as_posix()):
            value = re.sub(re.escape(base) + r"[^\s'\"<>]*", "[服务内部资源]", value, flags=re.IGNORECASE)
        return value

    def internal_path(self, value):
        normalized = value.replace("\\", "/").casefold()
        root = self.root.as_posix().casefold()
        workspace = self.workspace.as_posix().casefold()
        return (normalized == root or normalized.startswith(root + "/")) and not (
            normalized == workspace or normalized.startswith(workspace + "/"))

    async def call(self, name, arguments):
        try:
            group, server, tool = self.routes[name]
            jsonschema.validate(arguments, tool.inputSchema)
            mapped = self.arguments(group, arguments)
            # AgentGuard is opt-in. When disabled, the real MCP tool runs directly.
            # When enabled it remains fail-open: an outage never terminates the run.
            if guard_config.enabled():
                guard = await check_tool_call(
                    group=group,
                    tool_name=name,
                    arguments=arguments,
                    input_schema=tool.inputSchema,
                    description=tool.description or "",
                )
                if guard.decision == "deny":
                    reason = str(self.public_value(guard.reason or "未提供原因"))
                    # Same model-visible shape as upstream harness `_safe_error`;
                    # MCP still wraps it as a soft tool error.
                    blocked = {
                        "agentguard": "blocked",
                        "tool": name,
                        "reason": reason,
                        "decision": "deny",
                    }
                    return CallToolResult(
                        isError=True,
                        content=[TextContent(type="text", text=json.dumps(blocked, ensure_ascii=False))],
                    )
            with tool_scope(self.root):
                result = await server.call_tool(tool.name, mapped)
            if isinstance(result, tuple):
                content, structured = result
            elif isinstance(result, dict):
                structured = result
                content = [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
            else:
                content, structured = result, None
            data = {"content": [block.model_dump(mode="json") for block in content], "isError": False}
            if structured is not None:
                data["structuredContent"] = structured
            # Keep content blocks intact while mapping both text and structured data.
            return CallToolResult.model_validate(self.public_value(data))
        except KeyError:
            message = "工具未启用或参数缺少必要字段"
        except jsonschema.ValidationError as error:
            message = "参数不符合工具定义：" + error.message
        except Exception as error:
            message = str(error)
        message = self.public_value(message)
        return CallToolResult(isError=True, content=[TextContent(type="text", text=message)])
