#!/usr/bin/env python3
"""Execute the frozen mode-4 internal evaluation.

Run from the artifact directory:
    PYTHONPATH=src python scripts/run_evaluation.py

The driver writes raw per-instance evidence before deriving aggregate JSON.
"""
from __future__ import annotations

import json
import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def scientific_failures(summary: dict) -> list[str]:
    required_zero = {
        'full_semantic_differences', 'local_carrier_differences',
        'reference_evaluator_differences', 'reference_selection_differences',
        'reference_target_differences', 'reference_acceptance_differences',
        'mutation_decision_differences', 'derivation_failures',
        'derivation_producer_differences', 'derivation_target_differences',
        'frame_failures', 'selector_differences', 'accepted_mutations',
        'reference_accepted_mutations', 'accepted_proof_mutations',
    }
    failures = [key for key in sorted(required_zero) if summary.get(key) != 0]
    failures.extend(key for key, value in summary.items()
                    if key not in required_zero
                    and (key.endswith('_differences') or key.endswith('_failures'))
                    and value != 0)
    for key, expected in {'programs': 400, 'bindings': 13464, 'selected': 5782,
                          'payload_bits': 4461, 'full_executions': 3200,
                          'local_carrier_cases': 46256, 'reference_evaluator_calls': 6400,
                          'derivations': 800, 'certificate_mutations': 2000,
                          'proof_mutations': 3280, 'derivation_mutations_not_applicable': 720,
                          'frame_vectors': 131071, 'legal_frames': 12309,
                          'interval_instances': 65536}.items():
        if summary.get(key) != expected:
            failures.append(key + ':count')
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=pathlib.Path,
                        help='Write a separate raw/derived run, preserving saved measurements.')
    args = parser.parse_args()
    from tidemark.evaluation import run
    output = args.output_dir.resolve() if args.output_dir else ROOT / 'data'
    summary = run(
        raw_dir=output / "raw" / "mode4",
        derived_dir=output / "derived",
    )
    # The mode-qualified file is authoritative.  The unqualified name is a
    # convenience pointer containing the same current bytes, not a hand-edited
    # status file.
    encoded = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    (output / "derived" / "evaluation-summary-mode4.json").write_text(encoded)
    (output / "derived" / "evaluation-summary.json").write_text(encoded)
    printable = {key: value for key, value in summary.items() if key not in {"family_summary", "carrier_ablation", "raw_files"}}
    print(json.dumps(printable, indent=2, sort_keys=True))
    print(output / "derived" / "evaluation-summary-mode4.json")
    # A process that finishes enumeration is not necessarily a successful check.
    failures = scientific_failures(summary)
    print(json.dumps({'scientific_failure_gates': failures}, sort_keys=True))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
