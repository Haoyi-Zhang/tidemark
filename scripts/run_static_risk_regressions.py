#!/usr/bin/env python3
"""Execute the mode-4 boundary regressions requested by the consistency audit."""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tidemark import reference
from tidemark.core import (
    CHECKER_VERSION, MODE_VERSION, SCHEMA, Command, Expr, Program, Type,
    canonical_json, check_certificate, digest_bytes, discover_candidates,
    evaluate_program, parse_program, select_sites, serialize_program, typecheck_program,
)
from tidemark.corpus import build_program, build_specs
from tidemark.external_llvm import project

OUT = ROOT / "data" / "derived" / "static-risk-regressions-mode4.json"


def cert_for(raw: bytes) -> bytes:
    return canonical_json({
        "checker": CHECKER_VERSION,
        "mode": MODE_VERSION,
        "payload": "",
        "schema": SCHEMA,
        "source_sha256": digest_bytes(raw),
        "target_sha256": digest_bytes(raw),
    })


def exception_result(call: Callable[[], Any]) -> dict[str, Any]:
    try:
        call()
        return {"accepted": True, "exception_type": "", "reason": "accepted"}
    except Exception as exc:
        return {"accepted": False, "exception_type": type(exc).__name__, "reason": str(exc)}


def main() -> int:
    cases: list[dict[str, Any]] = []

    # F8: a well-typed but effectful base is outside both singleton carriers.
    get_plus_zero = Program(
        (), (("r", Type.INT),),
        (Command("x", Expr.binary("add", Expr.get("r"), Expr.integer(0))),),
        "x",
    )
    typecheck_program(get_plus_zero)
    production_get = [(site.family, site.start, site.end) for site in discover_candidates(get_plus_zero)]
    reference_get = [(site[0], site[1], site[2]) for site in reference.candidates(get_plus_zero.to_obj())]
    cases.append({
        "name": "effectful_get_plus_zero_is_not_a_candidate",
        "production_candidates": production_get,
        "reference_candidates": reference_get,
        "expected": [],
        "passed": production_get == [] and reference_get == [],
        "boundary": "typechecks, then discovery rejects singleton carrier because the base is not a pure atomic identity operand",
    })

    # The disputed candidate is legal under the formal mode-4 adjacent rule.
    precedence = Program(
        (("a", Type.INT), ("b0", Type.BOOL)), (),
        (
            Command("x", Expr.var("a")),
            Command("y", Expr.binary("add", Expr.var("x"), Expr.integer(0))),
            Command("z", Expr.binary("eq", Expr.var("b0"), Expr.boolean(True))),
        ),
        "y",
    )
    production_candidates = [(site.family, site.start, site.end) for site in discover_candidates(precedence)]
    reference_candidates = [(site[0], site[1], site[2]) for site in reference.candidates(precedence.to_obj())]
    selected = [(site.family, site.start, site.end) for site in select_sites(discover_candidates(precedence))]
    expected_candidates = [
        ("identity", 0, 0),
        ("identity", 1, 1),
        ("adjacent", 1, 2),
        ("identity", 2, 2),
    ]
    expected_selected = [("identity", 0, 0), ("identity", 1, 1), ("identity", 2, 2)]
    cases.append({
        "name": "identity_precedence_retains_independently_legal_adjacent_candidate",
        "production_candidates": production_candidates,
        "reference_candidates": reference_candidates,
        "selected": selected,
        "expected_candidates": expected_candidates,
        "expected_selected": expected_selected,
        "passed": production_candidates == expected_candidates and reference_candidates == expected_candidates and selected == expected_selected,
        "explanation": "identity precedence suppresses operand classification at one command; it does not suppress the distinct [1,2] adjacent interval. y uses x, z uses b0, both commands are pure, and neither result is used by the other.",
    })

    put_emit = Program(
        (("a", Type.INT),), (("r", Type.INT),),
        (Command("u", Expr.put("r", Expr.var("a"))), Command("v", Expr.emit(Expr.var("a")))),
        "u",
    )
    put_emit_production = [(site.family, site.start, site.end) for site in discover_candidates(put_emit)]
    put_emit_reference = [(site[0], site[1], site[2]) for site in reference.candidates(put_emit.to_obj())]
    cases.append({
        "name": "put_and_emit_can_commute_when_resources_are_disjoint",
        "production_candidates": put_emit_production,
        "reference_candidates": put_emit_reference,
        "expected": [("adjacent", 0, 1)],
        "passed": put_emit_production == [("adjacent", 0, 1)] and put_emit_reference == [("adjacent", 0, 1)],
    })

    same_typed_if_a = Program(
        (("b", Type.BOOL),), (),
        (Command("x", Expr.choose(Expr.var("b"), Expr.integer(0), Expr.integer(1))),), "x",
    )
    same_typed_if_b = Program(
        (("b", Type.BOOL),), (),
        (Command("x", Expr.choose(Expr.var("b"), Expr.integer(0), Expr.integer(2))),), "x",
    )
    typecheck_program(same_typed_if_a); typecheck_program(same_typed_if_b)
    if_a = evaluate_program(same_typed_if_a, {"b": False}, {})
    if_b = evaluate_program(same_typed_if_b, {"b": False}, {})
    cases.append({
        "name": "same_typed_if_counterexample_is_well_typed",
        "first_observation": if_a,
        "second_observation": if_b,
        "passed": if_a != if_b,
    })

    emits = Program(
        (), (),
        (Command("u", Expr.emit(Expr.integer(0))), Command("v", Expr.emit(Expr.integer(1)))), "u",
    )
    swapped_emits = Program(emits.params, emits.regions, tuple(reversed(emits.commands)), emits.result)
    typecheck_program(emits); typecheck_program(swapped_emits)
    emit_first = evaluate_program(emits, {}, {})
    emit_second = evaluate_program(swapped_emits, {}, {})
    cases.append({
        "name": "ordered_emit_counterexample_is_well_typed",
        "candidates": [(site.family, site.start, site.end) for site in discover_candidates(emits)],
        "first_trace": emit_first[2],
        "second_trace": emit_second[2],
        "passed": discover_candidates(emits) == () and emit_first != emit_second,
    })

    malformed_programs = {
        "matching_digest_unknown_type": {
            "schema": "tidemark-ir-3", "params": [["x", "Unknown"]], "regions": [], "commands": [], "result": "x",
        },
        "matching_digest_duplicate_declaration": {
            "schema": "tidemark-ir-3", "params": [["x", "Int"], ["x", "Int"]], "regions": [], "commands": [], "result": "x",
        },
        "matching_digest_extra_expression_argument": {
            "schema": "tidemark-ir-3", "params": [["x", "Int"]], "regions": [],
            "commands": [["let", "y", ["bin", "add", ["var", "x"], ["int", 0], ["int", 1]]]], "result": "y",
        },
    }
    for name, value in malformed_programs.items():
        raw = canonical_json(value)
        certificate = cert_for(raw)
        production = exception_result(lambda raw=raw, certificate=certificate: check_certificate(raw, raw, certificate))
        reference_result = exception_result(lambda raw=raw, certificate=certificate: reference.check(raw, raw, certificate))
        cases.append({
            "name": name,
            "source_sha256": digest_bytes(raw),
            "certificate_digests_match_input": True,
            "production": production,
            "reference": reference_result,
            "passed": not production["accepted"] and not reference_result["accepted"],
            "boundary": "rejected during strict program schema/type analysis before candidate discovery or replay",
        })

    metadata_sample = '''define i32 @f(i32 %x) !dbg !1 {\nentry:\n  %y = add i32 %x, %x, !dbg !2\n  ret i32 %y, !dbg !3\n}\n!1 = distinct !DISubprogram(name: "f")\n!2 = !DILocation(line: 1, column: 1, scope: !1)\n!3 = !DILocation(line: 2, column: 1, scope: !1)\n'''
    metadata_projection = project(metadata_sample)
    cases.append({
        "name": "llvm_metadata_is_removed_before_equal_operand_test",
        "operand_sites": metadata_projection.operand_sites,
        "passed": metadata_projection.operand_sites == 0,
    })

    poison_undef_sample = '''define i32 @f(i32 %x) {\nentry:\n  %a = add i32 %x, poison\n  %b = add i32 %x, undef\n  %c = add i32 %x, 1\n  ret i32 %c\n}\n'''
    poison_projection = project(poison_undef_sample)
    cases.append({
        "name": "llvm_poison_and_undef_are_excluded",
        "operand_sites": poison_projection.operand_sites,
        "passed": poison_projection.operand_sites == 1,
    })

    spec = build_specs()[17]
    first = build_program(spec)
    second = build_program(spec)
    build_api_passed = (
        serialize_program(first) == serialize_program(second)
        and len(select_sites(discover_candidates(first))) == spec.capacity
    )
    typecheck_program(first)
    cases.append({
        "name": "build_program_is_current_deterministic_corpus_api",
        "spec": spec.__dict__,
        "program_sha256": hashlib.sha256(serialize_program(first)).hexdigest(),
        "selected_sites": len(select_sites(discover_candidates(first))),
        "passed": build_api_passed,
        "decision": "retain build_program as the current deterministic API because the corpus generator, tests, and evaluation all consume it",
    })

    reference_path = ROOT / "src" / "tidemark" / "reference.py"
    tree = ast.parse(reference_path.read_text())
    prohibited_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith("core") or module == "tidemark.core":
                prohibited_imports.append(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tidemark.core" or alias.name.endswith(".core"):
                    prohibited_imports.append(alias.name)
    cases.append({
        "name": "reference_checker_does_not_import_production_core",
        "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        "prohibited_imports": prohibited_imports,
        "passed": not prohibited_imports,
    })

    failed = [case for case in cases if not case["passed"]]
    result = {
        "schema": "tidemark-static-risk-regressions-mode4",
        "mode": MODE_VERSION,
        "cases": cases,
        "case_count": len(cases),
        "failure_count": len(failed),
        "failures": failed,
        "all_passed": not failed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
