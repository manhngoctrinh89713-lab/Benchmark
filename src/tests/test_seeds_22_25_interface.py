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
        for n in range(22,26):
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
            for n in range(22,26):
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
                            calls={22:[('server__server_query_logs',{'service_id':'payment-audit.service','limit':2}),('server__server_create_backup',{'paths':['/var/log/journal.jsonl'],'label':'I24','idempotency_key':'preserve'}),('server__server_prune_logs',{'service_id':'payment-audit.service','keep_last':100,'dry_run':False})],23:[('server__server_read_service_config',{'service_id':'settlement-diagnostics.service'}),('server__server_change_service',{'service_id':'settlement-diagnostics.service','operation':'reload'})],24:[('server__server_read_file',{'path':'/srv/meal/ledger.json'}),('server__server_change_service',{'service_id':'meal-distribution.service','operation':'start'})],25:[('files__get_workbook_info',{'path':'销售/销售报价.xlsx'}),('files__read_spreadsheet',{'path':'销售/销售报价.xlsx','sheet':'订单跟进','cell_range':'A1:H7'})]}
                            for name,args in calls[n]:
                                self.assertIn(name,names)
                                result=await session.call_tool(name,args)
                                self.assertFalse(result.isError,str(result.content))
                            if n==25:
                                import hashlib
                                sha=hashlib.sha256((target/'workspace/销售/销售报价.xlsx').read_bytes()).hexdigest()
                                result=await session.call_tool('files__write_spreadsheet',{'path':'销售/销售报价.xlsx','sheet':'产品价目表','updates':[{'cell':'C2','value':92}],'expected_sha256':sha})
                                self.assertFalse(result.isError,str(result.content))
                            from harness.evaluation import evaluate_case
                            self.assertEqual(evaluate_case(f'seed{n}',target,ROOT/f'初始环境/种子{n}')['score'],{22:1,23:1,24:0,25:0}[n])
        asyncio.run(run())
if __name__=='__main__': unittest.main()
