"""Run the current150-169 checks and the four rewritten-seed boundaries; no API."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
if __name__=='__main__':
    for stream in [sys.stdout,sys.stderr]:
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    loader=unittest.TestLoader();suite=unittest.TestSuite()
    # Version-specific *_release.py files may describe retired seed scenarios.
    # Select the current case checks explicitly instead of discovering those files.
    for name in ['tests.test_seed150','tests.test_seeds151_156','tests.test_seed150_169_release','tests.test_rewritten_163_203_215_223']:
        suite.addTests(loader.loadTestsFromName(name))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
