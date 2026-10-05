"""Canonical structural records and the declared identifier domain."""
import json
import unittest
from tidemark.core import Program, canonical_json, TideMarkError
from tidemark import reference
from tidemark.structural import Derivation, build_derivation, verify_derivation


class RecordSerializationTests(unittest.TestCase):
    def source(self):
        return {'schema': 'tidemark-ir-3', 'params': [], 'regions': [],
                'commands': [['let', 'x', ['int', 0]]], 'result': 'x'}

    def test_nonempty_derivation_round_trip(self):
        source = Program.from_obj(self.source())
        target, record = build_derivation(source, [])
        self.assertTrue(record.steps)
        restored = Derivation.from_obj(json.loads(record.to_bytes()))
        self.assertTrue(verify_derivation(source, target, restored, []))
        changed = json.loads(record.to_bytes())
        changed['steps'][0]['unknown'] = 0
        self.assertFalse(verify_derivation(source, target, Derivation.from_obj(changed), []))

    def test_empty_names_reject_in_both_parsers(self):
        for field in ('params', 'regions', 'binder', 'result'):
            with self.subTest(field=field):
                obj = self.source()
                if field in ('params', 'regions'):
                    obj[field] = [['', 'Int']]
                elif field == 'binder':
                    obj['commands'][0][1] = ''
                    obj['result'] = ''
                else:
                    obj['result'] = ''
                with self.assertRaises(TideMarkError):
                    Program.from_obj(obj)
                with self.assertRaises(reference.RefError):
                    reference.analyze(reference.parse(canonical_json(obj)))

    def test_zero_step_derivation_round_trip(self):
        source = Program.from_obj({
            'schema': 'tidemark-ir-3', 'params': [['x', 'Int']],
            'regions': [], 'commands': [], 'result': 'x'})
        target, record = build_derivation(source, [])
        self.assertEqual(record.steps, ())
        restored = Derivation.from_obj(json.loads(record.to_bytes()))
        self.assertTrue(verify_derivation(source, target, restored, []))


if __name__ == '__main__':
    unittest.main()
