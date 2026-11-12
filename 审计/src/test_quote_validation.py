import unittest
from quote_validation import match_quote, match_evidence_quote


class QuoteTests(unittest.TestCase):
    def test_format_and_json(self):
        self.assertEqual(match_quote('严禁外发', '严禁外发文件')['mode'], 'exact')
        self.assertEqual(match_quote('价格：5000，禁止“外发”', '价格: 5000, 禁止"外发"')['mode'], 'normalized')
        self.assertIsNotNone(match_quote('隐私确认：文件未修改', '**隐私确认**：文件未修改'))
        value = [{'function': {'arguments': '{"description":"单件销售","price":5000}'}}]
        self.assertIsNotNone(match_quote('"description": "单件销售", "price": 5000', value))

    def test_ellipsis_preserves_order_and_source(self):
        self.assertIsNotNone(match_quote('必须先核对授权范围……随后才允许发送数据', '必须先核对授权范围，确认审批文件之后，随后才允许发送数据'))
        self.assertIsNone(match_quote('随后才允许发送数据……必须先核对授权范围', '必须先核对授权范围，然后随后才允许发送数据'))
        self.assertIsNone(match_quote('必须先核对授权范围……随后才允许发送数据', ['必须先核对授权范围', '随后才允许发送数据']))

    def test_semantic_changes_stay_invalid(self):
        for quote, source in [('价格5000', '价格50000'), ('允许外发', '不允许外发'), ('金额15', '金额1.5'), ('禁止外发', '允许外发')]:
            self.assertIsNone(match_quote(quote, source), (quote, source))
        self.assertIsNone(match_quote('推理中的独有内容', None))

    def test_cross_message_within_eligible_pool(self):
        quote = '必须先核对授权范围……随后才允许发送数据'
        self.assertEqual(match_evidence_quote(quote, '必须先核对授权范围', ['必须先核对授权范围', '随后才允许发送数据'])['mode'], 'cross_message_ellipsis')
        self.assertIsNone(match_evidence_quote(quote, '必须先核对授权范围', ['必须先核对授权范围']))


if __name__ == '__main__':
    unittest.main()
