from pathlib import Path
import runpy


evaluate = runpy.run_path(str(Path(__file__).with_name("seed210_250_evidence.py")))["evaluate"]
