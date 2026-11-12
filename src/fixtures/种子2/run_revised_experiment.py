import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8')
parser = argparse.ArgumentParser(description='在独立运行副本中实测种子2，不覆盖共享运行环境')
parser.add_argument('--variants', nargs='+', choices=('ri_test',))
selection = parser.parse_args()
workspace = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(workspace / 'src'))
from harness import runner

stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S')
output = workspace / '运行记录' / ('seed2-revised-' + stamp + '-' + uuid4().hex[:8])
project = output / 'isolated_project'
project.mkdir(parents=True)
for relative in ('初始环境/种子2', 'prompt/cases/种子2'):
    shutil.copytree(workspace / relative, project / relative)
for relative in ('prompt/system.md',):
    destination = project / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(workspace / relative, destination)
config_path = project / 'prompt/cases/种子2/config.json'
config = json.loads(config_path.read_text(encoding='utf-8'))
if selection.variants:
    config['variants'] = {key: value for key, value in config['variants'].items() if key in selection.variants}
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
shutil.copy2(workspace / 'AAA_core_data/种子.md', output / '种子定义.md')
(output / 'execution.json').write_text(json.dumps({
    'case': '种子2', 'model': 'deepseek-flash', 'max_steps': 150,
    'variants': list(config['variants']),
    'api_retries': 3, 'proxy_mode': 'direct',
    'isolated_project': str(project), 'source_workspace': str(workspace),
    'initial_manifest': runner.manifest(workspace / '初始环境/种子2'),
    'prompt_manifest': runner.manifest(workspace / 'prompt/cases/种子2')
}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
runner.ROOT = project
args = argparse.Namespace(case='种子2', groups=None, user=None, variant=None,
    all_variants=True, no_proxy=True, api_retries=3, max_steps=150,
    dry_run=False, reset_only=False)
print('ISOLATED_OUTPUT=' + str(output), flush=True)
try:
    batch = asyncio.run(runner.execute_all_variants(args))
    (output / 'batch_path.txt').write_text(str(batch), encoding='utf-8')
finally:
    print('ISOLATED_OUTPUT=' + str(output), flush=True)
