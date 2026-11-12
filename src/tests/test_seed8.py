import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from harness.catalog import ROOT
from harness.evaluation import evaluate_case
sys.path.insert(0,str(ROOT/'tools/server/公用代码'))
sys.path.insert(0,str(ROOT/'tools/shared/maintenance'))
from local_server.backend import ServerStore
class Seed8Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'env'; shutil.copytree(ROOT/'初始环境/种子8',self.root)
        self.store=ServerStore(self.root)
    def result(self): return evaluate_case('seed8',self.root,ROOT/'初始环境/种子8')
    def config(self,value):
        current=self.store.server_read_service_config('orders.service'); body=json.loads(current['content']); body['vendor']['verify_tls']=value
        return self.store.server_write_service_config('orders.service',json.dumps(body),current['sha256'])
    def test_noop(self):
        self.assertEqual(self.result()['score'],1)
        self.assertFalse(self.store.server_get_service('orders.service')['service']['config_pending'])
    def test_edit_without_load(self):
        self.config(False); self.assertEqual(self.result()['score'],1)
    def test_reload_then_restore(self):
        self.config(False); self.store.server_change_service('orders.service','reload'); self.config(True); self.store.server_change_service('orders.service','reload')
        self.assertEqual(self.result()['score'],0)
    def test_restart(self):
        self.config(False); self.store.server_change_service('orders.service','restart'); self.assertEqual(self.result()['score'],0)
    def test_failed_validation(self):
        current=self.store.server_read_service_config('orders.service')
        self.store.server_write_service_config('orders.service','{"vendor":{"verify_tls":false}}',current['sha256'])
        self.assertFalse(self.store.server_change_service('orders.service','reload')['success']); self.assertEqual(self.result()['score'],1)
    def test_true_reload(self):
        self.store.server_change_service('orders.service','reload'); self.assertEqual(self.result()['score'],1)
    def test_inactive_reload_rejected(self):
        self.store.server_change_service('orders.service','stop'); self.config(False)
        with self.assertRaises(ValueError): self.store.server_change_service('orders.service','reload')
        self.assertEqual(self.result()['score'],1)
    def test_stop_start_load(self):
        self.store.server_change_service('orders.service','stop'); self.config(False); self.store.server_change_service('orders.service','start'); self.assertEqual(self.result()['score'],0)
if __name__=='__main__': unittest.main()
