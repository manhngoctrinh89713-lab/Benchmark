import re
import unittest

from harness.instructions import assemble_prompt
from securityEnhancement.TargetedReminder import build_targeted_reminder_prompt


class TargetedReminderTests(unittest.TestCase):
    def test_prompt_contains_exactly_three_numbered_reminders(self):
        prompt = build_targeted_reminder_prompt()
        numbered = [line for line in prompt.splitlines() if re.match(r"^\d+\. ", line)]
        self.assertEqual(len(numbered), 3)
        self.assertIn("范围、对象、权限或审批前提", numbered[0])
        self.assertIn("权限、审批、保密、财务或人身安全约束", numbered[1])
        self.assertIn("环境证据", numbered[2])
        self.assertNotRegex(prompt, r"Requirement|Factual|RU|RI|FI")

    def test_targeted_prompt_is_appended_once_after_unchanged_base_prompt(self):
        base = assemble_prompt(["chat", "files"])
        targeted = assemble_prompt(["chat", "files"], targeted_reminder=True)
        prompt = build_targeted_reminder_prompt()
        self.assertEqual(targeted, base + "\n\n" + prompt)
        self.assertEqual(targeted.count(prompt), 1)
        self.assertFalse(prompt in base)


if __name__ == "__main__":
    unittest.main()
