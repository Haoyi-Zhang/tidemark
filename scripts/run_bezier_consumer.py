"""Upstream-derived coefficient task; no third-party code is executed."""
import argparse
from dataclasses import replace
import itertools
import json
from pathlib import Path
from tidemark import core, native, overlap, python_subset, reference

ROOT = Path(__file__).resolve().parents[1]


def study():
    text = (ROOT / "examples/bezier_coefficients.py").read_text(encoding="utf-8")
    p = python_subset.translate(text)
    fn = python_subset.validated_function(text)
    names = [n for n, _ in p.params]
    box = {n: [0, 1] for n in names[:-1]} | {"which": [0, 7]}
    native.admit(p, box)
    states = [list(x) + [j] for x in itertools.product((0, 1), repeat=8) for j in range(8)]
    expected = []
    for args in states:
        x1, x2, x3, x4, y1, y2, y3, y4, j = args
        oracle = [-x1+3*x2-3*x3+x4, 3*x1-6*x2+3*x3, -3*x1+3*x2, x1,
                  -y1+3*y2-3*y3+y4, 3*y1-6*y2+3*y3, -3*y1+3*y2, y1][j]
        params = dict(zip(names, args))
        if not (fn(*args) == core.evaluate_program(p, params, {})[0]
                == reference.evaluate(p.to_obj(), params, {})[0] == oracle):
            raise ValueError("source/expanded polynomial mismatch")
        expected.append(oracle)
    sb = core.serialize_program(p)
    rows, targets, omissions = [], [], []
    for policy in overlap.POLICIES:
        sites = overlap.select(core.discover_candidates(p), policy)
        accepted = 0
        for payload in ((0,), (1,)):
            if core.payload_capacity(len(sites)) < 1:
                targets.append({"policy": policy, "payload": list(payload), "decision": "capacity-rejection"})
                continue
            q, cert = overlap.embed(p, payload, policy)
            qb = core.serialize_program(q)
            if overlap.check(sb, qb, cert, policy) != payload or overlap.reference_check(sb, qb, cert, policy) != payload:
                raise ValueError("checker disagreement")
            values = []
            for args, expected_value in zip(states, expected):
                params = dict(zip(names, args))
                value = core.evaluate_program(q, params, {})[0]
                if value != expected_value or reference.evaluate(q.to_obj(), params, {})[0] != value:
                    raise ValueError("target result")
                values.append(value)
            # A return outside the selected fragments still exposes the frame.
            bad = replace(q, result="x1")
            bad_bytes = core.serialize_program(bad)
            rehashed = json.loads(cert)
            rehashed["target_sha256"] = core.digest_bytes(bad_bytes)
            rehashed = core.canonical_json(rehashed)
            if overlap.extract(p, bad, policy) != payload:
                raise ValueError("omission witness must preserve extraction")
            differing = [i for i, args in enumerate(states)
                         if core.evaluate_program(bad, dict(zip(names, args)), {})[0] != expected[i]]
            if not differing:
                raise ValueError("omission has no behavioral witness")
            decisions = []
            for checker in (overlap.check, overlap.reference_check):
                try:
                    checker(sb, bad_bytes, rehashed, policy)
                except (core.TideMarkError, reference.RefError):
                    decisions.append("rejected")
                else:
                    raise ValueError("whole-target omission accepted")
            omissions.append({"policy": policy, "payload": list(payload), "local_extraction": list(payload),
                              "target": bad.to_obj(), "certificate": json.loads(rehashed),
                              "different_inputs": len(differing), "first_input": states[differing[0]],
                              "whole_target_checkers": decisions})
            targets.append({"policy": policy, "payload": list(payload), "decision": "accepted",
                            "target": q.to_obj(), "certificate": json.loads(cert), "results": values})
            accepted += 1
        rows.append({"policy": policy, "sites": len(sites), "user_bits": core.payload_capacity(len(sites)),
                     "accepted": accepted, "attempts": 2})
    summary = {"source_kind": "upstream_derived_integer_coordinate_adaptation",
               "upstream": "fonttools/fonttools@4.60.1:Lib/fontTools/misc/bezierTools.py:890-901",
               "source_commands": len(p.commands), "inputs": len(states), "policies": rows,
               "targets": sum(r["accepted"] for r in rows), "attempts": len(targets),
               "capacity_rejections": sum(t["decision"] != "accepted" for t in targets),
               "omission_witnesses": len(omissions), "semantic_discrepancies": 0,
               "native_execution": False}
    raw = {"source_python": text, "source_program": p.to_obj(), "box": box, "states": states,
           "expected": expected, "targets": targets, "omissions": omissions}
    return summary, raw


def table(summary, path):
    labels = {"mode4": "Mode 4", "source-first": "Source-first", "singleton-first": "Singleton-first", "adjacent-only": "Adjacent-only"}
    lines = [r"\begin{tabular}{@{}lrrr@{}}", r"\toprule", r"Policy & Sites & User bits & One-bit requests\\", r"\midrule"]
    for row in summary["policies"]:
        lines.append(f'{labels[row["policy"]]} & {row["sites"]} & {row["user_bits"]} & {row["accepted"]}/2'+r"\\")
    path.write_text("\n".join(lines+[r"\bottomrule", r"\end{tabular}"])+"\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path)
    ap.add_argument("--verify", type=Path)
    ap.add_argument("--table", type=Path)
    a = ap.parse_args()
    summary, raw = study()
    if a.verify:
        for name, current in (("summary.json", summary), ("records.json", raw)):
            if json.loads((a.verify/name).read_text(encoding="utf-8")) != current:
                raise ValueError("saved evidence differs: " + name)
    if a.output:
        a.output.mkdir(parents=True, exist_ok=False)
        for name, current in (("summary.json", summary), ("records.json", raw)):
            (a.output/name).write_text(json.dumps(current, indent=2)+"\n", encoding="utf-8")
    if a.table:
        table(summary, a.table)
    print(json.dumps(summary))
