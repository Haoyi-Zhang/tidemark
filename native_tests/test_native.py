"""Owned arithmetic semantic-connection and exact-target regressions."""
import itertools
import json
import unittest
from dataclasses import replace
from tidemark import core, native

E, C, T = core.Expr, core.Command, core.Type


class NativeTests(unittest.TestCase):
    def test_overflowing_intermediate_and_eager_arm_rejected(self):
        for expr in (E.binary("mul", E.var("a"), E.var("a")),
                     E.choose(E.boolean(False), E.binary("mul", E.var("a"), E.var("a")), E.integer(0))):
            source = core.Program((("a", T.INT),), (), (C("z", expr),), "z")
            with self.assertRaises(native.NativeError):
                native.lower(source, {"a": [1 << 32, 1 << 32]})

    def test_schema_effect_interface_and_box_boundaries(self):
        p = core.Program((("a", T.INT),), (), (C("z", E.var("a")),), "z")
        for box in ({}, {"a": [False, 1]}, {"a": [0.0, 1]}, {"a": [2, 1]},
                    {"a": [native.MIN - 1, 0]}, {"a": [0, native.MAX + 1]}, {"a": [0, 1], "b": [0, 1]}):
            with self.assertRaises(native.NativeError):
                native.lower(p, box)
        for p2 in (replace(p, regions=(("r", T.INT),)),
                   replace(p, commands=(C("z", E.emit(E.var("a"))),)),
                   replace(p, params=(("a", T.UNIT),))):
            with self.assertRaises(native.NativeError):
                native.lower(p2, {"a": [0, 1]})
        for value in (native.MIN, native.MAX):
            self.assertIn(str(value).encode(), native.lower(replace(p, commands=(C("z", E.integer(value)),)), {"a": [0, 0]}))

    def test_all_payloads_overlap_and_literal_identity_ir(self):
        source = core.Program((("a", T.INT), ("flag", T.BOOL)), (),
            (C("x", E.integer(0)), C("y", E.boolean(True)),
             C("p", E.binary("add", E.var("a"), E.integer(1))),
             C("q", E.binary("sub", E.var("a"), E.integer(2))),
             C("r", E.binary("sub", E.var("a"), E.integer(3)))), "r")
        candidates = core.discover_candidates(source)
        sites = core.select_sites(candidates)
        self.assertGreater(len(candidates), len(sites))
        box = {"a": [-3, 3]}
        seen = set()
        for size in range(core.payload_capacity(len(sites)) + 1):
            for payload in itertools.product((0, 1), repeat=size):
                target, ir, wrapper = native.embed(source, payload, box)
                self.assertNotIn(ir, seen)
                seen.add(ir)
                self.assertEqual(native.extract_ir(source, ir, box), payload)
                self.assertEqual(native.check(core.serialize_program(source), core.serialize_program(target), ir, wrapper), payload)
                cert = json.loads(wrapper)
                changed = ir.replace(b"  ret i64 %c72", b"  ret i64 0")
                self.assertNotEqual(changed, ir)
                cert["ir_sha256"] = core.digest_bytes(changed)
                with self.assertRaises(native.NativeError):
                    native.check(core.serialize_program(source), core.serialize_program(target), changed, core.canonical_json(cert))

    def test_llvm_native_boundary_and_conditional(self):
        # This test requires an explicit optional native dependency; it is never
        # silently skipped or reported passed when llvmlite is unavailable.
        from tidemark import native_jit
        native_jit.initialize()
        p = core.Program((("a", T.INT), ("flag", T.BOOL)), (),
            (C("z", E.choose(E.var("flag"), E.binary("sub", E.var("a"), E.integer(1)), E.binary("add", E.var("a"), E.integer(1)))),), "z")
        rows = [(a, flag) for a in (-3, 0, 3) for flag in (0, 1)]
        result, _, obj = native_jit.execute(native.lower(p, {"a": [-3, 3]}), rows)
        expected = [core.evaluate_program(p, {"a": a, "flag": bool(f)}, {})[0] for a, f in rows]
        self.assertEqual(result, expected)
        self.assertGreater(len(obj), 0)

    def test_native_signed_endpoints_and_boolean_return_abi(self):
        from tidemark import native_jit
        native_jit.initialize()
        p = core.Program((("a", T.INT),), (),
                         (C("z", E.binary("add", E.var("a"), E.integer(0))),), "z")
        rows = [(native.MIN,), (native.MAX,)]
        result, _, _ = native_jit.execute(native.lower(p, {"a": [native.MIN, native.MAX]}), rows)
        self.assertEqual(result, [native.MIN, native.MAX])
        rows = list(itertools.product((native.MIN, 0, native.MAX), repeat=2))
        for op in ("eq", "lt"):
            p = core.Program((("a", T.INT), ("b", T.INT)), (),
                             (C("z", E.binary(op, E.var("a"), E.var("b"))),), "z")
            box = {"a": [native.MIN, native.MAX], "b": [native.MIN, native.MAX]}
            result, _, _ = native_jit.execute(native.lower(p, box), rows)
            expected = [int(core.evaluate_program(p, {"a": a, "b": b}, {})[0]) for a, b in rows]
            self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
