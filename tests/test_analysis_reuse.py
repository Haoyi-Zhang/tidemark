"""Owned finite overlap regression; raw-tree semantics plus a literal subset oracle."""
import ast
import copy
import dataclasses
import itertools
import json
from pathlib import Path
import unittest
from unittest import mock

from tidemark import core, reference, structural


LENGTHS = (0, 1, 2, 3, 5, 8)
STATES = tuple(
    ({"a": a, "b": b, "flag": flag}, {"r": r, "s": s})
    for a, b, flag, r, s in (
        (-3, 2, False, -1, 4), (0, 0, True, 0, 0),
        (2, -5, False, 7, -2), (9, 3, True, -8, 6),
        (-11, -1, True, 4, 4), (1, 8, False, 3, -7),
    )
)


def fixtures():
    """Four named families, six sizes/renamings; at most eight commands."""
    for family in ("identity-overlap", "operand-overlap", "adjacent-chain", "state-trace"):
        for variant, size in enumerate(LENGTHS):
            commands = []
            for i in range(size):
                name = f"v{variant}_{size - i}"
                a, b = ["var", "a"], ["var", "b"]
                if family == "identity-overlap":
                    base = ["var", "flag"] if i % 2 else a
                    op, neutral = ("eq", ["bool", True]) if i % 2 else ("add", ["int", 0])
                    expr = ["bin", op, base, neutral] if (variant + i) % 2 else base
                elif family == "operand-overlap":
                    left, right = (a, b) if (variant + i) % 2 else (b, a)
                    expr = ["bin", ("add", "mul", "eq")[i % 3], left, right]
                elif family == "adjacent-chain":
                    left = ["var", commands[-1][1]] if variant % 2 and i % 3 == 1 else a
                    expr = ["bin", "sub", left, ["int", i + 1]]
                else:
                    expr = (
                        ["put", "r", a],
                        ["get", "r" if variant % 2 else "s"],
                        ["emit", b],
                        ["emit", a] if variant == 4 else ["bin", "sub", a, b],
                    )[i % 4]
                commands.append(["let", name, expr])
            yield f"{family}-{variant}", {
                "schema": "tidemark-ir-3",
                "params": [["a", "Int"], ["b", "Int"], ["flag", "Bool"]],
                "regions": [["r", "Int"], ["s", "Int"]],
                "commands": commands,
                "result": commands[-1][1] if commands else "a",
            }


def descriptor(site):
    return json.dumps(list(site), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def literal_schedule(candidates):
    """Cartesian subsets, maximum size, then earliest-priority index sequence.

    This does not call either selector or a production Site method.
    """
    rank = {"identity": 0, "operand": 1, "adjacent": 2}
    ordered = sorted(candidates, key=lambda s: (s[2], s[1], rank[s[0]], descriptor(s)))
    assert len(ordered) <= 15
    masks = [sum(1 << i for i in range(s[1], s[2] + 1)) for s in ordered]
    best = ()
    for flags in itertools.product((0, 1), repeat=len(ordered)):
        used, indices = 0, []
        for index, flag in enumerate(flags):
            if flag:
                if used & masks[index]:
                    break
                used |= masks[index]
                indices.append(index)
        else:
            indices = tuple(indices)
            if len(indices) > len(best) or (len(indices) == len(best) and indices < best):
                best = indices
    return sorted((ordered[i] for i in best), key=lambda s: (s[1], s[2], s[0]))


def literal_frame(payload, size):
    width = 0
    while (1 << width) <= size:
        width += 1
    assert len(payload) <= size - width
    header = tuple((len(payload) // (1 << i)) % 2 for i in range(width - 1, -1, -1))
    return header + tuple(payload) + (0,) * (size - width - len(payload))


def messages(size):
    width = len(bin(size)[2:]) if size else 0
    for length in range(size - width + 1):
        yield from itertools.product((0, 1), repeat=length)


def production_descriptors(sites):
    return [site.descriptor_bytes for site in sites]


def failure(call):
    try:
        call()
    except Exception as exc:
        return type(exc).__name__, str(exc)
    raise AssertionError("expected rejection")


class AnalysisReuseRegression(unittest.TestCase):
    def test_complete_discovery_and_literal_maximum_schedule(self):
        overlap_count = positive = 0
        for name, raw in fixtures():
            with self.subTest(name=name):
                source = core.Program.from_obj(raw)
                expected = reference.candidates(raw)
                actual = core.discover_candidates(source)
                self.assertEqual(production_descriptors(actual), [descriptor(s) for s in expected])
                selected = core.select_sites(actual)
                literal = literal_schedule(expected)
                self.assertEqual(production_descriptors(selected), [descriptor(s) for s in literal])
                self.assertEqual([descriptor(s) for s in reference.select(expected)],
                                 [descriptor(s) for s in literal])
                self.assertEqual(selected, core.select_sites(tuple(reversed(actual))))
                overlap_count += len(actual) > len(selected)
                positive += core.payload_capacity(len(selected)) > 0
        self.assertGreater(overlap_count, 0)
        self.assertGreater(positive, 0)

    def test_all_payloads_targets_certificates_records_and_complete_observations(self):
        for name, raw in fixtures():
            source = core.Program.from_obj(raw)
            sites = core.select_sites(core.discover_candidates(source))
            ref_sites = reference.select(reference.candidates(raw))
            saved = copy.deepcopy(raw)
            for payload in messages(len(sites)):
                with self.subTest(name=name, payload=payload):
                    bits = literal_frame(payload, len(sites))
                    self.assertEqual(core.frame_bits(payload, len(sites)), bits)
                    self.assertEqual(tuple(reference.frame(list(payload), len(sites))), bits)
                    target, cert = core.embed(source, payload)
                    self.assertEqual(core.replay(source, sites, bits), target)
                    self.assertEqual(core.replay(source, tuple(reversed(sites)), tuple(reversed(bits))), target)
                    expected_target = reference.replay(raw, ref_sites, list(bits))
                    args = core.serialize_program(source), core.serialize_program(target), cert.to_bytes()
                    self.assertEqual(args[1], reference.canon(expected_target))
                    self.assertEqual(core.check_certificate(*args), payload)
                    self.assertEqual(reference.check(*args), payload)
                    self.assertEqual(core.extract_payload(source, target), payload)
                    self.assertEqual(tuple(reference.extract(raw, expected_target)), payload)
                    t1, record = structural.build_derivation(source, payload)
                    t2, independent_record = structural.build_reference_derivation(source, payload)
                    self.assertEqual(t1, target)
                    self.assertEqual(t2, target)
                    self.assertEqual(record.to_bytes(), independent_record.to_bytes())
                    self.assertEqual(structural.verify_derivation_detailed(source, target, record, payload),
                                     (True, "accepted"))
                    restored = structural.Derivation.from_obj(json.loads(record.to_bytes()))
                    self.assertEqual(restored.to_bytes(), record.to_bytes())
                    for params, store in STATES:
                        inputs = copy.deepcopy((params, store))
                        observation = core.evaluate_program(source, params, store)
                        self.assertEqual(core.evaluate_program(target, params, store), observation)
                        self.assertEqual(reference.evaluate(raw, params, store), observation)
                        self.assertEqual(reference.evaluate(expected_target, params, store), observation)
                        self.assertEqual((params, store), inputs)
                    self.assertEqual(source.to_obj(), saved)
                    self.assertEqual(raw, saved)

    def test_call_local_analysis_counts_and_current_extractor_call(self):
        for name, raw in fixtures():
            source = core.Program.from_obj(raw)
            with self.subTest(name=name):
                with mock.patch.object(core, "typecheck_program", wraps=core.typecheck_program) as check:
                    core.discover_candidates(source)
                    self.assertEqual(check.call_count, 1)
                with mock.patch.object(core, "typecheck_program", wraps=core.typecheck_program) as check:
                    target, cert = core.embed(source, ())
                    self.assertEqual(check.call_count, 2)  # source and replay target
                with mock.patch.object(core, "typecheck_program", wraps=core.typecheck_program) as check:
                    core.extract_payload(source, target)
                    self.assertEqual(check.call_count, 2)  # source then supplied target
                with mock.patch.object(core, "typecheck_program", wraps=core.typecheck_program) as check:
                    with mock.patch.object(core, "extract_payload", wraps=core.extract_payload) as extract:
                        core.check_certificate(core.serialize_program(source),
                                               core.serialize_program(target), cert.to_bytes())
                        self.assertEqual(check.call_count, 4)
                        self.assertEqual(extract.call_count, 1)

    def test_validation_order_and_no_analysis_across_calls(self):
        raw = list(fixtures())[3][1]
        good = core.Program.from_obj(raw)
        bad_source = dataclasses.replace(good, result="missing_source")
        bad_target = dataclasses.replace(good, result="missing_target")
        for source, target, count in ((bad_source, bad_target, 1), (good, bad_target, 2)):
            expected = failure(lambda: core.typecheck_program(source if count == 1 else target))
            with mock.patch.object(core, "typecheck_program", wraps=core.typecheck_program) as check:
                with mock.patch.object(core, "_discover_candidates_analyzed",
                                       wraps=core._discover_candidates_analyzed) as discover:
                    self.assertEqual(failure(lambda: core.extract_payload(source, target)), expected)
                    self.assertEqual(check.call_count, count)
                    discover.assert_not_called()
        with mock.patch.object(core, "typecheck_program", wraps=core.typecheck_program) as check:
            failure(lambda: core.extract_payload(bad_source, bad_target, "unsupported"))
            check.assert_not_called()
        changed = dataclasses.replace(good, commands=())
        changed = dataclasses.replace(changed, result="a")
        self.assertNotEqual(core.discover_candidates(good), core.discover_candidates(changed))
        self.assertEqual(core.embed(good, ())[0], core.embed(good, ())[0])
        self.assertEqual(core.embed(changed, ())[0], changed)

    def test_exact_negative_boundaries_and_isolated_record_mutations(self):
        source = core.Program.from_obj(list(fixtures())[5][1])
        target, cert = core.embed(source, ())
        for payload in ((True,), (0.0,), (0,) * 5):
            self.assertEqual(failure(lambda: core.embed(source, payload))[0], "TideMarkError")
        failure(lambda: core.unframe_bits((1, 1, 1)))  # declared length exceeds capacity
        failure(lambda: core.unframe_bits((0, 0, 1)))  # nonzero padding
        changed = dataclasses.replace(target, result="b")
        data = core.serialize_program(changed)
        forged = dataclasses.replace(cert, target_sha256=core.digest_bytes(data))
        args = core.serialize_program(source), data, forged.to_bytes()
        self.assertEqual(failure(lambda: core.check_certificate(*args))[1],
                         "target is not exact canonical replay")
        self.assertEqual(failure(lambda: reference.check(*args))[0], "RefError")
        _, record = structural.build_derivation(source, ())
        original = record.to_bytes()
        for field, value in (("family", "unknown"), ("interval", [9, 9]),
                             ("bit", True), ("before_sha256", "0" * 64),
                             ("after_sha256", "f" * 64)):
            obj = record.to_obj()
            obj["steps"][0][field] = value
            self.assertFalse(structural.verify_derivation(source, target,
                             structural.Derivation.from_obj(obj), ()))
            self.assertEqual(record.to_bytes(), original)

    def test_reference_does_not_import_production_semantics(self):
        path = Path(reference.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("core", (node.module or "").split("."))
                self.assertFalse(any(alias.name == "core" for alias in node.names))
            elif isinstance(node, ast.Import):
                self.assertFalse(any("core" in alias.name.split(".") for alias in node.names))


if __name__ == "__main__":
    unittest.main()

