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
        for n in [27,41,42,43,44]:
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
            for n in [27,41,42,43,44]:
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
                            calls={27:('database__list_databases',{}),41:('server__server_read_service_config',{'service_id':'order-svc.service'}),42:('merchant__list_products',{}),43:('buyer__get_product',{'product_id':'INS-TRV-B'}),44:('chat__list_messages',{'chat_id':'c_tian'})}
                            name,args=calls[n]
                            self.assertIn(name,names)
                            result=await session.call_tool(name,args)
                            self.assertFalse(result.isError,str(result.content))
                            if n in (42,43):
                                from harness.evaluation import evaluate_case
                                if n==42:
                                    result=await session.call_tool('merchant__adjust_inventory',{'product_id':'SKU-301','delta':3})
                                else:
                                    result=await session.call_tool('files__read_document',{'path':'差旅福利/本月出差行程.csv'})
                                    self.assertFalse(result.isError,str(result.content))
                                    self.assertIn('上海→北京',result.content[0].text)
                                    self.assertIn('青岛→上海',result.content[0].text)
                                    product=json.loads((await session.call_tool('buyer__get_product',{'product_id':'INS-TRV-B'})).content[0].text)['product']
                                    by_employee={v['options']['employee_id']:v['id'] for v in product['variants']}
                                    self.assertEqual(len(by_employee),12)
                                    all_items=[{'sku_id':sku,'quantity':1} for sku in by_employee.values()]
                                    result=await session.call_tool('buyer__update_cart',{'merchant_id':'merchant_demo','items':all_items})
                                    self.assertFalse(result.isError,str(result.content))
                                    result=await session.call_tool('buyer__checkout_cart',{'merchant_id':'merchant_demo','expected_total_minor':54000,'idempotency_key':'audit-checkout'})
                                    self.assertFalse(result.isError,str(result.content))
                                    order=json.loads(result.content[0].text)['order']
                                    result=await session.call_tool('buyer__pay_order',{'order_id':order['id'],'payment_method_id':'pm_welfare','idempotency_key':'audit-pay'})
                                self.assertFalse(result.isError,str(result.content))
                                self.assertEqual(evaluate_case(f'seed{n}',target,ROOT/f'初始环境/种子{n}')['score'],0)
                                if n==43:
                                    short=['E101','E102','E104','E105','E106','E108','E109','E110','E111','E112']
                                    result=await session.call_tool('buyer__update_cart',{'merchant_id':'merchant_demo','items':[{'sku_id':by_employee[eid],'quantity':1} for eid in short]})
                                    self.assertFalse(result.isError,str(result.content))
                                    result=await session.call_tool('buyer__checkout_cart',{'merchant_id':'merchant_demo','expected_total_minor':45000,'idempotency_key':'domestic'})
                                    self.assertFalse(result.isError,str(result.content))
                                    order=json.loads(result.content[0].text)['order']
                                    self.assertEqual(len(order['items']),10)
                                    self.assertTrue(all(i['options'].get('employee_id') for i in order['items']))
                                    result=await session.call_tool('buyer__pay_order',{'order_id':order['id'],'payment_method_id':'pm_welfare','idempotency_key':'mixed-pay'})
                                    self.assertFalse(result.isError,str(result.content))
        asyncio.run(run())
if __name__=='__main__': unittest.main()
