from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import unittest

from tidemark.core import (
    CHECKER_VERSION,
    MODE_VERSION,
    Analysis,
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
    decode_site,
    digest_bytes,
    discover_candidates,
    embed,
    evaluate_program,
    expr_free_vars,
    frame_bits,
    header_width,
    infer_expr,
    optimal_interval_count,
    parse_program,
    payload_capacity,
    replay,
    select_sites,
    serialize_program,
    typecheck_program,
    unframe_bits,
)
from tidemark.corpus import build_program, build_specs
from tidemark import reference
from tidemark.structural import Derivation, build_derivation, build_reference_derivation, verify_derivation


def sample_program() -> Program:
    return Program(
        (("a", Type.INT), ("b", Type.INT)),
        (("r", Type.INT),),
        (
            Command("x", Expr.binary("add", Expr.var("a"), Expr.var("b"))),
            Command("y", Expr.var("x")),
            Command("u", Expr.binary("sub", Expr.var("y"), Expr.integer(2))),
            Command("v", Expr.binary("sub", Expr.var("y"), Expr.integer(3))),
            Command("z", Expr.binary("sub", Expr.var("u"), Expr.var("v"))),
        ),
        "z",
    )


def program_with(expressions: list[tuple[str, Expr]], result: str | None = None) -> Program:
    commands = tuple(Command(name, expr) for name, expr in expressions)
    return Program((("a", Type.INT), ("b", Type.INT), ("flag", Type.BOOL)), (("r", Type.INT),), commands, result or commands[-1].name)


class CanonicalEncodingTests(unittest.TestCase):
    def test_program_round_trip(self):
        source = sample_program()
        self.assertEqual(parse_program(serialize_program(source)), source)

    def test_program_noncanonical_whitespace_rejected(self):
        data = serialize_program(sample_program())
        with self.assertRaises(TideMarkError):
            parse_program(data.replace(b'{', b'{ ', 1))

    def test_program_unknown_field_rejected(self):
        obj = sample_program().to_obj(); obj["extra"] = 1
        with self.assertRaises(TideMarkError):
            Program.from_obj(obj)

    def test_program_unsupported_schema_rejected(self):
        obj = sample_program().to_obj(); obj["schema"] = "future"
        with self.assertRaises(TideMarkError):
            Program.from_obj(obj)

    def test_program_invalid_utf8_rejected(self):
        with self.assertRaises(TideMarkError):
            parse_program(b"\xff")

    def test_expression_malformed_rejected(self):
        with self.assertRaises(TideMarkError):
            Expr.from_obj(["bin", "add", ["int", 1]])

    def test_duplicate_parameter_rejected(self):
        obj = sample_program().to_obj(); obj["params"] = [["a", "Int"], ["a", "Int"]]
        with self.assertRaises(TideMarkError):
            Program.from_obj(obj)

    def test_duplicate_command_rejected(self):
        source = program_with([("x", Expr.var("a")), ("x", Expr.var("b"))])
        with self.assertRaises(TideMarkError):
            typecheck_program(source)

    def test_canonical_json_is_key_order_stable(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), b'{"a":1,"b":2}')

    def test_digest_is_sha256(self):
        self.assertEqual(digest_bytes(b"abc"), hashlib.sha256(b"abc").hexdigest())


class StaticAndDynamicSemanticsTests(unittest.TestCase):
    def test_free_variables(self):
        expr = Expr.binary("add", Expr.var("a"), Expr.binary("mul", Expr.var("b"), Expr.integer(2)))
        self.assertEqual(expr_free_vars(expr), frozenset({"a", "b"}))

    def test_integer_addition_type(self):
        typ, effect = infer_expr(Expr.binary("add", Expr.var("a"), Expr.integer(1)), {"a": Type.INT}, {})
        self.assertEqual((typ, effect), (Type.INT, Effect()))

    def test_boolean_not_type(self):
        typ, effect = infer_expr(Expr.logical_not(Expr.var("p")), {"p": Type.BOOL}, {})
        self.assertEqual((typ, effect), (Type.BOOL, Effect()))

    def test_equality_type_mismatch_rejected(self):
        with self.assertRaises(TideMarkError):
            infer_expr(Expr.binary("eq", Expr.integer(1), Expr.boolean(True)), {}, {})

    def test_if_branch_mismatch_rejected(self):
        with self.assertRaises(TideMarkError):
            infer_expr(Expr.choose(Expr.boolean(True), Expr.integer(1), Expr.boolean(False)), {}, {})

    def test_unbound_variable_rejected(self):
        with self.assertRaises(TideMarkError):
            infer_expr(Expr.var("missing"), {}, {})

    def test_get_effect(self):
        typ, effect = infer_expr(Expr.get("r"), {}, {"r": Type.INT})
        self.assertEqual(typ, Type.INT); self.assertEqual(effect.reads, frozenset({"r"}))

    def test_put_effect(self):
        typ, effect = infer_expr(Expr.put("r", Expr.integer(3)), {}, {"r": Type.INT})
        self.assertEqual(typ, Type.UNIT); self.assertEqual(effect.writes, frozenset({"r"}))

    def test_emit_effect(self):
        typ, effect = infer_expr(Expr.emit(Expr.integer(3)), {}, {})
        self.assertEqual(typ, Type.UNIT); self.assertTrue(effect.emits)

    def test_disjoint_effects_commute(self):
        self.assertTrue(Effect(writes=frozenset({"r"})).commutes_with(Effect(reads=frozenset({"s"}))))

    def test_write_read_conflict_does_not_commute(self):
        self.assertFalse(Effect(writes=frozenset({"r"})).commutes_with(Effect(reads=frozenset({"r"}))))

    def test_two_emissions_do_not_commute(self):
        self.assertFalse(Effect(emits=True).commutes_with(Effect(emits=True)))

    def test_evaluation_observation(self):
        source = program_with([
            ("w", Expr.put("r", Expr.var("a"))),
            ("x", Expr.get("r")),
            ("o", Expr.emit(Expr.var("x"))),
            ("z", Expr.binary("add", Expr.var("x"), Expr.var("b"))),
        ], "z")
        self.assertEqual(evaluate_program(source, {"a": 4, "b": 5, "flag": False}, {"r": 0}), (9, {"r": 4}, (4,)))

    def test_evaluation_parameter_domain_rejected(self):
        with self.assertRaises(TideMarkError):
            evaluate_program(sample_program(), {"a": 1}, {"r": 0})

    def test_evaluation_store_domain_rejected(self):
        with self.assertRaises(TideMarkError):
            evaluate_program(sample_program(), {"a": 1, "b": 2}, {})


class CarrierAndSelectionTests(unittest.TestCase):
    def families(self, program: Program) -> list[str]:
        return [site.family for site in discover_candidates(program)]

    def test_operand_addition_discovered(self):
        source = program_with([("x", Expr.binary("add", Expr.var("a"), Expr.var("b")))])
        self.assertIn("operand", self.families(source))

    def test_equal_operands_not_discovered(self):
        source = program_with([("x", Expr.binary("add", Expr.var("a"), Expr.var("a")))])
        self.assertNotIn("operand", self.families(source))

    def test_effectful_operands_not_discovered(self):
        source = program_with([("x", Expr.binary("add", Expr.get("r"), Expr.var("a")))])
        self.assertNotIn("operand", self.families(source))

    def test_integer_identity_discovered(self):
        source = program_with([("x", Expr.var("a"))])
        self.assertIn("identity", self.families(source))

    def test_boolean_identity_discovered(self):
        source = program_with([("x", Expr.var("flag"))])
        self.assertIn("identity", self.families(source))

    def test_adjacent_independent_discovered(self):
        source = program_with([("x", Expr.binary("sub", Expr.var("a"), Expr.integer(1))), ("y", Expr.binary("sub", Expr.var("b"), Expr.integer(2)))], "y")
        self.assertIn("adjacent", self.families(source))

    def test_adjacent_dependency_rejected(self):
        source = program_with([("x", Expr.binary("sub", Expr.var("a"), Expr.integer(1))), ("y", Expr.binary("sub", Expr.var("x"), Expr.integer(2)))], "y")
        self.assertNotIn("adjacent", self.families(source))

    def test_adjacent_state_conflict_rejected(self):
        source = program_with([("x", Expr.put("r", Expr.var("a"))), ("y", Expr.get("r"))], "y")
        self.assertNotIn("adjacent", self.families(source))

    def test_adjacent_trace_conflict_rejected(self):
        source = program_with([("x", Expr.emit(Expr.var("a"))), ("y", Expr.emit(Expr.var("b")))], "y")
        self.assertNotIn("adjacent", self.families(source))

    def test_selector_chooses_maximum_cardinality(self):
        sites = (
            Site("adjacent", 0, 1, (), ()),
            Site("operand", 0, 0, (), ()),
            Site("operand", 1, 1, (), ()),
            Site("adjacent", 1, 2, (), ()),
            Site("operand", 2, 2, (), ()),
        )
        selected = select_sites(sites)
        self.assertEqual(len(selected), 3)
        self.assertEqual(len(selected), optimal_interval_count(sites))

    def test_selector_is_deterministic_under_input_permutation(self):
        source = sample_program(); candidates = discover_candidates(source)
        self.assertEqual(select_sites(candidates), select_sites(tuple(reversed(candidates))))

    def test_coordinates_are_payload_independent(self):
        source = build_program(next(spec for spec in build_specs() if spec.capacity >= 8))
        q1, _ = embed(source, (1,)); q2, _ = embed(source, (0, 1))
        sites = select_sites(discover_candidates(source))
        self.assertEqual([(s.family, s.start, s.end) for s in sites], [(s.family, s.start, s.end) for s in select_sites(discover_candidates(source))])
        self.assertEqual(len(q1.commands), len(q2.commands))

    def test_replay_order_independence_for_disjoint_sites(self):
        source = sample_program(); sites = select_sites(discover_candidates(source)); bits = frame_bits((), len(sites))
        target1 = replay(source, sites, bits)
        target2 = replay(source, tuple(reversed(sites)), tuple(reversed(bits)))
        self.assertEqual(target1, target2)

    def test_decode_both_orientations(self):
        source = sample_program(); site = select_sites(discover_candidates(source))[0]
        self.assertEqual(decode_site(site, replay(source, (site,), (0,))), 0)
        self.assertEqual(decode_site(site, replay(source, (site,), (1,))), 1)

    def test_decode_nonorientation_rejected(self):
        source = sample_program(); site = select_sites(discover_candidates(source))[0]
        broken = Program(source.params, source.regions, (Command(source.commands[0].name, Expr.integer(999)),) + source.commands[1:], source.result)
        with self.assertRaises(TideMarkError):
            decode_site(site, broken)


class FramingTests(unittest.TestCase):
    def test_header_widths(self):
        self.assertEqual([header_width(n) for n in range(9)], [0, 1, 2, 2, 3, 3, 3, 3, 4])

    def test_payload_capacities(self):
        self.assertEqual([payload_capacity(n) for n in range(6)], [0, 0, 0, 1, 1, 2])

    def test_frame_round_trip(self):
        for n in range(1, 20):
            for length in range(payload_capacity(n) + 1):
                message = tuple((i + n) % 2 for i in range(length))
                self.assertEqual(unframe_bits(frame_bits(message, n)), message)

    def test_trailing_zero_distinction(self):
        self.assertNotEqual(frame_bits((1,), 8), frame_bits((1, 0), 8))

    def test_nonzero_padding_rejected(self):
        bits = list(frame_bits((1,), 8)); bits[-1] = 1
        with self.assertRaises(TideMarkError):
            unframe_bits(bits)

    def test_oversize_payload_rejected(self):
        with self.assertRaises(TideMarkError):
            frame_bits((1, 0), 3)

    def test_zero_capacity_frame(self):
        self.assertEqual(frame_bits((), 0), ())
        self.assertEqual(unframe_bits(()), ())

    def test_invalid_frame_bit_rejected(self):
        with self.assertRaises(TideMarkError):
            frame_bits((2,), 4)

    def test_exhaustive_12309_cases(self):
        count = 0
        for n in range(17):
            capacity = payload_capacity(n)
            for length in range(capacity + 1):
                for value in range(1 << length):
                    message = tuple((value >> shift) & 1 for shift in reversed(range(length)))
                    self.assertEqual(unframe_bits(frame_bits(message, n)), message)
                    count += 1
        self.assertEqual(count, 12309)


class CertificateAndIndependentEvidenceTests(unittest.TestCase):
    def test_end_to_end_round_trip(self):
        source = sample_program(); sites = select_sites(discover_candidates(source)); payload = (1,) * payload_capacity(len(sites))
        target, certificate = embed(source, payload)
        self.assertEqual(check_certificate(serialize_program(source), serialize_program(target), certificate.to_bytes()), payload)

    def test_reference_checker_agrees(self):
        source = sample_program(); target, certificate = embed(source, ())
        args = serialize_program(source), serialize_program(target), certificate.to_bytes()
        self.assertEqual(reference.check(*args), check_certificate(*args))

    def test_unsupported_embed_mode_rejected(self):
        with self.assertRaises(TideMarkError):
            embed(sample_program(), (), "future")

    def test_bad_checker_version_rejected(self):
        source = sample_program(); target, certificate = embed(source, ())
        bad = dataclasses.replace(certificate, checker="future")
        with self.assertRaises(TideMarkError):
            check_certificate(serialize_program(source), serialize_program(target), bad.to_bytes())

    def test_source_digest_mutation_rejected(self):
        source = sample_program(); target, certificate = embed(source, ())
        bad = dataclasses.replace(certificate, source_sha256="0" * 64)
        with self.assertRaises(TideMarkError):
            check_certificate(serialize_program(source), serialize_program(target), bad.to_bytes())

    def test_target_digest_mutation_rejected(self):
        source = sample_program(); target, certificate = embed(source, ())
        bad = dataclasses.replace(certificate, target_sha256="0" * 64)
        with self.assertRaises(TideMarkError):
            check_certificate(serialize_program(source), serialize_program(target), bad.to_bytes())

    def test_certificate_unknown_field_rejected(self):
        source = sample_program(); _, certificate = embed(source, ())
        obj = certificate.to_obj(); obj["extra"] = 1
        with self.assertRaises(TideMarkError):
            Certificate.from_bytes(canonical_json(obj))

    def test_certificate_noncanonical_encoding_rejected(self):
        source = sample_program(); _, certificate = embed(source, ())
        with self.assertRaises(TideMarkError):
            Certificate.from_bytes(certificate.to_bytes().replace(b'{', b'{ ', 1))

    def test_certificate_invalid_payload_rejected(self):
        source = sample_program(); _, certificate = embed(source, ())
        obj = certificate.to_obj(); obj["payload"] = "10x"
        with self.assertRaises(TideMarkError):
            Certificate.from_bytes(canonical_json(obj))

    def test_target_mutation_rejected(self):
        source = sample_program(); target, certificate = embed(source, ())
        changed = Program(target.params, target.regions, target.commands[:-1] + (Command(target.commands[-1].name, Expr.integer(0)),), target.result)
        changed_bytes = serialize_program(changed)
        forged = dataclasses.replace(certificate, target_sha256=digest_bytes(changed_bytes))
        with self.assertRaises(TideMarkError):
            check_certificate(serialize_program(source), changed_bytes, forged.to_bytes())

    def test_payload_mutation_rejected(self):
        source = build_program(next(spec for spec in build_specs() if spec.capacity >= 8)); target, certificate = embed(source, (1,))
        forged = dataclasses.replace(certificate, payload=(0,))
        with self.assertRaises(TideMarkError):
            check_certificate(serialize_program(source), serialize_program(target), forged.to_bytes())

    def test_trailing_zero_messages_produce_distinct_targets(self):
        source = build_program(next(spec for spec in build_specs() if spec.capacity >= 8))
        q1, _ = embed(source, (1,)); q2, _ = embed(source, (1, 0))
        self.assertNotEqual(serialize_program(q1), serialize_program(q2))

    def test_structural_derivation_verifies(self):
        source = sample_program(); sites = select_sites(discover_candidates(source)); payload = (0,) * payload_capacity(len(sites))
        target, derivation = build_derivation(source, payload)
        self.assertTrue(verify_derivation(source, target, derivation, payload))

    def test_structural_derivation_mutation_rejected(self):
        source = sample_program(); target, derivation = build_derivation(source, ())
        obj = derivation.to_obj(); obj["source_hash"] = "0" * 64
        bad = Derivation(obj["source_hash"], obj["target_hash"], tuple(tuple(x) for x in obj["selected"]), tuple(obj["framed_bits"]), tuple(obj["steps"]))
        self.assertFalse(verify_derivation(source, target, bad, ()))

    def test_reference_rejects_noncanonical_program(self):
        source = serialize_program(sample_program()).replace(b'{', b'{ ', 1)
        target, certificate = embed(sample_program(), ())
        with self.assertRaises(reference.RefError):
            reference.check(source, serialize_program(target), certificate.to_bytes())


class CorpusAndDeterminismTests(unittest.TestCase):
    def test_corpus_program_count(self):
        self.assertEqual(len(build_specs()), 400)

    def test_corpus_frozen_totals(self):
        specs = build_specs()
        self.assertEqual(sum(len(build_program(spec).commands) for spec in specs), 13464)
        self.assertEqual(sum(spec.capacity for spec in specs), 5782)
        self.assertEqual(sum(header_width(spec.capacity) for spec in specs), 1321)
        self.assertEqual(sum(payload_capacity(spec.capacity) for spec in specs), 4461)

    def test_corpus_three_zero_controls(self):
        zero_families = {"subtraction-control", "state-conflict-control", "trace-order-control"}
        seen = set()
        for spec in build_specs():
            if spec.family in zero_families:
                seen.add(spec.family)
                self.assertEqual(len(select_sites(discover_candidates(build_program(spec)))), 0)
        self.assertEqual(seen, zero_families)

    def test_corpus_declared_capacity_matches_discovery(self):
        for spec in build_specs()[::17]:
            self.assertEqual(len(select_sites(discover_candidates(build_program(spec)))), spec.capacity)

    def test_process_hash_seed_does_not_change_corpus_digest(self):
        code = (
            "import hashlib; from tidemark.corpus import build_specs,build_program; "
            "from tidemark.core import serialize_program; h=hashlib.sha256(); "
            "[h.update(serialize_program(build_program(s))) for s in build_specs()]; print(h.hexdigest())"
        )
        digests = []
        root = pathlib.Path(__file__).resolve().parents[1]
        for seed in ("0", "1", "random"):
            env = dict(os.environ); env["PYTHONHASHSEED"] = seed; env["PYTHONPATH"] = str(root / "src")
            digests.append(subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip())
        self.assertEqual(len(set(digests)), 1)


class StrictRuntimeBoundaryTests(unittest.TestCase):
    def test_integer_constructor_rejects_boolean(self):
        with self.assertRaises(TideMarkError):
            Expr.integer(True)

    def test_boolean_constructor_rejects_integer(self):
        with self.assertRaises(TideMarkError):
            Expr.boolean(1)

    def test_evaluator_rejects_boolean_for_integer_parameter(self):
        source = sample_program()
        with self.assertRaises(TideMarkError):
            evaluate_program(source, {"a": True, "b": 2}, {"r": 0})

    def test_evaluator_rejects_integer_for_boolean_parameter(self):
        source = Program((("flag", Type.BOOL),), (), (), "flag")
        with self.assertRaises(TideMarkError):
            evaluate_program(source, {"flag": 1}, {})

    def test_evaluator_rejects_boolean_for_integer_region(self):
        source = Program((("x", Type.INT),), (("r", Type.INT),), (), "x")
        with self.assertRaises(TideMarkError):
            evaluate_program(source, {"x": 1}, {"r": False})

    def test_site_render_rejects_boolean_bit(self):
        site = select_sites(discover_candidates(sample_program()))[0]
        with self.assertRaises(TideMarkError):
            site.render(True)

    def test_frame_rejects_boolean_bit(self):
        with self.assertRaises(TideMarkError):
            frame_bits((True,), 4)

    def test_unframe_rejects_boolean_bit(self):
        with self.assertRaises(TideMarkError):
            unframe_bits((False, 0, 0))

    def test_header_width_large_integer_boundary(self):
        for exponent in (53, 64, 127, 1024):
            self.assertEqual(header_width((1 << exponent) - 1), exponent)
            self.assertEqual(header_width(1 << exponent), exponent + 1)

    def test_reference_runtime_boundary_matches_production(self):
        source = Program((("flag", Type.BOOL),), (), (), "flag")
        raw = source.to_obj()
        with self.assertRaises(reference.RefError):
            reference.evaluate(raw, {"flag": 1}, {})

    def test_independent_derivation_producers_agree(self):
        source = sample_program(); sites = select_sites(discover_candidates(source)); payload = (1,) * payload_capacity(len(sites))
        target1, derivation1 = build_derivation(source, payload)
        target2, derivation2 = build_reference_derivation(source, payload)
        self.assertEqual(serialize_program(target1), serialize_program(target2))
        self.assertEqual(derivation1.to_bytes(), derivation2.to_bytes())
        self.assertTrue(verify_derivation(source, target1, derivation1, payload))


if __name__ == "__main__":
    unittest.main()
