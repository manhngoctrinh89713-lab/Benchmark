import argparse,importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('batch364547',Path(__file__).with_name('seeds_36_45_47.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def evaluate(run_root,initial_root=None):return m.evaluate(36,run_root,initial_root)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run-root',required=True);p.add_argument('--initial-root');p.add_argument('--output');a=p.parse_args();r=evaluate(a.run_root,a.initial_root)
 if a.output:Path(a.output).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
 print(r['score'])
