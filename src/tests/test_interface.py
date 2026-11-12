import asyncio
import json
import shutil
import tempfile
import unittest
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from harness.catalog import ROOT, SRC_ROOT, SUITES, load_servers
from harness.interface import ToolInterface
from harness.instructions import assemble_prompt


class InterfaceTests(unittest.TestCase):
    def test_empty_payload_stays_empty_while_workspace_maps_to_dot(self):
        with tempfile.TemporaryDirectory() as directory:
            interface = ToolInterface(Path(directory), {})
            self.assertEqual(interface.public_value({"diff": "", "operation": None}), {"diff": "", "operation": None})
            self.assertEqual(interface.public_value(str(Path(directory) / "workspace")), ".")
            self.assertEqual(json.loads(interface.public_value('{"diff": ""}')), {"diff": ""})

    def test_shared_workspace_and_private_service_storage(self):
        async def run(root):
            interface = await ToolInterface(root, load_servers(root, SUITES)).initialize()

            async def call(name, arguments=None):
                result = await interface.call(name, arguments or {})
                self.assertFalse(result.isError, str(result.content))
                raw = result.model_dump_json()
                self.assertNotIn(str(root).replace('\\', '\\\\'), raw)
                self.assertNotIn(root.as_posix(), raw)
                return result

            self.assertEqual(len(interface.tools), 442)
            for tool in interface.tools:
                self.assertNotIn('workspace', tool.description)
                self.assertNotIn('services', tool.description)
            directories = await call('files__list_allowed_directories')
            self.assertEqual(json.loads(directories.content[0].text)['directories'], ['.'])
            databases = await call('database__list_databases')
            self.assertNotIn('path', json.loads(databases.content[0].text)['items'][0])
            for name in ['code__list_projects', 'git__list_repositories', 'chat__list_chats',
                         'mail__list_accounts', 'pc__pc_get_system_info', 'server__server_get_system_info']:
                await call(name)
            await call('files__write_file', {'path': 'output/shared.txt', 'content': 'shared'})
            await call('chat__send_file', {'chat_id': 'c_project', 'file_path': 'output/shared.txt'})
            await call('chat__download_media', {'chat_id': 'c_project', 'message_id': 'm1',
                'attachment_id': 'a1', 'save_path': 'output/attachment.csv'})
            await call('files__read_document', {'path': 'output/attachment.csv'})
            await call('merchant__export_orders', {'save_path': 'output/orders.csv'})
            await call('files__read_document', {'path': 'output/orders.csv'})
            self.assertTrue((root / 'workspace/output/orders.csv').is_file())
            for path in [str(root / 'workspace/output/shared.txt'), '../services/chat/state.json',
                         'C:/Users/secret.txt', '/etc/passwd', '//host/share/file', 'file.txt:stream']:
                error = await interface.call('files__read_document', {'path': path})
                self.assertTrue(error.isError)
                self.assertNotIn(str(root), str(error.content))
            missing = await interface.call('files__read_document', {'path': 'missing.txt'})
            self.assertTrue(missing.isError)
            self.assertNotIn(str(root), missing.content[0].text)
            self.assertNotIn(str(root).replace('\\', '\\\\'), missing.content[0].text)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            shutil.copytree(ROOT / '初始环境/综合测试', root)
            asyncio.run(run(root))

    def test_prompt_contains_only_public_environment(self):
        prompt = assemble_prompt(['chat', 'files'])
        self.assertIn('启用工具组：chat, files', prompt)
        # 工具说明只走请求里的 tools 数组，system 里不再拼 prompt/tools/<组>.md。
        self.assertNotIn('可用工具（参数见函数定义）', prompt)
        self.assertNotIn('workspace', prompt)
        self.assertNotIn('services', prompt)
        self.assertNotIn(str(ROOT), prompt)
        self.assertNotIn('运行根', prompt)

    def test_stdio_publishes_public_paths(self):
        async def run(root):
            params = StdioServerParameters(command=sys.executable,
                args=['-B', '-m', 'harness.worker', '--run-root', str(root), '--groups', 'files', 'chat', 'database'],
                cwd=str(ROOT), env={'PYTHONPATH': str(SRC_ROOT), 'PYTHONIOENCODING': 'utf-8'})
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    self.assertEqual(len(tools), 106)
                    result = await session.call_tool('files__list_allowed_directories', {})
                    self.assertFalse(result.isError)
                    self.assertEqual(json.loads(result.content[0].text)['directories'], ['.'])
                    result = await session.call_tool('files__read_document', {'path': 'missing.txt'})
                    self.assertTrue(result.isError)
                    self.assertNotIn(str(root), result.content[0].text)
                    self.assertNotIn(str(root).replace('\\', '\\\\'), result.content[0].text)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'run'
            shutil.copytree(ROOT / '初始环境/综合测试', root)
            asyncio.run(run(root))


if __name__ == '__main__':
    unittest.main()
