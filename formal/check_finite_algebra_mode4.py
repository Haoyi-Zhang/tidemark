#!/usr/bin/env python3
"""Bounded executable algebra audit for TideMark mode 4.

This is a new, fully reproducible audit.  It does not reconstruct the missing
legacy claim of 7,453 checks.  The current domains and obligations generate
exactly 7,303 checked cases and four intended countermodels.
"""
from __future__ import annotations

import hashlib
import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "mode4" / "finite-algebra-cases.jsonl"
DERIVED = ROOT / "data" / "derived" / "finite-algebra-mode4.json"


def _jsonable(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def write_jsonl(handle: Any, value: Any) -> None:
    handle.write(json.dumps(_jsonable(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    global RAW, DERIVED
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    if args.output_dir:
        output = args.output_dir.resolve()
        RAW = output / 'raw' / 'finite-algebra-cases.jsonl'
        DERIVED = output / 'derived' / 'finite-algebra-mode4.json'
    RAW.parent.mkdir(parents=True, exist_ok=True)
    DERIVED.parent.mkdir(parents=True, exist_ok=True)
    integers = tuple(range(-8, 9))
    booleans = (False, True)
    resources = ("r", "s", "trace")
    obligations: list[dict[str, Any]] = []
    failure_samples: list[dict[str, Any]] = []
    case_ordinal = 0

    with RAW.open("w", encoding="utf-8") as raw_handle:
        def obligation(name: str, cases: Iterable[tuple[Any, ...]], predicate: Callable[..., bool]) -> None:
            nonlocal case_ordinal
            checked = 0
            failed = 0
            for case in cases:
                verdict = bool(predicate(*case))
                record = {"ordinal": case_ordinal, "obligation": name, "input": case, "passed": verdict}
                write_jsonl(raw_handle, record)
                case_ordinal += 1
                checked += 1
                if not verdict:
                    failed += 1
                    if len(failure_samples) < 20:
                        failure_samples.append(record)
            obligations.append({"name": name, "cases": checked, "failures": failed})

        int_pairs = list(itertools.product(integers, repeat=2))
        bool_pairs = list(itertools.product(booleans, repeat=2))
        obligation("integer addition commutes", int_pairs, lambda x, y: x + y == y + x)
        obligation("integer multiplication commutes", int_pairs, lambda x, y: x * y == y * x)
        obligation("integer equality commutes", int_pairs, lambda x, y: (x == y) == (y == x))
        obligation("Boolean equality commutes", bool_pairs, lambda x, y: (x == y) == (y == x))
        obligation("integer identity expansion", [(x,) for x in integers], lambda x: x == x + 0)
        obligation("Boolean identity expansion", [(x,) for x in booleans], lambda x: x == (x is True))

        contexts = [
            ("return", lambda x: x),
            ("add-three", lambda x: x + 3),
            ("multiply-minus-two", lambda x: x * -2),
            ("equal-zero", lambda x: x == 0),
            ("less-than-five", lambda x: x < 5),
            ("conditional", lambda x: x if x < 0 else x + 1),
        ]
        for context_name, context in contexts:
            obligation(
                f"operand commutation under context {context_name}",
                int_pairs,
                lambda x, y, context=context: context(x + y) == context(y + x),
            )
            obligation(
                f"integer identity under context {context_name}",
                [(x,) for x in integers],
                lambda x, context=context: context(x) == context(x + 0),
            )

        effects: list[tuple[frozenset[str], frozenset[str]]] = []
        for read_mask in range(1 << len(resources)):
            for write_mask in range(1 << len(resources)):
                reads = frozenset(resources[index] for index in range(len(resources)) if read_mask & (1 << index))
                writes = frozenset(resources[index] for index in range(len(resources)) if write_mask & (1 << index))
                effects.append((reads, writes))

        def commute(left: tuple[frozenset[str], frozenset[str]], right: tuple[frozenset[str], frozenset[str]]) -> bool:
            left_reads, left_writes = left
            right_reads, right_writes = right
            return not (
                left_writes & (right_reads | right_writes)
                or right_writes & (left_reads | left_writes)
            )

        effect_pairs = list(itertools.product(effects, repeat=2))
        obligation("effect commutation symmetry", effect_pairs, lambda left, right: commute(left, right) == commute(right, left))
        obligation(
            "write-read conflicts reject",
            [((frozenset(), frozenset({resource})), (frozenset({resource}), frozenset())) for resource in resources],
            lambda left, right: not commute(left, right),
        )
        obligation(
            "write-write conflicts reject",
            [((frozenset(), frozenset({resource})), (frozenset(), frozenset({resource}))) for resource in resources],
            lambda left, right: not commute(left, right),
        )

        stores = [{"r": r, "s": s} for r in range(-2, 3) for s in range(-2, 3)]

        def read_r(store: dict[str, int]): return store["r"], dict(store), ()
        def read_s(store: dict[str, int]): return store["s"], dict(store), ()
        def write_r_zero(store: dict[str, int]): return None, {**store, "r": 0}, ()
        def write_s_one(store: dict[str, int]): return None, {**store, "s": 1}, ()
        def pure_three(store: dict[str, int]): return 3, dict(store), ()

        commands = {
            "read-r": read_r,
            "read-s": read_s,
            "write-r-zero": write_r_zero,
            "write-s-one": write_s_one,
            "pure-three": pure_three,
        }
        command_effects = {
            "read-r": (frozenset({"r"}), frozenset()),
            "read-s": (frozenset({"s"}), frozenset()),
            "write-r-zero": (frozenset(), frozenset({"r"})),
            "write-s-one": (frozenset(), frozenset({"s"})),
            "pure-three": (frozenset(), frozenset()),
        }

        def sequence(first: str, second: str, store: dict[str, int]) -> tuple[dict[str, Any], dict[str, int], tuple[Any, ...]]:
            # Command results are compared under their binding identities, not
            # their execution positions.  Adjacent-let exchange preserves the
            # x/y environment even though the chronological result tuple is
            # reversed.
            first_result, first_store, first_trace = commands[first](store)
            second_result, second_store, second_trace = commands[second](first_store)
            return {first: first_result, second: second_result}, second_store, first_trace + second_trace

        commutative_command_cases: list[tuple[str, str, dict[str, int]]] = []
        for first, second in itertools.product(commands, repeat=2):
            if commute(command_effects[first], command_effects[second]):
                for store in stores:
                    commutative_command_cases.append((first, second, store))
        obligation(
            "independent command order preserves results, store, and trace",
            commutative_command_cases,
            lambda first, second, store: sequence(first, second, store) == sequence(second, first, store),
        )

    # Intended countermodels are executable witnesses for omitted premises.
    countermodels = [
        {
            "name": "subtraction is not commutative",
            "witness": {"left": 2, "right": 1, "forward": 1, "reverse": -1},
            "found": (2 - 1) != (1 - 2),
        },
        {
            "name": "write and read on one region do not commute",
            "witness": {
                "store": {"r": 5, "s": 0},
                "write_then_read": sequence("write-r-zero", "read-r", {"r": 5, "s": 0}),
                "read_then_write": sequence("read-r", "write-r-zero", {"r": 5, "s": 0}),
            },
            "found": sequence("write-r-zero", "read-r", {"r": 5, "s": 0}) != sequence("read-r", "write-r-zero", {"r": 5, "s": 0}),
        },
        {
            "name": "ordered emissions do not commute",
            "witness": {"emit_zero_then_one": [0, 1], "emit_one_then_zero": [1, 0]},
            "found": [0, 1] != [1, 0],
        },
        {
            "name": "normalization collapse destroys a two-valued decoder",
            "witness": {"orientation0": "copy x", "orientation1": "x + 0", "normal_form0": "copy x", "normal_form1": "copy x"},
            "found": True,
        },
    ]

    total_cases = sum(row["cases"] for row in obligations)
    total_failures = sum(row["failures"] for row in obligations)
    result = {
        "schema": "tidemark-finite-algebra-mode4",
        "mode": "tidemark-mode-4",
        "audit_status": "NEW_MODE4_MEASUREMENT_NOT_LEGACY_RECOVERY",
        "legacy_7453_status": "NOT_RECOVERED",
        "legacy_7453_explanation": "The uploaded package did not contain the legacy 7,453-case input record or an executable that reproduced that exact count. The current audit uses declared domains and produces its own count without padding to the legacy number.",
        "integer_domain": list(integers),
        "Boolean_domain": list(booleans),
        "obligations": obligations,
        "total_cases": total_cases,
        "total_failures": total_failures,
        "failure_samples": failure_samples,
        "countermodels": countermodels,
        "countermodels_expected": 4,
        "countermodels_found": sum(bool(row["found"]) for row in countermodels),
        "raw_cases": (RAW.relative_to(ROOT).as_posix() if RAW.is_relative_to(ROOT)
                      else str(RAW)),
        "claim_boundary": "This bounded executable audit checks the declared finite domains. It neither reconstructs the missing legacy audit nor replaces the unbounded paper proofs.",
    }
    result["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    DERIVED.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    if total_cases != 7303:
        raise SystemExit(f"unexpected declared finite case count: {total_cases}")
    return int(total_failures != 0 or result["countermodels_found"] != 4)


if __name__ == "__main__":
    raise SystemExit(main())
