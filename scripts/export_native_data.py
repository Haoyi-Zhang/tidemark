"""Derive native tables/cost summaries without modifying old result macros."""
import argparse
import collections
import gzip
import json
from pathlib import Path


def derive(run):
    with gzip.open(run / "raw.jsonl.gz", "rt", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    saved = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    policy = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        if r["kind"] == "attempt" and r["status"] == "embedded":
            for k in ("pre_jit_seconds", "whole_case_seconds", "whole_case_process_seconds"):
                policy[r["policy"]][k] += r[k]
            policy[r["policy"]]["feasible_cases"] += 1
    return {"saved_counts": saved["counts"], "policy_cost_sums": dict(policy),
            "raw_rows": len(rows), "raw_gzip_bytes": (run / "raw.jsonl.gz").stat().st_size,
            "timing_scope": "Whole feasible case: embed/range admission/replay/check/extract, two interpreters over all 98 states, LLVM verification/object emission/MCJIT at backend-opt0 and IR-pipeline-O2, 196 target calls, and two rehashed module checks. Excludes source generation/admission/98 native source calls, compression/writing, capacity rejects, and summary aggregation. Case CPU is process CPU; no pinned/isolated claim. Pre-JIT includes interpreter checks; not an embedding-only timer.",
            "scope": "Object byte sums are experiment artifacts, not deployment, DB, WAL, runtime memory or lifecycle footprint."}, saved


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--paper", type=Path, required=True)
    a = p.parse_args()
    derived, saved = derive(a.run)
    (a.run / "cost-summary.json").write_text(json.dumps(derived, indent=2) + "\n", encoding="utf-8")
    lines = [r"\begin{tabular}{@{}lrrrrr@{}}", r"\toprule",
             r"Policy & Sites & User bits & 8-bit success & Feasible & Case wall (s)\\", r"\midrule"]
    for name, label in (("mode4", "Mode 4"), ("source-first", "Source-first"),
                        ("singleton-first", "Singleton-first"), ("adjacent-only", "Adjacent-only")):
        r = saved["policies"][name]
        elapsed = derived["policy_cost_sums"][name]["whole_case_seconds"]
        lines.append(f"{label} & {r['sites']:,} & {r['user_bits']:,} & {r['fixed8_success']}/96 & {r['embeddings']} & {elapsed:.3f}" + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (a.paper / "tables/native-comparison.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(derived, indent=2))
