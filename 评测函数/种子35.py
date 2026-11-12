import argparse,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('seeds35_38',Path(__file__).with_name('seeds_35_38.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def evaluate(run_root,initial_root=None):return module.evaluate(35,run_root,initial_root)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run-root',type=Path,required=True);p.add_argument('--initial-root',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();r=evaluate(a.run_root,a.initial_root)
 if a.output:a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
 print(r['score'])
