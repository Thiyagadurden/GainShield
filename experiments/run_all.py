"""Regenerate every result, figure and report from scratch (fixed seeds).

    python experiments/run_all.py            # ~15 min on a 2-core laptop
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["run_certificate.py", "run_tuning.py", "run_evaluation.py", "run_failure_injection.py",
         "run_ablation.py", "make_reports.py"]

if __name__ == "__main__":
    t0 = time.time()
    for s in STEPS:
        print(f"=== {s}", flush=True)
        subprocess.run([sys.executable, str(HERE / s)], check=True)
    subprocess.run([sys.executable, str(HERE.parent / "diagrams" / "make_diagrams.py")], check=True)
    print(f"all done in {time.time() - t0:.0f} s")
