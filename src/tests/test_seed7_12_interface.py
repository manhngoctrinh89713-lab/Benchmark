"""MCP wiring and source-prompt integrity for the new production snapshots."""
import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from harness.catalog import ROOT,SRC_ROOT
from harness.instructions import select_instruction
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
class NewSeedInterfaceTests(unittest.TestCase):
    def test_original_prompts(self):
        text=(ROOT/'AAA_core_data/种子.md').read_text(encoding='utf-8')
        for n in range(8,13):
            with self.subTest(seed=n):
                directory=ROOT/f'prompt/cases/种子{n}'
                config=json.loads((directory/'config.json').read_text(encoding='utf-8'))
                section=text.split(f'# 种子{n}\n',1)[1].split('\n# 种子',1)[0]
                prompts=[line.split('|')[2].strip() for line in section.splitlines() if len(line.split('|')) > 2 and line.split('|')[1].strip() == '测试指令']
                self.assertEqual(len(config['variants']),len(prompts))
                for key,expected in zip(config['variants'],prompts):
                    self.assertEqual(select_instruction(config,directory,key)[0].strip(),expected)
    def test_mcp_initial_environments(self):
        async def run():
            for n in range(8,13):
                with self.subTest(seed=n), tempfile.TemporaryDirectory() as tmp:
                    target=Path(tmp)/'env'; shutil.copytree(ROOT/f'初始环境/种子{n}',target)
                    config=json.loads((ROOT/f'prompt/cases/种子{n}/config.json').read_text(encoding='utf-8'))
                    params=StdioServerParameters(command=sys.executable,args=['-B','-m','harness.worker','--run-root',str(target),'--groups',*config['groups']],cwd=str(ROOT),env={'PYTHONPATH':str(SRC_ROOT),'PYTHONIOENCODING':'utf-8'})
                    async with stdio_client(params) as streams:
                        async with ClientSession(*streams) as session:
                            await session.initialize(); listing=await session.list_tools()
                            self.assertTrue(listing.tools)
                            for group in config['groups']:
                                self.assertTrue(any(t.name.startswith(group+'__') for t in listing.tools),group)
                            names={t.name for t in listing.tools}
                            calls={8:('server__server_list_services',{}),9:('merchant__get_merchant_order',{'order_id':'O301'}),10:('git__list_repositories',{}),11:('database__list_databases',{}),12:('chat__list_chats',{})}
                            name,args=calls[n]
                            self.assertIn(name,names)
                            result=await session.call_tool(name,args)
                            self.assertFalse(result.isError,str(result.content))
        asyncio.run(run())
if __name__=='__main__': unittest.main()
