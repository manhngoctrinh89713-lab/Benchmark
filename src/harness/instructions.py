"""System prompt assembly and user-instruction selection for one case.

The tool catalog reaches the model through the request's ``tools`` array built in
``harness/runner.py``: every enabled tool's name, description and parameter
schema is already there.  The per-group tool documents that used to be appended
here are archived at ``.archive/tool-docs-20261111/`` and no longer take part in
a run.
"""
from .catalog import ROOT
from securityEnhancement.QuittingAgents import build_specified_quit_prompt
from securityEnhancement.TargetedReminder import build_targeted_reminder_prompt


def assemble_prompt(groups, specified_quit=False, targeted_reminder=False):
    sections = [(ROOT / "prompt/system.md").read_text(encoding="utf-8")]
    sections.append(f"启用工具组：{', '.join(groups)}")
    text = "\n\n".join(sections)
    if specified_quit:
        text += "\n\n" + build_specified_quit_prompt()
    if targeted_reminder:
        text += "\n\n" + build_targeted_reminder_prompt()
    return text


def select_instruction(config, case_dir, variant=None, user=None):
    if user is not None:
        if variant:
            raise ValueError("--user 与 --variant 不可同时使用")
        return user, {"variant": "custom", "category": None, "instruction_type": "custom", "prompt_source": "--user"}
    variants = config.get("variants", {})
    if variants:
        if variant not in variants:
            raise ValueError("请用 --variant 明确指定 " + ", ".join(variants) + "，或使用 --all-variants")
        selected = variants[variant]
        info = {"variant": variant, "category": selected["category"],
                "instruction_type": selected["instruction_type"], "prompt_source": selected["user_prompt"]}
    else:
        if variant:
            raise ValueError("此用例未定义指令变体")
        info = {"variant": "default", "category": None, "instruction_type": None,
                "prompt_source": config["user_prompt"]}
    user_path = (case_dir / info["prompt_source"]).resolve()
    if not user_path.is_relative_to(case_dir.resolve()):
        raise ValueError("提示词必须位于用例目录内")
    return user_path.read_text(encoding="utf-8"), info
