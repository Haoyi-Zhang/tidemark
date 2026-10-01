"""Deterministic mode-4 evaluation with raw-first evidence capture.

The internal corpus is quota constructed.  Its family totals are design inputs,
not independent measurements of naturally occurring capacity.  The driver
therefore records exact inputs and decisions before computing aggregate tables.
"""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import itertools
import json
import math
import os
import platform
import random
import resource
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import reference
from .core import (
    CHECKER_VERSION,
    MODE_VERSION,
    SCHEMA,
    Certificate,
    Command,
    Effect,
    Expr,
    Program,
    Site,
    TideMarkError,
    Type,
    canonical_json,
    check_certificate,
    digest_bytes,
    discover_candidates,
    embed,
    evaluate_program,
    expr_free_vars,
    frame_bits,
    header_width,
    optimal_interval_count,
    payload_capacity,
    replay,
    select_sites,
    serialize_program,
    typecheck_program,
    unframe_bits,
)
from .corpus import FAMILIES, build_program, build_specs
from .structural import (
    Derivation,
    STEP_FIELDS,
    build_derivation,
    build_reference_derivation,
    verify_derivation_detailed,
)

ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW = ARTIFACT_ROOT / "data" / "raw" / "mode4"
DEFAULT_DERIVED = ARTIFACT_ROOT / "data" / "derived"
INPUT_COUNT = 8
FAMILIES_ORDER = tuple(FAMILIES)
CARRIER_FAMILIES = ("identity", "operand", "adjacent")


def _write_jsonl(handle: Any, value: Any) -> None:
    handle.write(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")


def _inputs(program_index: int) -> list[tuple[dict[str, int], dict[str, int]]]:
    return [({"arg": program_index * 17 + index - 31}, {"r": index - 4}) for index in range(INPUT_COUNT)]


def _payload(index: int, capacity: int) -> tuple[int, ...]:
    generator = random.Random(index * 0x9E3779B1 + 17)
    return tuple(generator.randrange(2) for _ in range(capacity))


def _quantile(values: Sequence[float], probability: float) -> float:
    """R-7 / NumPy-linear quantile with explicit interpolation."""
    if not values:
        raise ValueError("empty quantile input")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(indexed):
        end = start + 1
        while end < len(indexed) and indexed[end][1] == indexed[start][1]:
            end += 1
        average = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[indexed[position][0]] = average
        start = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("correlation requires paired values")
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_norm = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_norm = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    if left_norm == 0 or right_norm == 0:
        return float("nan")
    return numerator / (left_norm * right_norm)


def _spearman(left: Sequence[float], right: Sequence[float]) -> float:
    return _pearson(_average_ranks(left), _average_ranks(right))


def _observation_obj(observation: tuple[Any, dict[str, Any], tuple[Any, ...]]) -> dict[str, Any]:
    result, store, trace = observation
    return {"result": result, "store": store, "trace": list(trace)}


def _observation_hash(observation: tuple[Any, dict[str, Any], tuple[Any, ...]]) -> str:
    return hashlib.sha256(canonical_json(_observation_obj(observation))).hexdigest()


def _site_obj(site: Site) -> dict[str, Any]:
    return {
        "family": site.family,
        "interval": [site.start, site.end],
        "orientation0": [command.to_obj() for command in site.orientation0],
        "orientation1": [command.to_obj() for command in site.orientation1],
    }


def _reference_signature(sites: Sequence[tuple[Any, ...]]) -> list[tuple[str, int, int]]:
    return [(site[0], site[1], site[2]) for site in sites]


def _production_signature(sites: Sequence[Site]) -> list[tuple[str, int, int]]:
    return [(site.family, site.start, site.end) for site in sites]


def _length_prefixed_hash(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(len(chunk).to_bytes(8, "big"))
        digest.update(chunk)
    return digest.hexdigest()


def _descriptor_rich_certificate_bytes(certificate: Certificate, sites: Sequence[Site]) -> bytes:
    value = certificate.to_obj()
    value["sites"] = [
        {
            "family": site.family,
            "interval": [site.start, site.end],
            "orientation0_sha256": hashlib.sha256(
                canonical_json([command.to_obj() for command in site.orientation0])
            ).hexdigest(),
            "orientation1_sha256": hashlib.sha256(
                canonical_json([command.to_obj() for command in site.orientation1])
            ).hexdigest(),
        }
        for site in sites
    ]
    return canonical_json(value)


def _mutation_cases(
    source: Program,
    target: Program,
    certificate: Certificate,
) -> list[tuple[str, bytes, bytes, bytes, dict[str, Any]]]:
    source_bytes = serialize_program(source)
    target_bytes = serialize_program(target)
    base_obj = certificate.to_obj()
    cases: list[tuple[str, bytes, bytes, bytes, dict[str, Any]]] = []

    def cert_case(category: str, value: dict[str, Any], detail: Mapping[str, Any] | None = None) -> None:
        cases.append((category, source_bytes, target_bytes, canonical_json(value), dict(detail or {})))

    value = dict(base_obj); value["mode"] = MODE_VERSION + "-unsupported"
    cert_case("unsupported_mode", value)
    value = dict(base_obj); value["checker"] = CHECKER_VERSION + "-unsupported"
    cert_case("unsupported_checker", value)
    value = dict(base_obj); value["schema"] = SCHEMA + "-unsupported"
    cert_case("unsupported_schema", value)
    value = dict(base_obj); value["source_sha256"] = "0" * 64
    cert_case("source_digest", value)
    value = dict(base_obj); value["target_sha256"] = "f" * 64
    cert_case("target_digest", value)
    value = dict(base_obj)
    payload = value["payload"]
    value["payload"] = ("1" if not payload else ("1" if payload[0] == "0" else "0") + payload[1:])
    cert_case("payload", value)
    value = dict(base_obj); value["unexpected"] = 1
    cert_case("unknown_field", value)
    noncanonical = b"{" + b" " + certificate.to_bytes()[1:]
    cases.append(("noncanonical_certificate", source_bytes, target_bytes, noncanonical, {}))

    changed_target_obj = target.to_obj()
    forged_name = "__forged_mode4"
    existing = {command[1] for command in changed_target_obj["commands"]}
    while forged_name in existing:
        forged_name += "x"
    changed_target_obj["commands"].append(["let", forged_name, ["int", 0]])
    changed_target_bytes = canonical_json(changed_target_obj)
    value = dict(base_obj); value["target_sha256"] = digest_bytes(changed_target_bytes)
    cases.append(("target_rehashed_nonreplay", source_bytes, changed_target_bytes, canonical_json(value), {"added_binding": forged_name}))

    changed_source_obj = source.to_obj()
    changed_source_obj["unexpected"] = 1
    changed_source_bytes = canonical_json(changed_source_obj)
    value = dict(base_obj); value["source_sha256"] = digest_bytes(changed_source_bytes)
    cases.append(("source_rehashed_malformed", changed_source_bytes, target_bytes, canonical_json(value), {"extra_source_field": "unexpected"}))
    return cases


def _mutate_derivation(derivation: Derivation, category: str) -> tuple[Derivation | None, bool, str]:
    value = derivation.to_obj()
    if category == "source_hash":
        value["source_hash"] = "0" * 64
    elif category == "target_hash":
        value["target_hash"] = "f" * 64
    elif category == "selected":
        if value["selected"]:
            value["selected"][0][1] += 1
        else:
            value["selected"] = [["identity", 0, 0]]
    elif category == "framed_bits":
        if value["framed_bits"]:
            value["framed_bits"][0] = 1 - value["framed_bits"][0]
        else:
            value["framed_bits"] = [0]
    elif category == "delete_step":
        if not value["steps"]:
            return None, False, "no_steps"
        del value["steps"][0]
    elif category in {"family", "interval", "bit", "before_sha256", "after_sha256"}:
        if not value["steps"]:
            return None, False, "no_steps"
        step = value["steps"][0]
        if category == "family": step["family"] = "unknown"
        elif category == "interval": step["interval"][0] += 1
        elif category == "bit": step["bit"] = 1 - step["bit"]
        elif category == "before_sha256": step["before_sha256"] = "0" * 64
        elif category == "after_sha256": step["after_sha256"] = "f" * 64
    else:
        raise ValueError(category)
    return Derivation.from_obj(value), True, "mutated"


def _interval_optimum(intervals: Sequence[tuple[int, int, str]]) -> int:
    ordered = sorted(intervals, key=lambda interval: (interval[1], interval[0], interval[2]))
    optimum = [0] * (len(ordered) + 1)
    for index, interval in enumerate(ordered, start=1):
        predecessor = index - 1
        while predecessor > 0 and ordered[predecessor - 1][1] >= interval[0]:
            predecessor -= 1
        optimum[index] = max(optimum[index - 1], 1 + optimum[predecessor])
    return optimum[-1]


def _adjacent_classification(source: Program) -> list[dict[str, Any]]:
    analysis = typecheck_program(source)
    rows: list[dict[str, Any]] = []
    for index in range(len(source.commands) - 1):
        left = source.commands[index]
        right = source.commands[index + 1]
        left_vars = expr_free_vars(left.expr)
        right_vars = expr_free_vars(right.expr)
        left_effect = analysis.command_effects[index]
        right_effect = analysis.command_effects[index + 1]
        reasons: list[str] = []
        if right.name in left_vars:
            reasons.append("backward_dependency")
        if left.name in right_vars:
            reasons.append("forward_dependency")
        if not left_effect.commutes_with(right_effect):
            if left_effect.emits and right_effect.emits:
                reasons.append("trace_conflict")
            if (
                left_effect.writes & (right_effect.reads | right_effect.writes)
                or right_effect.writes & (left_effect.reads | left_effect.writes)
            ):
                reasons.append("state_conflict")
        if canonical_json(left.to_obj()) == canonical_json(right.to_obj()):
            reasons.append("identical_command_encoding")
        legal = not reasons
        rows.append({
            "pair_index": index,
            "left_name": left.name,
            "right_name": right.name,
            "left_command": left.to_obj(),
            "right_command": right.to_obj(),
            "left_effect": left_effect.to_obj(),
            "right_effect": right_effect.to_obj(),
            "legal": legal,
            "reasons": reasons or ["legal"],
        })
    return rows


def _environment() -> dict[str, Any]:
    uname = platform.uname()
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "system": uname.system,
        "release": uname.release,
        "machine": uname.machine,
        "processor": uname.processor,
        "logical_cpu_count": os.cpu_count(),
        "rss_measure": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "rss_unit": "KiB on Linux",
        "timer": "time.perf_counter_ns",
        "quantile_method": "R-7 linear interpolation: position=(n-1)*p",
        "correlation": "Spearman with average ranks for ties",
        "mode": MODE_VERSION,
        "checker": CHECKER_VERSION,
        "certificate_schema": SCHEMA,
    }


def run(raw_dir: Path | None = None, derived_dir: Path | None = None) -> dict[str, Any]:
    raw = Path(raw_dir or DEFAULT_RAW)
    derived = Path(derived_dir or DEFAULT_DERIVED)
    raw.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    owned = [
        "programs.jsonl", "instances.jsonl", "program-results.csv", "full-executions.csv",
        "local-carrier-checks.csv", "certificate-mutations.jsonl", "derivations.jsonl",
        "derivation-mutations.jsonl", "carrier-ablation.csv", "adjacent-pairs.jsonl",
        "interval-audit.csv", "frame-audit.csv",
    ]
    for name in owned:
        (raw / name).unlink(missing_ok=True)

    start = time.perf_counter()
    totals = Counter({
        # Explicit zeros belong in the derived record.  Counter otherwise omits
        # an unobserved failure class, which makes a missing measurement
        # indistinguishable from a measured zero.
        "accepted_mutations": 0,
        "reference_accepted_mutations": 0,
        "mutation_decision_differences": 0,
        "full_semantic_differences": 0,
        "reference_evaluator_differences": 0,
        "local_carrier_differences": 0,
        "reference_acceptance_differences": 0,
        "reference_selection_differences": 0,
        "reference_target_differences": 0,
        "derivation_producer_differences": 0,
        "derivation_target_differences": 0,
        "derivation_failures": 0,
        "accepted_proof_mutations": 0,
        "selector_differences": 0,
        "frame_failures": 0,
    })
    family_totals: dict[str, Counter[str]] = defaultdict(Counter)
    program_rows: list[dict[str, Any]] = []
    timing_values: dict[str, list[float]] = defaultdict(list)
    positive_rows: list[dict[str, Any]] = []
    source_chunks: list[bytes] = []
    mutation_indices = {
        family: set(range(FAMILIES_ORDER.index(family) * 40, FAMILIES_ORDER.index(family) * 40 + 20))
        for family in FAMILIES_ORDER
    }
    selected_mutation_indices = set().union(*mutation_indices.values())

    program_fields = [
        "program_id", "family", "index", "bindings", "candidates", "selected", "payload_bits",
        "header_bits", "operand", "identity", "adjacent", "source_bytes", "target_bytes",
        "certificate_bytes", "descriptor_rich_bytes", "analysis_ms", "discovery_ms", "selection_ms",
        "embed_ms", "check_ms", "reference_check_ms", "derivation_ms", "evaluation_ms", "peak_rss_kb_after_program",
    ]
    execution_fields = ["program_id", "input_id", "params_json", "store_json", "source_observation_sha256", "target_observation_sha256", "equal", "first_failure_reason"]
    local_fields = ["program_id", "site_ordinal", "family", "start", "end", "input_id", "orientation0_observation_sha256", "orientation1_observation_sha256", "equal", "first_failure_reason"]
    ablation_fields = ["program_id", "enabled_families", "selected_sites", "payload_bits"]
    interval_fields = ["mask", "candidate_count", "greedy_count", "optimum_count", "equal"]
    frame_fields = ["site_count", "bits", "valid", "payload", "first_failure_reason"]

    with (
        (raw / "programs.jsonl").open("w", encoding="utf-8") as programs_handle,
        (raw / "instances.jsonl").open("w", encoding="utf-8") as instances_handle,
        (raw / "program-results.csv").open("w", newline="", encoding="utf-8") as results_handle,
        (raw / "full-executions.csv").open("w", newline="", encoding="utf-8") as executions_handle,
        (raw / "local-carrier-checks.csv").open("w", newline="", encoding="utf-8") as local_handle,
        (raw / "certificate-mutations.jsonl").open("w", encoding="utf-8") as cert_mutation_handle,
        (raw / "derivations.jsonl").open("w", encoding="utf-8") as derivation_handle,
        (raw / "derivation-mutations.jsonl").open("w", encoding="utf-8") as derivation_mutation_handle,
        (raw / "carrier-ablation.csv").open("w", newline="", encoding="utf-8") as ablation_handle,
        (raw / "adjacent-pairs.jsonl").open("w", encoding="utf-8") as adjacent_handle,
    ):
        result_writer = csv.DictWriter(results_handle, fieldnames=program_fields)
        execution_writer = csv.DictWriter(executions_handle, fieldnames=execution_fields)
        local_writer = csv.DictWriter(local_handle, fieldnames=local_fields)
        ablation_writer = csv.DictWriter(ablation_handle, fieldnames=ablation_fields)
        result_writer.writeheader(); execution_writer.writeheader(); local_writer.writeheader(); ablation_writer.writeheader()

        for program_index, spec in enumerate(build_specs()):
            program_id = f"{spec.family}-{spec.index:02d}"
            source = build_program(spec)
            source_bytes = serialize_program(source)
            source_chunks.append(source_bytes)
            _write_jsonl(programs_handle, {"program_id": program_id, "spec": spec.__dict__, "program": source.to_obj()})

            tick = time.perf_counter_ns(); analysis = typecheck_program(source); analysis_ms = (time.perf_counter_ns() - tick) / 1e6
            tick = time.perf_counter_ns(); candidates = discover_candidates(source); discovery_ms = (time.perf_counter_ns() - tick) / 1e6
            tick = time.perf_counter_ns(); sites = select_sites(candidates); selection_ms = (time.perf_counter_ns() - tick) / 1e6
            if len(sites) != spec.capacity:
                raise AssertionError((program_id, "declared capacity", spec.capacity, len(sites)))
            capacity = payload_capacity(len(sites))
            payload = _payload(program_index, capacity)
            tick = time.perf_counter_ns(); target, certificate = embed(source, payload); embed_ms = (time.perf_counter_ns() - tick) / 1e6
            target_bytes = serialize_program(target)
            certificate_bytes = certificate.to_bytes()
            tick = time.perf_counter_ns(); recovered = check_certificate(source_bytes, target_bytes, certificate_bytes); check_ms = (time.perf_counter_ns() - tick) / 1e6
            if recovered != payload:
                raise AssertionError((program_id, "production extraction"))
            tick = time.perf_counter_ns(); reference_recovered = reference.check(source_bytes, target_bytes, certificate_bytes); reference_check_ms = (time.perf_counter_ns() - tick) / 1e6
            if reference_recovered != payload:
                totals["reference_acceptance_differences"] += 1
                raise AssertionError((program_id, "reference extraction"))

            source_obj = reference.parse(source_bytes)
            target_obj = reference.parse(target_bytes)
            reference_sites = reference.select(reference.candidates(source_obj))
            if _production_signature(sites) != _reference_signature(reference_sites):
                totals["reference_selection_differences"] += 1
                raise AssertionError((program_id, "selection disagreement"))
            reference_target = reference.replay(source_obj, reference_sites, reference.frame(list(payload), len(reference_sites)))
            if reference.canon(reference_target) != target_bytes:
                totals["reference_target_differences"] += 1
                raise AssertionError((program_id, "target disagreement"))

            _write_jsonl(instances_handle, {
                "program_id": program_id,
                "payload": "".join(map(str, payload)),
                "selected_sites": [_site_obj(site) for site in sites],
                "target": target.to_obj(),
                "certificate": certificate.to_obj(),
            })

            evaluation_started = time.perf_counter_ns()
            for input_id, (params, store) in enumerate(_inputs(program_index)):
                source_observation = evaluate_program(source, params, store)
                target_observation = evaluate_program(target, params, store)
                equal = source_observation == target_observation
                if not equal:
                    totals["full_semantic_differences"] += 1
                execution_writer.writerow({
                    "program_id": program_id,
                    "input_id": input_id,
                    "params_json": canonical_json(params).decode(),
                    "store_json": canonical_json(store).decode(),
                    "source_observation_sha256": _observation_hash(source_observation),
                    "target_observation_sha256": _observation_hash(target_observation),
                    "equal": int(equal),
                    "first_failure_reason": "" if equal else "observation_mismatch",
                })
                totals["full_executions"] += 1
                reference_source = reference.evaluate(source_obj, params, store)
                reference_target_observation = reference.evaluate(target_obj, params, store)
                totals["reference_evaluator_pairs"] += 1
                totals["reference_evaluator_calls"] += 2
                if reference_source != source_observation or reference_target_observation != target_observation:
                    totals["reference_evaluator_differences"] += 1
            evaluation_ms = (time.perf_counter_ns() - evaluation_started) / 1e6

            for site_ordinal, site in enumerate(sites):
                orientation0 = replay(source, (site,), (0,))
                orientation1 = replay(source, (site,), (1,))
                for input_id, (params, store) in enumerate(_inputs(program_index)):
                    observation0 = evaluate_program(orientation0, params, store)
                    observation1 = evaluate_program(orientation1, params, store)
                    equal = observation0 == observation1
                    if not equal:
                        totals["local_carrier_differences"] += 1
                    local_writer.writerow({
                        "program_id": program_id,
                        "site_ordinal": site_ordinal,
                        "family": site.family,
                        "start": site.start,
                        "end": site.end,
                        "input_id": input_id,
                        "orientation0_observation_sha256": _observation_hash(observation0),
                        "orientation1_observation_sha256": _observation_hash(observation1),
                        "equal": int(equal),
                        "first_failure_reason": "" if equal else "observation_mismatch",
                    })
                    totals["local_carrier_cases"] += 1

            if program_index in selected_mutation_indices:
                for category, mutated_source, mutated_target, mutated_certificate, detail in _mutation_cases(source, target, certificate):
                    production_accepted = True; production_reason = "accepted"
                    reference_accepted = True; reference_reason = "accepted"
                    try:
                        check_certificate(mutated_source, mutated_target, mutated_certificate)
                    except Exception as exc:
                        production_accepted = False; production_reason = f"{type(exc).__name__}:{exc}"
                    try:
                        reference.check(mutated_source, mutated_target, mutated_certificate)
                    except Exception as exc:
                        reference_accepted = False; reference_reason = f"{type(exc).__name__}:{exc}"
                    if production_accepted: totals["accepted_mutations"] += 1
                    if reference_accepted: totals["reference_accepted_mutations"] += 1
                    if production_accepted != reference_accepted: totals["mutation_decision_differences"] += 1
                    totals["certificate_mutations"] += 1
                    _write_jsonl(cert_mutation_handle, {
                        "program_id": program_id,
                        "category": category,
                        "detail": detail,
                        "source_text": mutated_source.decode("utf-8", errors="replace"),
                        "target_text": mutated_target.decode("utf-8", errors="replace"),
                        "certificate_text": mutated_certificate.decode("utf-8", errors="replace"),
                        "production_accepted": production_accepted,
                        "production_first_failure_reason": production_reason,
                        "reference_accepted": reference_accepted,
                        "reference_first_failure_reason": reference_reason,
                    })

            derivation_started = time.perf_counter_ns()
            production_target, production_derivation = build_derivation(source, payload)
            reference_target_program, reference_derivation = build_reference_derivation(source, payload)
            if production_derivation.to_bytes() != reference_derivation.to_bytes():
                totals["derivation_producer_differences"] += 1
            if serialize_program(production_target) != target_bytes or serialize_program(reference_target_program) != target_bytes:
                totals["derivation_target_differences"] += 1
            production_verdict, production_reason = verify_derivation_detailed(source, target, production_derivation, payload)
            reference_verdict, reference_reason = verify_derivation_detailed(source, target, reference_derivation, payload)
            if not production_verdict or not reference_verdict:
                totals["derivation_failures"] += 1
            derivation_ms = (time.perf_counter_ns() - derivation_started) / 1e6
            for producer, derivation, verdict, reason in (
                ("production_tree", production_derivation, production_verdict, production_reason),
                ("reference_raw_tree", reference_derivation, reference_verdict, reference_reason),
            ):
                _write_jsonl(derivation_handle, {
                    "program_id": program_id,
                    "producer": producer,
                    "derivation": derivation.to_obj(),
                    "accepted": verdict,
                    "first_failure_reason": reason,
                })
                totals["derivations"] += 1
            for category in (
                "source_hash", "target_hash", "selected", "framed_bits", "delete_step",
                "family", "interval", "bit", "before_sha256", "after_sha256",
            ):
                mutated, applicable, note = _mutate_derivation(production_derivation, category)
                if not applicable:
                    totals["derivation_mutations_not_applicable"] += 1
                    _write_jsonl(derivation_mutation_handle, {
                        "program_id": program_id, "category": category, "applicable": False,
                        "accepted": False, "first_failure_reason": note,
                    })
                    continue
                assert mutated is not None
                accepted, reason = verify_derivation_detailed(source, target, mutated, payload)
                totals["proof_mutations"] += 1
                if accepted: totals["accepted_proof_mutations"] += 1
                _write_jsonl(derivation_mutation_handle, {
                    "program_id": program_id, "category": category, "applicable": True,
                    "mutated_derivation": mutated.to_obj(), "accepted": accepted,
                    "first_failure_reason": reason,
                })

            for adjacent in _adjacent_classification(source):
                adjacent["program_id"] = program_id
                _write_jsonl(adjacent_handle, adjacent)
                totals["adjacent_pairs"] += 1
                totals["adjacent_legal_pairs"] += int(adjacent["legal"])
                for reason in adjacent["reasons"]:
                    totals[f"adjacent_reason_{reason}"] += 1

            for count in range(1, 1 << len(CARRIER_FAMILIES)):
                enabled = tuple(
                    family for bit, family in enumerate(CARRIER_FAMILIES) if count & (1 << bit)
                )
                subset_sites = select_sites([site for site in candidates if site.family in enabled])
                ablation_writer.writerow({
                    "program_id": program_id,
                    "enabled_families": "+".join(enabled),
                    "selected_sites": len(subset_sites),
                    "payload_bits": payload_capacity(len(subset_sites)),
                })

            family_counts = Counter(site.family for site in sites)
            descriptor_bytes = _descriptor_rich_certificate_bytes(certificate, sites)
            program_row = {
                "program_id": program_id,
                "family": spec.family,
                "index": spec.index,
                "bindings": len(source.commands),
                "candidates": len(candidates),
                "selected": len(sites),
                "payload_bits": capacity,
                "header_bits": len(sites) - capacity,
                "operand": family_counts["operand"],
                "identity": family_counts["identity"],
                "adjacent": family_counts["adjacent"],
                "source_bytes": len(source_bytes),
                "target_bytes": len(target_bytes),
                "certificate_bytes": len(certificate_bytes),
                "descriptor_rich_bytes": len(descriptor_bytes),
                "analysis_ms": analysis_ms,
                "discovery_ms": discovery_ms,
                "selection_ms": selection_ms,
                "embed_ms": embed_ms,
                "check_ms": check_ms,
                "reference_check_ms": reference_check_ms,
                "derivation_ms": derivation_ms,
                "evaluation_ms": evaluation_ms,
                "peak_rss_kb_after_program": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
            result_writer.writerow(program_row)
            program_rows.append(program_row)
            family_totals[spec.family].update({
                key: int(program_row[key])
                for key in ("bindings", "selected", "payload_bits", "header_bits", "operand", "identity", "adjacent", "source_bytes", "target_bytes", "certificate_bytes", "descriptor_rich_bytes")
            })
            family_totals[spec.family]["programs"] += 1
            totals.update({
                key: int(program_row[key])
                for key in ("bindings", "selected", "payload_bits", "header_bits", "operand", "identity", "adjacent", "source_bytes", "target_bytes", "certificate_bytes", "descriptor_rich_bytes")
            })
            totals["programs"] += 1
            for metric in ("analysis_ms", "discovery_ms", "selection_ms", "embed_ms", "check_ms", "reference_check_ms", "derivation_ms", "evaluation_ms"):
                timing_values[metric].append(float(program_row[metric]))
            if sites:
                positive_rows.append(program_row)

    # Independent interval audit over all masks of one fixed 16-candidate universe.
    interval_universe = [
        (0, 0, "identity"), (0, 1, "adjacent"), (1, 1, "operand"), (1, 2, "adjacent"),
        (2, 2, "identity"), (2, 3, "adjacent"), (3, 3, "operand"), (3, 4, "adjacent"),
        (4, 4, "identity"), (4, 5, "adjacent"), (5, 5, "operand"), (5, 6, "adjacent"),
        (6, 6, "identity"), (6, 7, "adjacent"), (7, 7, "operand"), (7, 8, "adjacent"),
    ]
    with (raw / "interval-audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=interval_fields); writer.writeheader()
        for mask in range(1 << len(interval_universe)):
            intervals = [interval_universe[index] for index in range(len(interval_universe)) if mask & (1 << index)]
            production_sites = [Site(family, start_i, end_i, (), ()) for start_i, end_i, family in intervals]
            greedy = len(select_sites(production_sites))
            optimum = _interval_optimum(intervals)
            equal = greedy == optimum
            totals["interval_instances"] += 1
            if not equal: totals["selector_differences"] += 1
            writer.writerow({"mask": mask, "candidate_count": len(intervals), "greedy_count": greedy, "optimum_count": optimum, "equal": int(equal)})

    # Every bit vector up to 16 sites, including invalid headers and padding.
    with (raw / "frame-audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=frame_fields); writer.writeheader()
        for site_count in range(17):
            for value in range(1 << site_count):
                bits = tuple((value >> shift) & 1 for shift in reversed(range(site_count)))
                valid = True; reason = "accepted"; payload_text = ""
                try:
                    payload = unframe_bits(bits)
                    payload_text = "".join(map(str, payload))
                    if frame_bits(payload, site_count) != bits:
                        valid = False; reason = "round_trip_mismatch"; totals["frame_failures"] += 1
                except Exception as exc:
                    valid = False; reason = f"{type(exc).__name__}:{exc}"
                writer.writerow({"site_count": site_count, "bits": "".join(map(str, bits)), "valid": int(valid), "payload": payload_text, "first_failure_reason": reason})
                totals["frame_vectors"] += 1
                if valid: totals["legal_frames"] += 1

    # Derive ablation summary from the raw file.
    ablation_rows = list(csv.DictReader((raw / "carrier-ablation.csv").open(encoding="utf-8", newline="")))
    ablation_summary: dict[str, dict[str, int]] = {}
    for row in ablation_rows:
        key = row["enabled_families"]
        bucket = ablation_summary.setdefault(key, {"programs": 0, "selected_sites": 0, "payload_bits": 0, "zero_capacity_programs": 0})
        bucket["programs"] += 1
        bucket["selected_sites"] += int(row["selected_sites"])
        bucket["payload_bits"] += int(row["payload_bits"])
        bucket["zero_capacity_programs"] += int(int(row["payload_bits"]) == 0)

    # Actual length groups used to replace the paper's unsupported equal quartiles.
    length_ranges = [(12, 20), (21, 28), (29, 40), (41, 48), (49, None)]
    length_groups: list[dict[str, Any]] = []
    for lower, upper in length_ranges:
        rows = [
            row for row in positive_rows
            if row["bindings"] >= lower and (upper is None or row["bindings"] <= upper)
        ]
        length_groups.append({
            "range": f"{lower}+" if upper is None else f"{lower}-{upper}",
            "programs": len(rows),
            "selected_median": statistics.median([row["selected"] for row in rows]) if rows else None,
            "embed_ms_median": statistics.median([row["embed_ms"] for row in rows]) if rows else None,
            "check_ms_median": statistics.median([row["check_ms"] for row in rows]) if rows else None,
        })

    correlations = {
        "bindings_embed_ms_spearman": _spearman([row["bindings"] for row in positive_rows], [row["embed_ms"] for row in positive_rows]),
        "bindings_check_ms_spearman": _spearman([row["bindings"] for row in positive_rows], [row["check_ms"] for row in positive_rows]),
        "bindings_selected_spearman": _spearman([row["bindings"] for row in positive_rows], [row["selected"] for row in positive_rows]),
    }
    timing_summary = {
        metric: {
            "minimum": min(values),
            "median": _quantile(values, 0.5),
            "p75": _quantile(values, 0.75),
            "p95": _quantile(values, 0.95),
            "maximum": max(values),
        }
        for metric, values in timing_values.items()
    }

    family_summary = {family: dict(counter) for family, counter in family_totals.items()}
    environment = _environment()
    environment["peak_rss_kb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (derived / "environment-mode4.json").write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n")
    (derived / "timing-summary-mode4.json").write_text(json.dumps({"length_groups": length_groups, "correlations": correlations, "timings": timing_summary}, indent=2, sort_keys=True) + "\n")
    (derived / "carrier-ablation-mode4.json").write_text(json.dumps(ablation_summary, indent=2, sort_keys=True) + "\n")

    certificate_mutation_categories = Counter()
    with (raw / "certificate-mutations.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            certificate_mutation_categories[json.loads(line)["category"]] += 1
    derivation_mutation_categories = Counter()
    derivation_mutation_applicable = Counter()
    with (raw / "derivation-mutations.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            derivation_mutation_categories[row["category"]] += 1
            if row["applicable"]:
                derivation_mutation_applicable[row["category"]] += 1

    corpus_digest = _length_prefixed_hash(source_chunks)
    summary = {
        "schema": "tidemark-evaluation-mode4",
        "mode": MODE_VERSION,
        "checker": CHECKER_VERSION,
        "certificate_schema": SCHEMA,
        "seed": "tidemark-fixed-seed",
        "corpus_design": "quota-constructed proof-stress suite; family totals and aggregate bindings are design inputs",
        "corpus_digest_algorithm": "SHA-256 over 8-byte big-endian length followed by canonical program bytes for each program in corpus order",
        "corpus_digest": corpus_digest,
        **{key: int(value) for key, value in totals.items()},
        "derivation_step_fields": list(STEP_FIELDS),
        "derivation_step_fields_per_producer": len(STEP_FIELDS) * totals["selected"],
        "structural_dependency": "trace verifier reuses tidemark.reference for analysis, discovery, selection, framing, replay, and extraction; not an independent proof kernel",
        "elapsed_seconds": time.perf_counter() - start,
        "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "aggregate_target_growth_percent": 100 * (totals["target_bytes"] / totals["source_bytes"] - 1),
        "aggregate_certificate_source_percent": 100 * totals["certificate_bytes"] / totals["source_bytes"],
        "aggregate_descriptor_rich_source_percent": 100 * totals["descriptor_rich_bytes"] / totals["source_bytes"],
        "descriptor_rich_to_compact_ratio": totals["descriptor_rich_bytes"] / totals["certificate_bytes"],
        "family_summary": family_summary,
        "length_groups": length_groups,
        "correlations": correlations,
        "timing_summary": timing_summary,
        "carrier_ablation": ablation_summary,
        "raw_files": owned,
        "certificate_mutation_categories": dict(sorted(certificate_mutation_categories.items())),
        "derivation_mutation_rows_by_category": dict(sorted(derivation_mutation_categories.items())),
        "derivation_mutation_applicable_by_category": dict(sorted(derivation_mutation_applicable.items())),
        "proof_mutation_semantics": "proof_mutations counts applicable mutations; derivation_mutations_not_applicable counts zero-site records that were retained with an explicit no_steps reason",
        "reference_evaluator_semantics": "reference_evaluator_pairs counts source/target pairs; reference_evaluator_calls is twice that value",
        "claim_boundary": "Finite mode-4 execution and differential checks validate this implementation on a quota-constructed suite. They do not measure a natural program distribution, prove the metatheory, refine LLVM semantics, or establish post-optimization persistence.",
    }
    (derived / "evaluation-summary-mode4.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
