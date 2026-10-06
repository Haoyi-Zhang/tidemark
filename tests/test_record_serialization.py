"""Canonical structural records and the declared identifier domain."""
import json
import copy
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

    def test_export_does_not_alias_steps_or_intervals(self):
        source = Program.from_obj(self.source())
        _, record = build_derivation(source, [])
        before = record.to_bytes()
        obj = record.to_obj()
        obj['steps'][0]['family'] = 'unknown'
        obj['steps'][0]['interval'][0] = 7
        self.assertEqual(record.to_bytes(), before)

    def test_import_does_not_alias_steps_or_intervals(self):
        source = Program.from_obj(self.source())
        _, record = build_derivation(source, [])
        obj = record.to_obj()
        restored = Derivation.from_obj(obj)
        before = restored.to_bytes()
        obj['steps'][0]['family'] = 'unknown'
        obj['steps'][0]['interval'][0] = 7
        self.assertEqual(restored.to_bytes(), before)

    def test_record_numeric_fields_reject_boolean_and_float_aliases(self):
        source = Program.from_obj(self.source())
        target, record = build_derivation(source, [])
        for field in ('selected', 'framed_bits', 'interval', 'bit'):
            for value in (False, 0.0):
                with self.subTest(field=field, value=value):
                    obj = copy.deepcopy(record.to_obj())
                    if field == 'selected': obj[field][0][1] = value
                    elif field == 'framed_bits': obj[field][0] = value
                    elif field == 'interval': obj['steps'][0][field][0] = value
                    else: obj['steps'][0][field] = value
                    self.assertFalse(verify_derivation(source, target, Derivation.from_obj(obj), []))

    def test_each_step_field_mutation_starts_from_the_same_record(self):
        source = Program.from_obj(self.source())
        target, record = build_derivation(source, [])
        before = record.to_bytes()
        for field in ('family', 'interval', 'bit', 'before_sha256', 'after_sha256'):
            with self.subTest(field=field):
                obj = record.to_obj()
                obj['steps'][0][field] = {
                    'family': 'unknown', 'interval': [1, 1], 'bit': 1,
                    'before_sha256': '0' * 64, 'after_sha256': 'f' * 64,
                }[field]
                self.assertFalse(verify_derivation(source, target, Derivation.from_obj(obj), []))
                self.assertEqual(record.to_bytes(), before)

    def test_all_frame_vectors_against_independent_length_and_padding_rule(self):
        from tidemark.core import frame_bits, unframe_bits
        # Includes expected rejects: a decoder that rejects every input must fail.
        valid_count = 0
        for n in range(17):
            width = n.bit_length()
            for value in range(1 << n):
                bits = tuple((value >> shift) & 1 for shift in reversed(range(n)))
                length = value >> (n - width) if width else 0
                expected_valid = length <= n - width
                if expected_valid:
                    expected_valid = not any(bits[width + length:])
                try:
                    payload = unframe_bits(bits)
                except TideMarkError:
                    self.assertFalse(expected_valid)
                else:
                    self.assertTrue(expected_valid)
                    self.assertEqual(payload, bits[width:width + length])
                    self.assertEqual(frame_bits(payload, n), bits)
                    valid_count += 1
        self.assertEqual(valid_count, 12309)


if __name__ == '__main__':
    unittest.main()
