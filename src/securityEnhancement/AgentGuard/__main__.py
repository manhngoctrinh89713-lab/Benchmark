"""Command line entry point: ``python -m securityEnhancement.AgentGuard``."""
from __future__ import annotations

import argparse
import sys

from . import config
from .audit import AuditLog
from .policy import Policy
from .server import GuardService, serve


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="python -m securityEnhancement.AgentGuard",
        description="本地 AgentGuard 工具调用防护服务（仅监听 localhost）",
    )
    parser.add_argument("--host", default=config.DEFAULT_HOST, help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PORT, help="监听端口，默认 38080")
    parser.add_argument("--policy", help="覆盖 AGENTGUARD_POLICY_PATH 的 policy 文件路径")
    parser.add_argument("--audit-dir", help="覆盖 AGENTGUARD_AUDIT_DIR 的审计目录")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port 必须在 0 到 65535 之间")
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("host 必须是 localhost 回环地址（127.0.0.1 / localhost / ::1）")

    policy_path = args.policy if args.policy is not None else config.policy_path()
    service = GuardService(policy=Policy.load(policy_path), audit=AuditLog(args.audit_dir))
    try:
        serve(args.host, args.port, service)
    except OSError as error:
        print(f"AgentGuard 启动失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
