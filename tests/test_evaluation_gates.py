"""Driver exits must reflect scientific discrepancies, not just enumeration."""
import json
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]
gate = runpy.run_path(str(ROOT / 'scripts/run_evaluation.py'))['scientific_failures']


class EvaluationGateTests(unittest.TestCase):
    def baseline(self):
        return json.loads((ROOT / 'data/derived/evaluation-summary-mode4.json').read_text())

    def test_retained_counts_satisfy_gate_without_claiming_a_rerun(self):
        self.assertEqual(gate(self.baseline()), [])

    def test_discrepancy_acceptance_and_wrong_counts_fail(self):
        for key in ('full_semantic_differences', 'frame_failures', 'accepted_mutations',
                    'reference_accepted_mutations', 'accepted_proof_mutations', 'programs'):
            with self.subTest(key=key):
                summary = self.baseline()
                summary[key] += 1
                self.assertTrue(gate(summary))

    def test_missing_measured_count_fails(self):
        summary = self.baseline()
        del summary['frame_vectors']
        self.assertIn('frame_vectors:count', gate(summary))

    def test_missing_discrepancy_counter_fails(self):
        summary = self.baseline()
        del summary['full_semantic_differences']
        self.assertIn('full_semantic_differences', gate(summary))


if __name__ == '__main__':
    unittest.main()
