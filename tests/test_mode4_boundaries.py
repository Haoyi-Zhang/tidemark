from __future__ import annotations

import json
import unittest

from tidemark import reference
from tidemark.core import (
    CHECKER_VERSION,
    MODE_VERSION,
    SCHEMA,
    Certificate,
    Command,
    Expr,
    Program,
    TideMarkError,
    Type,
    canonical_json,
    check_certificate,
    digest_bytes,
    discover_candidates,
    evaluate_program,
    select_sites,
    serialize_program,
    typecheck_program,
)
from tidemark.corpus import build_program, build_specs
from tidemark.external_llvm import project
from tidemark.structural import STEP_FIELDS, build_derivation, verify_derivation


def identity_precedence_program() -> Program:
    return Program(
        (("a", Type.INT), ("b0", Type.BOOL)),
        (),
        (
            Command("x", Expr.var("a")),
            Command("y", Expr.binary("add", Expr.var("x"), Expr.integer(0))),
            Command("z", Expr.binary("eq", Expr.var("b0"), Expr.boolean(True))),
        ),
        "y",
    )


def certificate_for_raw(source_obj: object, target_obj: object | None = None) -> bytes:
    if target_obj is None:
        target_obj = source_obj
    source_bytes = canonical_json(source_obj)
    target_bytes = canonical_json(target_obj)
    return canonical_json(
        {
            "checker": CHECKER_VERSION,
            "mode": MODE_VERSION,
            "payload": "",
            "schema": SCHEMA,
            "source_sha256": digest_bytes(source_bytes),
            "target_sha256": digest_bytes(target_bytes),
        }
    )


class Mode4CandidateBoundaryTests(unittest.TestCase):
    def test_identity_domain_and_precedence(self):
        program = identity_precedence_program()
        candidates = discover_candidates(program)
        signature = [(site.family, site.start, site.end) for site in candidates]
        # y = x + 0 and z = (b0 == true) are independent, pure, adjacent
        # commands.  Identity precedence suppresses operand classification at
        # each command, not the separately legal adjacent interval.
        self.assertEqual(
            signature,
            [
                ("identity", 0, 0),
                ("identity", 1, 1),
                ("adjacent", 1, 2),
                ("identity", 2, 2),
            ],
        )
        self.assertEqual(
            [(site.family, site.start, site.end) for site in select_sites(candidates)],
            [("identity", 0, 0), ("identity", 1, 1), ("identity", 2, 2)],
        )
        raw = program.to_obj()
        self.assertEqual(
            [(site[0], site[1], site[2]) for site in reference.candidates(raw)],
            signature,
        )

    def test_identity_direct_and_expanded_share_atomic_domain(self):
        program = Program(
            (("a", Type.INT), ("b", Type.BOOL)),
            (),
            (
                Command("i0", Expr.integer(7)),
                Command("i1", Expr.binary("add", Expr.integer(7), Expr.integer(0))),
                Command("b0", Expr.boolean(False)),
                Command("b1", Expr.binary("eq", Expr.boolean(False), Expr.boolean(True))),
            ),
            "i1",
        )
        identities = [site for site in discover_candidates(program) if site.family == "identity"]
        self.assertEqual([(site.start, site.end) for site in identities], [(0, 0), (1, 1), (2, 2), (3, 3)])

    def test_non_atomic_pure_base_is_not_identity(self):
        program = Program(
            (("a", Type.INT), ("b", Type.INT)),
            (),
            (Command("x", Expr.binary("add", Expr.binary("add", Expr.var("a"), Expr.var("b")), Expr.integer(0))),),
            "x",
        )
        self.assertNotIn("identity", [site.family for site in discover_candidates(program)])
        self.assertNotIn("identity", [site[0] for site in reference.candidates(program.to_obj())])

    def test_effectful_get_plus_zero_is_not_candidate(self):
        program = Program(
            (),
            (("r", Type.INT),),
            (Command("x", Expr.binary("add", Expr.get("r"), Expr.integer(0))),),
            "x",
        )
        self.assertEqual(discover_candidates(program), ())
        self.assertEqual(reference.candidates(program.to_obj()), [])

    def test_put_and_emit_are_adjacent_when_effects_are_disjoint(self):
        program = Program(
            (("a", Type.INT),),
            (("r", Type.INT),),
            (
                Command("u", Expr.put("r", Expr.var("a"))),
                Command("v", Expr.emit(Expr.var("a"))),
            ),
            "u",
        )
        signature = [(site.family, site.start, site.end) for site in discover_candidates(program)]
        self.assertEqual(signature, [("adjacent", 0, 1)])
        self.assertEqual([(site[0], site[1], site[2]) for site in reference.candidates(program.to_obj())], signature)

    def test_operand_orientation_uses_canonical_json(self):
        program = Program(
            (("a", Type.INT),),
            (),
            (Command("x", Expr.binary("add", Expr.var("a"), Expr.integer(2))),),
            "x",
        )
        site = next(site for site in discover_candidates(program) if site.family == "operand")
        left0, right0 = site.orientation0[0].expr.args[1:]
        self.assertLess(canonical_json(left0.to_obj()), canonical_json(right0.to_obj()))

    def test_same_typed_if_counterexample_is_well_typed_and_distinguishable(self):
        first = Program(
            (("b", Type.BOOL),), (),
            (Command("x", Expr.choose(Expr.var("b"), Expr.integer(0), Expr.integer(1))),),
            "x",
        )
        second = Program(
            (("b", Type.BOOL),), (),
            (Command("x", Expr.choose(Expr.var("b"), Expr.integer(0), Expr.integer(2))),),
            "x",
        )
        typecheck_program(first); typecheck_program(second)
        self.assertNotEqual(evaluate_program(first, {"b": False}, {}), evaluate_program(second, {"b": False}, {}))

    def test_two_emits_are_well_typed_but_not_adjacent_carrier(self):
        source = Program(
            (), (),
            (Command("u", Expr.emit(Expr.integer(0))), Command("v", Expr.emit(Expr.integer(1)))),
            "u",
        )
        swapped = Program(source.params, source.regions, tuple(reversed(source.commands)), source.result)
        typecheck_program(source); typecheck_program(swapped)
        self.assertEqual(discover_candidates(source), ())
        self.assertNotEqual(evaluate_program(source, {}, {}), evaluate_program(swapped, {}, {}))

    def test_adjacent_orientation_uses_complete_command_json(self):
        program = Program(
            (("a", Type.INT),),
            (),
            (
                Command("z", Expr.binary("sub", Expr.var("a"), Expr.integer(1))),
                Command("a0", Expr.binary("sub", Expr.var("a"), Expr.integer(2))),
            ),
            "z",
        )
        site = next(site for site in discover_candidates(program) if site.family == "adjacent")
        self.assertLess(
            canonical_json(site.orientation0[0].to_obj()),
            canonical_json(site.orientation0[1].to_obj()),
        )


class ReferenceSchemaBoundaryTests(unittest.TestCase):
    def _assert_both_reject(self, raw_program: dict[str, object]) -> None:
        program_bytes = canonical_json(raw_program)
        certificate = certificate_for_raw(raw_program)
        with self.assertRaises(Exception):
            check_certificate(program_bytes, program_bytes, certificate)
        with self.assertRaises(reference.RefError):
            reference.check(program_bytes, program_bytes, certificate)

    def test_matching_digest_unknown_type_rejected(self):
        self._assert_both_reject(
            {
                "schema": "tidemark-ir-3",
                "params": [["x", "Unknown"]],
                "regions": [],
                "commands": [],
                "result": "x",
            }
        )

    def test_matching_digest_duplicate_declaration_rejected(self):
        self._assert_both_reject(
            {
                "schema": "tidemark-ir-3",
                "params": [["x", "Int"], ["x", "Int"]],
                "regions": [],
                "commands": [],
                "result": "x",
            }
        )

    def test_matching_digest_extra_expression_argument_rejected(self):
        self._assert_both_reject(
            {
                "schema": "tidemark-ir-3",
                "params": [["x", "Int"]],
                "regions": [],
                "commands": [["let", "y", ["bin", "add", ["var", "x"], ["int", 0], ["int", 1]]]],
                "result": "y",
            }
        )


class CorpusApiAndStructuralDisclosureTests(unittest.TestCase):
    def test_build_program_is_current_deterministic_api(self):
        spec = build_specs()[17]
        first = build_program(spec)
        second = build_program(spec)
        self.assertEqual(serialize_program(first), serialize_program(second))
        typecheck_program(first)
        self.assertEqual(len(select_sites(discover_candidates(first))), spec.capacity)

    def test_structural_steps_have_exact_five_field_schema(self):
        source = build_program(next(spec for spec in build_specs() if spec.capacity >= 8))
        target, derivation = build_derivation(source, (1,))
        self.assertTrue(verify_derivation(source, target, derivation, (1,)))
        self.assertTrue(derivation.steps)
        for step in derivation.steps:
            self.assertEqual(tuple(step.keys()), STEP_FIELDS)


class LLVMProjectionBoundaryTests(unittest.TestCase):
    def test_equal_operands_with_metadata_are_not_candidate(self):
        text = """define i32 @f(i32 %x) !dbg !1 {\nentry:\n  %y = add i32 %x, %x, !dbg !2\n  ret i32 %y, !dbg !3\n}\n!1 = distinct !DISubprogram(name: \"f\")\n!2 = !DILocation(line: 1, column: 1, scope: !1)\n!3 = !DILocation(line: 2, column: 1, scope: !1)\n"""
        self.assertEqual(project(text).operand_sites, 0)

    def test_poison_and_undef_are_excluded(self):
        text = """define i32 @f(i32 %x) {\nentry:\n  %a = add i32 %x, poison\n  %b = add i32 %x, undef\n  %c = add i32 %x, 1\n  ret i32 %c\n}\n"""
        self.assertEqual(project(text).operand_sites, 1)


if __name__ == "__main__":
    unittest.main()
