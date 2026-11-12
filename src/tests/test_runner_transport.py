import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from harness.transport import request_model


class ModelTransportTests(unittest.TestCase):
    def test_transport_retries_exact_request_and_records_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AsyncMock()
            expected = httpx.Response(200, json={"choices": []})
            client.post.side_effect = [httpx.ReadError("closed"), httpx.RemoteProtocolError("closed"), expected]
            meta, payload = {}, {"messages": [{"role": "user", "content": "task"}]}
            with patch("harness.runner.asyncio.sleep", new_callable=AsyncMock):
                result = asyncio.run(request_model(client, payload, "test-only", Path(directory), 3, meta, 2))
            self.assertIs(result, expected)
            self.assertEqual(meta["api_attempts"], 3)
            self.assertEqual(client.post.await_count, 3)
            self.assertTrue(all(call.kwargs["json"] is payload for call in client.post.await_args_list))
            events = [json.loads(line) for line in (Path(directory) / "transport_errors.jsonl").read_text().splitlines()]
            self.assertEqual([e["attempt"] for e in events], [1, 2])
            self.assertNotIn("test-only", json.dumps(events))

    def test_no_retries_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AsyncMock()
            client.post.side_effect = httpx.ReadError("closed")
            with self.assertRaises(httpx.ReadError):
                asyncio.run(request_model(client, {}, "test-only", Path(directory), 1, {}))
            self.assertEqual(client.post.await_count, 1)
