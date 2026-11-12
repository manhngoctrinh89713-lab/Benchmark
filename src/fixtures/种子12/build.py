import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_seeds_7_12 import build12, config
if __name__=='__main__':
 build12()
