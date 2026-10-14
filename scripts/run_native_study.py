"""Raw-first owned pure-IR native campaign; no old pipeline writes.

Requires optional llvmlite 0.46.0 and a fresh explicit output directory.
--verify-saved authorizes execution only after exact reconstruction of owned
source/target IR. It reruns LLVM, not merely a JSON count check.
"""
import argparse
import base64
import collections
import gzip
import itertools
import json
from pathlib import Path
import platform
import sys
import time
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tidemark import core, reference, overlap, native, native_jit
import llvmlite
from llvmlite import binding as llvm

FILES = ("src/tidemark/core.py", "src/tidemark/reference.py", "src/tidemark/overlap.py",
         "src/tidemark/native.py", "src/tidemark/native_jit.py", "scripts/run_native_study.py")
BOX = {"a": [-3, 3], "b": [-3, 3]}
INPUTS = list(itertools.product(range(-3, 4), range(-3, 4), (0, 1)))


def sources(small):
    E, C, T = core.Expr, core.Command, core.Type
    for family in ("identity", "operand", "adjacent", "nested"):
        for size in ((6,) if small else (6, 12, 24, 48)):
            for variant in ((0,) if small else range(6)):
                commands, typed = [], []
                for i in range(size):
                    name = f"v{size-i:03d}_{variant}"
                    a, b, flag = E.var("a"), E.var("b"), E.var("flag")
                    t = T.INT
                    if family == "identity":
                        e = flag if i % 3 == 0 else (E.integer(i) if i % 3 == 1 else a)
                        t = T.BOOL if i % 3 == 0 else T.INT
                    elif family == "operand":
                        op = ("add", "mul", "eq")[(i + variant) % 3]
                        e = E.binary(op, a, b) if i % 2 else E.binary(op, b, a)
                        t = T.BOOL if op == "eq" else T.INT
                    elif family == "adjacent":
                        # Every fourth command consumes a prior result; all
                        # independent gaps overlap. No singleton carriers here.
                        left = E.var(typed[-1][0]) if i % 4 == 1 else a
                        e = E.binary("sub", left, E.integer(i + variant + 1))
                    else:
                        e = (E.binary("add", E.binary("sub", a, E.integer(i)),
                                      E.choose(flag, b, E.integer(variant))) if i % 2 == 0
                             else E.choose(E.binary("lt", a, b), E.logical_not(flag),
                                           E.binary("eq", flag, E.boolean(True))))
                        t = T.INT if i % 2 == 0 else T.BOOL
                    commands.append(C(name, e))
                    typed.append((name, t))
                result = "a"
                for i, (name, t) in enumerate(typed):
                    term = E.var(name) if t == T.INT else E.choose(E.var(name), E.integer(1), E.integer(0))
                    out = f"out{i}"
                    commands.append(C(out, E.binary("sub", E.var(result), term)))
                    result = out
                yield f"{family}-{size}-{variant}", core.Program(
                    (("a", T.INT), ("b", T.INT), ("flag", T.BOOL)), (), tuple(commands), result)


def hashes():
    return {f: core.digest_bytes((ROOT / f).read_bytes()) for f in FILES}


def oracle(p):
    # Entire declared finite input box, two independent interpreters, full pure
    # observation (empty store/trace explicitly checked), not sampled states.
    result = []
    for a, b, flag in INPUTS:
        args = {"a": a, "b": b, "flag": bool(flag)}
        prod = core.evaluate_program(p, args, {})
        ref = reference.evaluate(p.to_obj(), args, {})
        if prod != ref or prod[1] or prod[2]:
            raise AssertionError("pure interpreter correspondence")
        result.append(int(prod[0]))
    return result


def encode_obj(data):
    return base64.b64encode(data).decode("ascii")


def mutations(source, target, ir, wrapper):
    # Owned local arithmetic edits. Rehashing the supplied module must NOT
    # authorize an unrelated return or an additional instruction.
    w = json.loads(wrapper)
    for name, changed in (("unrelated-return", ir[:ir.rfind(b"  ret i64 ")] + b"  ret i64 0\n}\n"),
                          ("extra-arithmetic", ir.replace(b"; end commands\n", b"; end commands\n  %extra = add i64 1, 1\n"))):
        w2 = dict(w, ir_sha256=core.digest_bytes(changed))
        try:
            native.check(core.serialize_program(source), core.serialize_program(target), changed, core.canonical_json(w2))
            rejected = False
        except ValueError:
            rejected = True
        yield {"category": name, "ir": changed.decode(), "wrapper": w2, "rejected": rejected}


def measure(name, source, policy, goal, payload, source_values):
    started, cpu = time.perf_counter(), time.process_time()
    try:
        target, ir, wrapper = native.embed(source, payload, BOX, policy)
    except core.TideMarkError as exc:
        capacity = core.payload_capacity(len(overlap.select(core.discover_candidates(source), policy)))
        if len(payload) <= capacity:
            raise
        return {"kind": "attempt", "id": name, "policy": policy, "goal": goal,
                "payload": list(payload), "status": "capacity-rejected", "reason": str(exc)}
    args = core.serialize_program(source), core.serialize_program(target), ir, wrapper
    if native.check(*args) != tuple(payload) or native.extract_ir(source, ir, BOX, policy) != tuple(payload):
        raise AssertionError("native wrapper or extraction")
    certificate = core.canonical_json(json.loads(wrapper)["core_certificate"])
    if overlap.reference_check(args[0], args[1], certificate, policy) != tuple(payload):
        raise AssertionError("reference certificate")
    expected = oracle(target)
    if expected != source_values:
        raise AssertionError("source target semantics")
    before_jit = time.perf_counter()
    values, normalized, obj = native_jit.execute(ir, INPUTS)
    optimized, opt_ir, opt_obj = native_jit.execute(ir, INPUTS, optimize=True)
    if values != expected or optimized != expected:
        raise AssertionError("native semantics")
    bad = list(mutations(source, target, ir, wrapper))
    if not all(r["rejected"] for r in bad):
        raise AssertionError("accepted rehashed module mutation")
    sites = overlap.select(core.discover_candidates(source), policy)
    return {"kind": "attempt", "id": name, "policy": policy, "goal": goal,
            "payload": list(payload), "status": "embedded", "target": target.to_obj(),
            "ir": ir.decode(), "wrapper": json.loads(wrapper),
            "orientations": [[s.family, b] for s, b in zip(sites, core.frame_bits(payload, len(sites)))],
            "oracle": expected, "native": values, "optimized_native": optimized,
            "parsed_ir": normalized, "optimized_ir": opt_ir,
            "object_base64": encode_obj(obj), "optimized_object_base64": encode_obj(opt_obj),
            "mutations": bad, "pre_jit_seconds": before_jit - started,
            "whole_case_seconds": time.perf_counter() - started,
            "whole_case_process_seconds": time.process_time() - cpu}


def summarize(rows):
    counts = collections.Counter()
    policies = {p: collections.Counter() for p in overlap.POLICIES}
    groups = collections.defaultdict(lambda: collections.defaultdict(set))
    for r in rows:
        if r["kind"] == "source":
            counts["sources"] += 1
            counts["candidates"] += len(r["candidates"])
            counts["conflicting_pairs"] += r["conflicts"]
            counts["overlap_sources"] += r["conflicts"] > 0
            counts["native_source_calls"] += len(r["native_source"])
            for p, v in r["policies"].items():
                policies[p]["sites"] += v["sites"]
                policies[p]["user_bits"] += v["capacity"]
                policies[p]["optimum_sources"] += v["sites"] == r["optimum"]
            continue
        counts["attempts"] += 1
        p = policies[r["policy"]]
        if r["status"] == "capacity-rejected":
            counts["capacity_rejections"] += 1
            p["rejected"] += 1
            continue
        counts["embeddings"] += 1
        p["embeddings"] += 1
        p["fixed8_success"] += r["goal"] == "fixed8"
        counts["native_target_calls"] += len(r["native"]) + len(r["optimized_native"])
        counts["mutations"] += len(r["mutations"])
        counts["accepted_mutations"] += sum(not b["rejected"] for b in r["mutations"])
        counts["semantic_differences"] += sum(a != b or a != c for a, b, c in zip(r["oracle"], r["native"], r["optimized_native"]))
        counts["object_bytes"] += len(base64.b64decode(r["object_base64"]))
        counts["optimized_object_bytes"] += len(base64.b64decode(r["optimized_object_base64"]))
        for family, bit in r["orientations"]:
            counts[f"orientation_{family}_{bit}"] += 1
        groups[(r["id"], r["policy"])][r["optimized_ir"]].add(tuple(r["payload"]))
    # A collision is a pair of different actual messages, not just failure of
    # the comment-based decoder after the LLVM pretty printer strips comments.
    counts["optimized_distinct_message_collision_pairs"] = sum(
        len(msgs) * (len(msgs) - 1) // 2 for bucket in groups.values() for msgs in bucket.values())
    return {"counts": dict(counts), "policies": {p: dict(c) for p, c in policies.items()}}


def run(out, small):
    if out.exists() and any(out.iterdir()):
        raise ValueError("fresh output required")
    out.mkdir(parents=True, exist_ok=True)
    native_jit.initialize()
    start = time.perf_counter()
    rows = []
    with gzip.open(out / "raw.jsonl.gz", "wt", encoding="utf-8") as f:
        def save(r):
            f.write(core.canonical_json(r).decode() + "\n")
            f.flush()
            rows.append(r)
        for name, source in sources(small):
            candidates = core.discover_candidates(source)
            refs = reference.candidates(source.to_obj())
            assert core.canonical_json([json.loads(s.descriptor_bytes) for s in candidates]) == reference.canon(refs)
            values = oracle(source)
            source_ir = native.lower(source, BOX)
            actual, parsed, obj = native_jit.execute(source_ir, INPUTS)
            assert actual == values
            optimum = overlap.optimum_count(refs, len(source.commands))
            plans = {p: overlap.select(candidates, p) for p in overlap.POLICIES}
            assert len(plans["mode4"]) == len(plans["singleton-first"]) == optimum
            save({"kind": "source", "id": name, "source": source.to_obj(), "box": BOX,
                  "inputs": INPUTS, "range_audit": native.admit(source, BOX),
                  "source_ir": source_ir.decode(), "parsed_source_ir": parsed,
                  "source_object_base64": encode_obj(obj), "native_source": actual,
                  "candidates": refs, "optimum": optimum,
                  "conflicts": sum(not(a.end < b.start or b.end < a.start) for i, a in enumerate(candidates) for b in candidates[i+1:]),
                  "policies": {p: {"sites": len(s), "capacity": core.payload_capacity(len(s)),
                                    "schedule": [json.loads(x.descriptor_bytes) for x in s]} for p, s in plans.items()}})
            for p, sites in plans.items():
                capacity = core.payload_capacity(len(sites))
                goals = ([(f"all-{n}-{k}", bits) for n in range(capacity+1)
                          for k, bits in enumerate(itertools.product((0, 1), repeat=n))] if small else
                         [("empty", ()), ("fixed8", (0, 1)*4), ("saturation", tuple(i % 2 for i in range(capacity)))])
                for goal, payload in goals:
                    save(measure(name, source, p, goal, payload, values))
            print(name, flush=True)
    summary = summarize(rows)
    assert summary["counts"]["semantic_differences"] == summary["counts"]["accepted_mutations"] == 0
    summary.update(source_versions=hashes(), small=small, elapsed_seconds=time.perf_counter()-start,
                   environment={"python": platform.python_version(), "executable": sys.executable,
                                "platform": platform.platform(), "llvmlite": llvmlite.__version__,
                                "llvm": llvm.llvm_version_info, "triple": llvm.get_default_triple(),
                                "clocks": {n: vars(time.get_clock_info(n)) for n in ("perf_counter", "process_time", "time")}},
                   scope="Owned pure scalar generated IR; source indices/decoder PRE-optimization only; trusted LLVM/ABI; no external LLVM, general IR validation, object extraction, persistence or deployment benefit.")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def verify(out):
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    if summary["source_versions"] != hashes():
        raise ValueError("source version mismatch")
    native_jit.initialize()
    sources_by_id = {}
    expected_sources = dict(sources(summary["small"]))
    expected_attempts, seen_attempts = set(), set()
    rows = []
    with gzip.open(out / "raw.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rows.append(r)
            if r["kind"] == "source":
                source = core.Program.from_obj(r["source"])
                assert r["id"] not in sources_by_id
                assert source == expected_sources[r["id"]]
                assert r["box"] == BOX and r["inputs"] == [list(x) for x in INPUTS]
                assert native.lower(source, BOX).decode() == r["source_ir"]
                candidates = core.discover_candidates(source)
                assert [json.loads(s.descriptor_bytes) for s in candidates] == r["candidates"]
                assert r["optimum"] == overlap.optimum_count(r["candidates"], len(source.commands))
                assert r["conflicts"] == sum(not(a.end < b.start or b.end < a.start) for i, a in enumerate(candidates) for b in candidates[i+1:])
                for p in overlap.POLICIES:
                    plan = overlap.select(candidates, p)
                    cap = core.payload_capacity(len(plan))
                    assert r["policies"][p] == {"sites": len(plan), "capacity": cap,
                                              "schedule": [json.loads(s.descriptor_bytes) for s in plan]}
                    goals = ([f"all-{n}-{k}" for n in range(cap+1) for k in range(1 << n)]
                             if summary["small"] else ["empty", "fixed8", "saturation"])
                    expected_attempts.update((r["id"], p, goal) for goal in goals)
                assert native.admit(source, BOX) == r["range_audit"]
                values = oracle(source)
                actual, _, _ = native_jit.execute(r["source_ir"].encode(), INPUTS)
                assert values == actual == r["native_source"]
                sources_by_id[r["id"]] = source, values
                continue
            source, values = sources_by_id[r["id"]]
            identity = r["id"], r["policy"], r["goal"]
            assert identity not in seen_attempts
            seen_attempts.add(identity)
            current = measure(r["id"], source, r["policy"], r["goal"], r["payload"], values)
            for key in current:
                if key.endswith("seconds"):
                    continue
                assert current[key] == r[key], (r["id"], key)
    actual = summarize(rows)
    assert set(sources_by_id) == set(expected_sources) and seen_attempts == expected_attempts
    assert actual["counts"] == summary["counts"] and actual["policies"] == summary["policies"]
    return actual


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--small", action="store_true")
    parser.add_argument("--verify-saved", action="store_true")
    args = parser.parse_args()
    result = verify(args.out) if args.verify_saved else run(args.out, args.small)
    print(json.dumps(result, indent=2))
