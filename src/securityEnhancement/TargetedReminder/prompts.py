"""Prompt block for the targeted-reminder experiment."""
from pathlib import Path

PROMPT_PATH = Path(__file__).with_name("prompt.md")


def build_targeted_reminder_prompt():
    """Return the three-sentence reminder block appended to the base system prompt."""
    return PROMPT_PATH.read_text(encoding="utf-8").strip()
