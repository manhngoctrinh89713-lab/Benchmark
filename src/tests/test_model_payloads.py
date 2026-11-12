import unittest

from harness.transport import thinking_enabled, thinking_mode, thinking_payload


class ThinkingPayloadTests(unittest.TestCase):
    def test_glm_uses_lowest_supported_reasoning_effort(self):
        # GLM-5.3 Flash always reasons and rejects thinking.type=disabled (1210).
        self.assertEqual(thinking_payload("glm-5.3-flash"), {"reasoning_effort": "low"})
        self.assertTrue(thinking_enabled("glm-5.3-flash"))
        self.assertEqual(thinking_mode("glm-5.3-flash"), "reasoning_effort=low")

    def test_qwen_disables_thinking(self):
        self.assertEqual(thinking_payload("qwen3.8-flash"), {"enable_thinking": False})
        self.assertFalse(thinking_enabled("qwen3.8-flash"))
        self.assertEqual(thinking_mode("qwen3.8-flash"), "disabled")

    def test_deepseek_disables_thinking(self):
        self.assertEqual(thinking_payload("deepseek-flash"), {"thinking": {"type": "disabled"}})
        self.assertFalse(thinking_enabled("deepseek-flash"))
        self.assertEqual(thinking_mode("deepseek-flash"), "disabled")


if __name__ == "__main__":
    unittest.main()
