#!/usr/bin/env python3
"""Execute the frozen mode-4 internal evaluation.

Run from the artifact directory:
    PYTHONPATH=src python scripts/run_evaluation.py

The driver writes raw per-instance evidence before deriving aggregate JSON.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tidemark.evaluation import run


def main() -> int:
    summary = run(
        raw_dir=ROOT / "data" / "raw" / "mode4",
        derived_dir=ROOT / "data" / "derived",
    )
    # The mode-qualified file is authoritative.  The unqualified name is a
    # convenience pointer containing the same current bytes, not a hand-edited
    # status file.
    encoded = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    (ROOT / "data" / "derived" / "evaluation-summary-mode4.json").write_text(encoded)
    (ROOT / "data" / "derived" / "evaluation-summary.json").write_text(encoded)
    printable = {key: value for key, value in summary.items() if key not in {"family_summary", "carrier_ablation", "raw_files"}}
    print(json.dumps(printable, indent=2, sort_keys=True))
    print("data/derived/evaluation-summary-mode4.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
