"""Summarize Specified Quit behavior from harness run records."""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from harness.catalog import ROOT


def _percentage(part, total):
    return None if not total else round(part / total * 100, 2)


def summarize_runs(runs):
    """Return run-level statistics for completed Specified Quit runs."""
    valid = [
        run for run in runs
        if run.get("method") == "specified_quit" and run.get("status") == "completed"
    ]
    invalid = [
        run for run in runs
        if run.get("method") == "specified_quit" and run.get("status") != "completed"
    ]

    outcomes = {
        "quit": 0,
        "tool_quit": 0,
        "text_quit": 0,
        "clarification_quit": 0,
        "quit_before_any_tool": 0,
        "mixed_call_quits": 0,
        "completed_without_quit": 0,
    }
    groups = defaultdict(lambda: {
        "total": 0,
        "quit": 0,
        "clarification_quit": 0,
        "quit_before_any_tool": 0,
    })

    for run in valid:
        decision = run.get("specified_quit") or {}
        triggered = bool(decision.get("triggered"))
        category = run.get("category") or "unclassified"
        instruction_type = run.get("instruction_type") or "unclassified"
        group = groups[(category, instruction_type)]
        group["total"] += 1

        if not triggered:
            outcomes["completed_without_quit"] += 1
            continue

        outcomes["quit"] += 1
        group["quit"] += 1
        source = decision.get("source")
        if source == "tool":
            outcomes["tool_quit"] += 1
        elif source == "text":
            outcomes["text_quit"] += 1
        if decision.get("question") or decision.get("missing_information"):
            outcomes["clarification_quit"] += 1
            group["clarification_quit"] += 1
        if decision.get("tool_calls_before") == 0:
            outcomes["quit_before_any_tool"] += 1
            group["quit_before_any_tool"] += 1
        if decision.get("mixed_with_other_calls"):
            outcomes["mixed_call_quits"] += 1

    total = len(valid)
    group_rows = []
    for (category, instruction_type), counts in sorted(groups.items()):
        group_total = counts["total"]
        group_rows.append({
            "category": category,
            "instruction_type": instruction_type,
            "total": group_total,
            **counts,
            "quit_rate_pct": _percentage(counts["quit"], group_total),
            "clarification_quit_rate_pct": _percentage(counts["clarification_quit"], group_total),
            "quit_before_any_tool_rate_pct": _percentage(counts["quit_before_any_tool"], group_total),
        })

    return {
        "total_runs": len(runs),
        "valid_runs": total,
        "invalid_runs": len(invalid),
        **outcomes,
        "quit_rate_pct": _percentage(outcomes["quit"], total),
        "clarification_quit_rate_pct": _percentage(outcomes["clarification_quit"], total),
        "quit_before_any_tool_rate_pct": _percentage(outcomes["quit_before_any_tool"], total),
        "groups": group_rows,
        "invalid_run_ids": sorted(run.get("run_id") for run in invalid),
    }


def load_runs(records_root, include_tests=False):
    runs = []
    for path in sorted(Path(records_root).glob("*/run.json")):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not include_tests and str(run.get("run_id", "")).startswith("test-"):
            continue
        if run.get("method") == "specified_quit":
            runs.append(run)
    return runs


def _format_rate(value):
    return "N/A" if value is None else f"{value}%"


def format_markdown(summary):
    lines = [
        "# Specified Quit 统计",
        "",
        f"- 有效运行：{summary['valid_runs']}",
        f"- 无效运行：{summary['invalid_runs']}",
        f"- Quit：{summary['quit']}（{_format_rate(summary['quit_rate_pct'])}）",
        f"- 带澄清问题或缺失信息的 Quit：{summary['clarification_quit']}（{_format_rate(summary['clarification_quit_rate_pct'])}）",
        f"- 尚未执行任何工具就 Quit：{summary['quit_before_any_tool']}（{_format_rate(summary['quit_before_any_tool_rate_pct'])}）",
        f"- 同批 tool calls 混入 Quit：{summary['mixed_call_quits']}",
        f"- 未 Quit 的正常完成：{summary['completed_without_quit']}",
        "",
        "| 类别 | 指令 | 总数 | Quit | 澄清型 Quit | 零工具 Quit | Quit率 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["groups"]:
        lines.append(
            f"| {row['category']} | {row['instruction_type']} | {row['total']} | "
            f"{row['quit']} | {row['clarification_quit']} | {row['quit_before_any_tool']} | "
            f"{_format_rate(row['quit_rate_pct'])} |"
        )
    if summary["invalid_run_ids"]:
        lines.extend(["", "无效运行：", "", *[f"- {run_id}" for run_id in summary["invalid_run_ids"]]])
    return "\n".join(lines) + "\n"


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="统计 Specified Quit 运行")
    parser.add_argument("--records", default=str(ROOT / "运行记录"), help="运行记录目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 而不是 Markdown")
    parser.add_argument("--include-tests", action="store_true", help="包含 test- 开头的测试运行记录")
    args = parser.parse_args()
    summary = summarize_runs(load_runs(args.records, include_tests=args.include_tests))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(format_markdown(summary), end="")


if __name__ == "__main__":
    main()
