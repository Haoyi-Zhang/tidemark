"""One owned application-shaped source, not a production-software sample."""
from pathlib import Path
import argparse
import itertools
import json
import platform
import sys
from tidemark import core, native, native_jit, overlap, python_subset, reference

ROOT = Path(__file__).resolve().parents[1]
BOX = {"units": [0, 5], "weight": [0, 4]}


def run():
    text = (ROOT / "examples/shipping_quote.py").read_text(encoding="utf-8")
    p = python_subset.translate(text)
    fn = python_subset.validated_function(text)
    states = list(itertools.product(range(6), range(5), (False, True)))
    expected = [fn(*args) for args in states]
    source_bytes = core.serialize_program(p)
    for args, result in zip(states, expected):
        params = dict(zip(("units", "weight", "priority"), args))
        if core.evaluate_program(p, params, {})[0] != result or reference.evaluate(p.to_obj(), params, {})[0] != result:
            raise ValueError("source/adapter/interpreter discrepancy")
    native_jit.initialize()
    source_ir = native.lower(p, BOX)
    source_result, source_normalized, source_object = native_jit.execute(source_ir, states)
    if source_result != expected:
        raise ValueError("source native discrepancy")
    rows, policies = [], []
    candidates = core.discover_candidates(p)
    for policy in overlap.POLICIES:
        selected = overlap.select(candidates, policy)
        if core.payload_capacity(len(selected)) < 1:
            raise ValueError("declared one-bit request does not fit")
        records = []
        for message in ((0,), (1,)):
            q, ir, wrapper = native.embed(p, message, BOX, policy)
            target_bytes = core.serialize_program(q)
            if native.check(source_bytes, target_bytes, ir, wrapper) != message:
                raise ValueError("exact wrapper replay")
            certificate = core.canonical_json(json.loads(wrapper)["core_certificate"])
            if overlap.reference_check(source_bytes, target_bytes, certificate, policy) != message:
                raise ValueError("raw-tree checker")
            for args, result in zip(states, expected):
                params = dict(zip(("units", "weight", "priority"), args))
                if core.evaluate_program(q, params, {})[0] != result or reference.evaluate(q.to_obj(), params, {})[0] != result:
                    raise ValueError("target interpreter discrepancy")
            values, normalized, obj = native_jit.execute(ir, states)
            optimized_values, optimized_ir, optimized_obj = native_jit.execute(ir, states, optimize=True)
            if values != expected or optimized_values != expected:
                raise ValueError("target native discrepancy")
            records.append({"policy": policy, "payload": list(message), "target": q.to_obj(),
                            "wrapper": json.loads(wrapper), "prepass_ir": ir.decode("ascii"),
                            "optimized_ir": optimized_ir, "result": values,
                            "optimized_result": optimized_values,
                            "object_bytes": len(obj), "optimized_object_bytes": len(optimized_obj)})
        different_prepass = records[0]["prepass_ir"] != records[1]["prepass_ir"]
        equal_optimized = records[0]["optimized_ir"] == records[1]["optimized_ir"]
        if not different_prepass:
            raise ValueError("prepass orientations not distinct")
        policies.append({"policy": policy, "sites": len(selected),
                         "capacity": core.payload_capacity(len(selected)), "messages": 2,
                         "exact_ir_decodes": 2, "different_prepass_ir": different_prepass,
                         "equal_optimized_ir": equal_optimized})
        rows.extend(records)
    summary = {"source_kind": "one_owned_shipping_quote_not_external_deployment",
               "source_commands": len(p.commands), "input_states": len(states),
               "policies": policies, "targets": len(rows), "native_calls": len(states) * (1 + 2*len(rows)),
               "optimized_collision_pairs": sum(x["equal_optimized_ir"] for x in policies),
               "semantic_discrepancies": 0, "python": sys.version.split()[0],
               "platform": platform.platform(), "llvm": list(native_jit.llvm.llvm_version_info)}
    details = {"source_python": text, "source_ir": source_ir.decode("ascii"),
               "source_program": p.to_obj(), "box": BOX, "states": states,
               "source_result": source_result, "source_object_bytes": len(source_object),
               "targets": rows}
    return summary, details


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--compare", type=Path)
    a = ap.parse_args()
    if a.output.exists():
        raise ValueError("fresh output required")
    summary, details = run()
    if a.compare:
        saved = json.loads(a.compare.read_text(encoding="utf-8"))
        for key in ("source_kind", "source_commands", "input_states", "policies", "targets",
                    "native_calls", "optimized_collision_pairs", "semantic_discrepancies"):
            if summary[key] != saved[key]:
                raise ValueError("scientific summary differs: " + key)
    a.output.mkdir(parents=True)
    for name, value in (("summary.json", summary), ("records.json", details)):
        (a.output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))
