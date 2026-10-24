import unittest
from pathlib import Path
from tidemark import core, native, python_subset


class PythonSubsetTests(unittest.TestCase):
    def test_owned_quote_and_exact_types(self):
        text = (Path(__file__).resolve().parents[1] / "examples/shipping_quote.py").read_text()
        p = python_subset.translate(text)
        fn = python_subset.validated_function(text)
        for u in range(6):
            for w in range(5):
                for flag in (False, True):
                    expected = 120*u + 15*w + u + 2 + (55 if flag else 5)
                    self.assertEqual(fn(u, w, flag), expected)
                    self.assertEqual(core.evaluate_program(p, {"units": u, "weight": w, "priority": flag}, {})[0], expected)
        native.admit(p, {"units": [0, 5], "weight": [0, 4]})
        with self.assertRaises(core.TideMarkError):
            core.evaluate_program(p, {"units": True, "weight": 0, "priority": False}, {})

    def test_unsupported_syntax_never_falls_back(self):
        samples = [
            "def f(x:int)->int:\n y=abs(x)\n return y",
            "def f(x:int=1)->int:\n return x",
            "@decorator\ndef f(x:int)->int:\n return x",
            "def f(x:int)->int:\n y=x.real\n return y",
            "def f(x:int)->int:\n x=x+1\n return x",
            "def f(x:int)->int:\n y=x/2\n return y",
            "def f(x:int)->int:\n y=x<2<3\n return x",
            "def f(x:int)->int:\n y=True\n return y",
            "import os\ndef f(x:int)->int:\n return x",
            "def f(x:int)->int:\n for y in []: pass\n return x",
        ]
        for text in samples:
            with self.subTest(text=text), self.assertRaises(core.TideMarkError):
                python_subset.translate(text)

    def test_exact_prepass_decode_and_whole_ir_binding(self):
        text = (Path(__file__).resolve().parents[1] / "examples/shipping_quote.py").read_text()
        p = python_subset.translate(text)
        box = {"units": [0, 5], "weight": [0, 4]}
        for message in ((0,), (1,)):
            q, ir, wrapper = native.embed(p, message, box)
            self.assertEqual(native.check(core.serialize_program(p), core.serialize_program(q), ir, wrapper), message)
            with self.assertRaises(core.TideMarkError):
                native.check(core.serialize_program(p), core.serialize_program(q), ir + b"\n", wrapper)
