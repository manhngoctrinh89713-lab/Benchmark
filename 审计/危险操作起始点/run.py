"""唯一命令入口：在独立环境中重放轨迹并逐步评分。"""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from replay import main

if __name__ == '__main__':
    raise SystemExit(main())
