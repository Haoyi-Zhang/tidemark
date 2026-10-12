"""Portable same-goal baseline and fail-gate regressions."""
import copy
import itertools
import json
from pathlib import Path
import runpy
import unittest

from tidemark import core, reference, overlap

driver = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/run_overlap_comparison.py"))


class OverlapComparisonTests(unittest.TestCase):
    def test_literal_optimum_and_strict_source_first_loss(self):
        E, C, T = core.Expr, core.Command, core.Type
        source = core.Program((("a", T.INT), ("b", T.INT)), (),
            tuple(C(f"v{i}", E.var("a")) for i in range(6)), "v5")
        candidates = core.discover_candidates(source)
        refs = reference.candidates(source.to_obj())
        literal = max(sum(mask) for mask in itertools.product((0, 1), repeat=len(refs))
                      if all(not mask[i] or not mask[j] or a[2] < b[1] or b[2] < a[1]
                             for i, a in enumerate(refs) for j, b in enumerate(refs) if i < j))
        self.assertEqual(literal, overlap.optimum_count(refs, len(source.commands)))
        self.assertEqual(literal, len(overlap.select(candidates, "mode4")))
        self.assertLess(len(overlap.select(candidates, "source-first")), literal)
        self.assertEqual(len(overlap.select(candidates, "singleton-first")), literal)

    def test_baselines_are_checked_embeddings_not_counts(self):
        fixtures = list(overlap.sources())
        for index in (0, 17, 49, 83, 97, 133, 149, 190):
            source = fixtures[index][-1]
            refs = reference.candidates(source.to_obj())
            for p in overlap.POLICIES:
                candidates = core.discover_candidates(source)
                sites = overlap.select(candidates, p)
                self.assertEqual(sites, overlap.select(tuple(reversed(candidates)), p))
                self.assertEqual(driver["descriptors"](sites), json.loads(reference.canon(overlap.reference_select(refs, p))))
                capacity = core.payload_capacity(len(sites))
                for payload in ((), tuple(i % 2 for i in range(capacity))):
                    target, cert = overlap.embed(source, payload, p)
                    args = core.serialize_program(source), core.serialize_program(target), cert, p
                    self.assertEqual(overlap.check(*args), payload)
                    self.assertEqual(overlap.reference_check(*args), payload)
                    self.assertEqual(overlap.extract(source, target, p), payload)
                    for params, store in overlap.STATES:
                        obs = core.evaluate_program(source, params, store)
                        self.assertEqual(core.evaluate_program(target, params, store), obs)
                        self.assertEqual(reference.evaluate(target.to_obj(), params, store), obs)
                    for _, bad_target, bad_cert in overlap.mutations(target, cert):
                        with self.assertRaises(ValueError):
                            overlap.check(args[0], bad_target, bad_cert, p)
                        with self.assertRaises(ValueError):
                            overlap.reference_check(args[0], bad_target, bad_cert, p)
                with self.assertRaises(core.TideMarkError):
                    overlap.embed(source, (0,) * (capacity + 1), p)

    def test_schema_and_policy_not_interchangeable(self):
        source = next(overlap.sources())[-1]
        target, cert = overlap.embed(source, (), "source-first")
        args = core.serialize_program(source), core.serialize_program(target), cert
        with self.assertRaises(ValueError):
            core.check_certificate(*args)
        with self.assertRaises(ValueError):
            overlap.check(*args, "singleton-first")
        for value in ((True,), (0.0,), (2,)):
            with self.assertRaises(core.TideMarkError):
                overlap.embed(source, value, "source-first")

    def test_gates_fail_on_missing_or_nonzero_measurements(self):
        counts = {key: 0 for key in driver["FAILURES"]}
        counts.update(programs=192, attempts=2304, embeddings=1,
                      full_comparisons=6, mutations=2, overlap_programs=1, conflict_pairs=1)
        for family in ("identity", "operand", "adjacent"):
            for bit in (0, 1):
                counts[f"oriented_{family}_{bit}"] = 1
        summary = {"counts": counts, "policies": {"mode4": {"discarded_candidates": 1}}}
        gate = driver["scientific_failures"]
        self.assertEqual(gate(summary), [])
        for key in driver["FAILURES"]:
            bad = copy.deepcopy(summary)
            bad["counts"][key] = 1
            self.assertIn(key, gate(bad))
            del bad["counts"][key]
            self.assertIn(key, gate(bad))
        bad = copy.deepcopy(summary)
        bad["counts"]["overlap_programs"] = 0
        self.assertIn("no-overlap", gate(bad))


if __name__ == "__main__":
    unittest.main()
