#!/usr/bin/env python3
"""Portable, raw-first, same-goal owned-IR selector comparison.

Default output is separate from every retained quota/LLVM measurement. An
existing run is never overwritten. --verify-saved rechecks saved concrete inputs
and targets, binds source versions, and derives the summary again without writes.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import platform
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tidemark import core, reference, overlap

VERSION_FILES = ("src/tidemark/core.py", "src/tidemark/reference.py",
                 "src/tidemark/overlap.py", "scripts/run_overlap_comparison.py")
FAILURES = ("candidate_differences", "schedule_differences", "optimum_differences",
            "target_differences", "check_failures", "extraction_failures",
            "semantic_differences", "reference_evaluator_differences",
            "accepted_mutations", "reference_accepted_mutations", "unexpected_rejections")


def row(handle, value):
    handle.write(core.canonical_json(value).decode("utf-8") + "\n")


def rows(path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def verdict(fn):
    try:
        return {"accepted": True, "payload": list(fn()), "reason": "accepted"}
    except (ValueError, TypeError, KeyError) as exc:
        return {"accepted": False, "payload": None, "reason": f"{type(exc).__name__}:{exc}"}


def observation(obs):
    return {"result": obs[0], "store": obs[1], "trace": list(obs[2])}


def descriptors(sites):
    return [json.loads(site.descriptor_bytes) for site in sites]


def version_hashes():
    return {name: core.digest_bytes((ROOT / name).read_bytes()) for name in VERSION_FILES}


def summarize(output):
    totals = collections.Counter({key: 0 for key in FAILURES})
    policies = {p: collections.Counter() for p in overlap.POLICIES}
    families = collections.defaultdict(collections.Counter)
    for source in rows(output / "sources.jsonl"):
        totals["programs"] += 1
        totals["bindings"] += len(source["source"]["commands"])
        totals["candidates"] += len(source["candidates"])
        totals["candidate_differences"] += not source["candidates_equal"]
        totals["overlap_programs"] += source["overlap"]
        totals["conflict_pairs"] += source["conflict_pairs"]
        for family, start, end, *_ in source["candidates"]:
            totals["candidate_" + family] += 1
        for p, info in source["policies"].items():
            bucket = policies[p]
            bucket["programs"] += 1
            bucket["selected_sites"] += len(info["schedule"])
            bucket["user_capacity_bits"] += info["capacity"]
            bucket["discarded_candidates"] += len(source["candidates"]) - len(info["schedule"])
            bucket["optimal_programs"] += len(info["schedule"]) == source["optimum"]
            bucket["site_deficit"] += source["optimum"] - len(info["schedule"])
            totals["schedule_differences"] += not info["reference_schedule_equal"]
            if p == "mode4":
                totals["optimum_differences"] += len(info["schedule"]) != source["optimum"]
            families[source["family"]][p + "_sites"] += len(info["schedule"])
            families[source["family"]][p + "_capacity"] += info["capacity"]
    for r in rows(output / "instances.jsonl"):
        totals["attempts"] += 1
        bucket = policies[r["policy"]]
        if r["status"] == "capacity-rejected":
            totals["capacity_rejections"] += 1
            bucket[r["goal"] + "_capacity_rejections"] += 1
            totals["unexpected_rejections"] += not r["expected_capacity_rejection"]
            continue
        totals["embeddings"] += 1
        bucket[r["goal"] + "_embeddings"] += 1
        totals["target_differences"] += not r["reference_target_equal"]
        totals["check_failures"] += not (r["production"]["accepted"] and r["reference"]["accepted"])
        totals["extraction_failures"] += not (r["extracted"] == r["payload"] == r["production"]["payload"] == r["reference"]["payload"])
        for family, bit in r["orientations"]:
            totals[f"oriented_{family}_{bit}"] += 1
    for r in rows(output / "executions.jsonl"):
        totals["full_comparisons"] += 1
        totals["semantic_differences"] += r["source"] != r["target"]
        totals["reference_evaluator_differences"] += not (
            r["source"] == r["reference_source"] and r["target"] == r["reference_target"])
    for r in rows(output / "mutations.jsonl"):
        totals["mutations"] += 1
        totals["accepted_mutations"] += r["production"]["accepted"]
        totals["reference_accepted_mutations"] += r["reference"]["accepted"]
    return {"counts": dict(totals), "policies": {p: dict(b) for p, b in policies.items()},
            "families": {p: dict(b) for p, b in families.items()}}


def scientific_failures(summary):
    c = summary["counts"]
    result = [key for key in FAILURES if c.get(key) != 0]
    if c.get("programs") != len(overlap.FAMILIES) * len(overlap.SIZES) * len(overlap.VARIANTS):
        result.append("programs:count")
    if c.get("attempts") != c.get("programs", 0) * len(overlap.POLICIES) * 3:
        result.append("attempts:count")
    if c.get("full_comparisons") != c.get("embeddings", 0) * len(overlap.STATES):
        result.append("full_comparisons:count")
    if c.get("mutations") != c.get("embeddings", 0) * 2:
        result.append("mutations:count")
    if c.get("overlap_programs", 0) <= 0 or c.get("conflict_pairs", 0) <= 0:
        result.append("no-overlap")
    if summary["policies"]["mode4"].get("discarded_candidates", 0) <= 0:
        result.append("no-discarded-candidates")
    # Reaching both representations matters for the actual decoding path.
    for family in ("identity", "operand", "adjacent"):
        for bit in (0, 1):
            if c.get(f"oriented_{family}_{bit}", 0) <= 0:
                result.append(f"missing-orientation:{family}:{bit}")
    return result


def run(output):
    if output.exists() and any(output.iterdir()):
        raise ValueError("refusing to overwrite an existing run; use --verify-saved")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with ((output / "sources.jsonl").open("w", encoding="utf-8") as sh,
          (output / "instances.jsonl").open("w", encoding="utf-8") as ih,
          (output / "executions.jsonl").open("w", encoding="utf-8") as eh,
          (output / "mutations.jsonl").open("w", encoding="utf-8") as mh):
        for index, (name, family, size, variant, source) in enumerate(overlap.sources()):
            # Save all candidates, including discarded orientations/descriptors.
            source_bytes = core.serialize_program(source)
            raw = reference.parse(source_bytes)
            candidates = core.discover_candidates(source)
            ref_candidates = reference.candidates(raw)
            desc = descriptors(candidates)
            optimum = overlap.optimum_count(ref_candidates, len(source.commands))
            conflicts = sum(not (a.end < b.start or b.end < a.start)
                            for i, a in enumerate(candidates) for b in candidates[i + 1:])
            schedules = {p: overlap.select(candidates, p) for p in overlap.POLICIES}
            ref_schedules = {p: overlap.reference_select(ref_candidates, p) for p in overlap.POLICIES}
            row(sh, {"program_id": name, "family": family, "body_size": size,
                     "variant": variant, "source": raw, "candidates": desc,
                     "candidates_equal": core.canonical_json(desc) == reference.canon(ref_candidates),
                     "optimum": optimum, "conflict_pairs": conflicts, "overlap": conflicts > 0,
                     "policies": {p: {"schedule": descriptors(schedules[p]),
                         "capacity": core.payload_capacity(len(schedules[p])),
                         "reference_schedule_equal": core.canonical_json(descriptors(schedules[p])) == reference.canon(ref_schedules[p])}
                         for p in overlap.POLICIES}})
            source_obs = [observation(core.evaluate_program(source, params, store)) for params, store in overlap.STATES]
            ref_source_obs = [observation(reference.evaluate(raw, params, store)) for params, store in overlap.STATES]
            for p in overlap.POLICIES:
                capacity = core.payload_capacity(len(schedules[p]))
                # Empty and fixed-8 goals are identical across policies. The
                # saturation goal deliberately differs and measures capacity.
                goals = (("empty", ()), ("fixed8", tuple((index + j) % 2 for j in range(8))),
                         ("saturation", tuple((index + j) % 2 for j in range(capacity))))
                for goal, payload in goals:
                    instance_id = f"{name}/{p}/{goal}"
                    try:
                        target, cert = overlap.embed(source, payload, p)
                    except core.TideMarkError as exc:
                        row(ih, {"instance_id": instance_id, "program_id": name,
                            "policy": p, "goal": goal, "payload": list(payload),
                            "status": "capacity-rejected", "reason": str(exc),
                            "expected_capacity_rejection": len(payload) > capacity})
                        continue
                    target_bytes = core.serialize_program(target)
                    ref_target = reference.replay(raw, ref_schedules[p], reference.frame(list(payload), len(ref_schedules[p])))
                    row(ih, {"instance_id": instance_id, "program_id": name, "policy": p,
                        "goal": goal, "payload": list(payload), "status": "embedded",
                        "target": target.to_obj(), "certificate": json.loads(cert),
                        "reference_target_equal": target_bytes == reference.canon(ref_target),
                        "extracted": list(overlap.extract(source, target, p)),
                        "orientations": [[s.family, b] for s, b in zip(schedules[p], core.frame_bits(payload, len(schedules[p])))],
                        "production": verdict(lambda: overlap.check(source_bytes, target_bytes, cert, p)),
                        "reference": verdict(lambda: overlap.reference_check(source_bytes, target_bytes, cert, p))})
                    for state, (params, store) in enumerate(overlap.STATES):
                        row(eh, {"instance_id": instance_id, "state": state,
                            "params": params, "initial_store": store,
                            "source": source_obs[state], "reference_source": ref_source_obs[state],
                            "target": observation(core.evaluate_program(target, params, store)),
                            "reference_target": observation(reference.evaluate(target.to_obj(), params, store))})
                    for category, bad_target, bad_cert in overlap.mutations(target, cert):
                        row(mh, {"instance_id": instance_id, "category": category,
                            "target": json.loads(bad_target), "certificate": json.loads(bad_cert),
                            "production": verdict(lambda: overlap.check(source_bytes, bad_target, bad_cert, p)),
                            "reference": verdict(lambda: overlap.reference_check(source_bytes, bad_target, bad_cert, p))})
            if (index + 1) % 24 == 0:
                print(f"{index + 1}/192 owned sources recorded", flush=True)
    summary = summarize(output)
    summary.update({"schema": "tidemark-owned-overlap-evaluation-1",
                    "environment": {"python": platform.python_version(), "platform": platform.platform(),
                                    "executable": sys.executable, "elapsed_seconds": time.perf_counter() - started},
                    "source_versions_sha256": version_hashes(),
                    "protocol": {"families": overlap.FAMILIES, "body_sizes": overlap.SIZES,
                                 "variants": overlap.VARIANTS, "states": overlap.STATES,
                                 "fixed_request_bits": 8, "goals": ["empty", "fixed8", "saturation"]},
                    "scope": "Constructed owned terminating IR, no LLVM execution or natural software distribution; baseline code shares carrier primitives, not an independent proof kernel."})
    summary["scientific_failure_gates"] = scientific_failures(summary)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def verify_saved(output):
    saved = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    if saved["source_versions_sha256"] != version_hashes():
        raise ValueError("saved run source version differs from current implementation")
    source_map = {}
    for r in rows(output / "sources.jsonl"):
        source = core.Program.from_obj(r["source"])
        candidates = core.discover_candidates(source)
        refs = reference.candidates(r["source"])
        if descriptors(candidates) != r["candidates"] or reference.canon(refs) != core.canonical_json(r["candidates"]):
            raise ValueError("saved candidate mismatch: " + r["program_id"])
        if overlap.optimum_count(refs, len(source.commands)) != r["optimum"]:
            raise ValueError("saved optimum mismatch")
        for p in overlap.POLICIES:
            if descriptors(overlap.select(candidates, p)) != r["policies"][p]["schedule"]:
                raise ValueError("saved schedule mismatch")
        source_map[r["program_id"]] = source
    instance_map = {}
    for r in rows(output / "instances.jsonl"):
        source = source_map[r["program_id"]]
        if r["status"] == "capacity-rejected":
            try:
                overlap.embed(source, r["payload"], r["policy"])
            except core.TideMarkError:
                continue
            raise ValueError("saved capacity rejection now embeds")
        target, cert = overlap.embed(source, r["payload"], r["policy"])
        if target.to_obj() != r["target"] or json.loads(cert) != r["certificate"]:
            raise ValueError("saved target/certificate differs")
        args = core.serialize_program(source), core.serialize_program(target), cert, r["policy"]
        if list(overlap.check(*args)) != r["payload"] or list(overlap.reference_check(*args)) != r["payload"]:
            raise ValueError("saved extraction/check mismatch")
        instance_map[r["instance_id"]] = (source, target, r["policy"])
    for r in rows(output / "executions.jsonl"):
        source, target, _ = instance_map[r["instance_id"]]
        for key, fn, program in (("source", core.evaluate_program, source), ("target", core.evaluate_program, target),
                                 ("reference_source", reference.evaluate, source.to_obj()),
                                 ("reference_target", reference.evaluate, target.to_obj())):
            if observation(fn(program, r["params"], r["initial_store"])) != r[key]:
                raise ValueError("saved observation mismatch")
    for r in rows(output / "mutations.jsonl"):
        source, _, p = instance_map[r["instance_id"]]
        args = core.serialize_program(source), core.canonical_json(r["target"]), core.canonical_json(r["certificate"]), p
        for key, fn in (("production", overlap.check), ("reference", overlap.reference_check)):
            if verdict(lambda: fn(*args)) != r[key]:
                raise ValueError("saved mutation mismatch")
    actual = summarize(output)
    if any(actual[key] != saved[key] for key in actual):
        raise ValueError("saved raw/summary disagreement")
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "results/current/overlap")
    parser.add_argument("--verify-saved", action="store_true")
    args = parser.parse_args()
    summary = verify_saved(args.output_dir) if args.verify_saved else run(args.output_dir)
    failures = scientific_failures(summary)
    print(json.dumps({"counts": summary["counts"], "policies": summary["policies"],
                      "scientific_failure_gates": failures}, indent=2, sort_keys=True))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
