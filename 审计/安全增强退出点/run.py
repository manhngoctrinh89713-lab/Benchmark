"""安全增强机制退出点事前风险证据评分唯一入口。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from enhanced_audit import main

if __name__ == '__main__':
    main()
