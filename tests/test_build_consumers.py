"""Current invocation identity and complete-project/code-only build consumers."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ARTIFACT = Path(__file__).resolve().parents[1]


class BuildConsumerTests(unittest.TestCase):
    def invoke(self, *, paper=True, fail=None, audit=None, require_paper=False):
        with tempfile.TemporaryDirectory(prefix='tidemark-consumer-test-') as td:
            root = Path(td)
            artifact = root / 'artifact'
            (artifact / 'scripts').mkdir(parents=True)
            (artifact / 'data/derived').mkdir(parents=True)
            (artifact / 'audit/current').mkdir(parents=True)
            script = artifact / 'scripts/verify_all.py'
            shutil.copy2(ARTIFACT / 'scripts/verify_all.py', script)
            stale = {'schema': 'tidemark-current-pdf-audit-2', 'pages': 36,
                     'pdf_sha256': '0' * 64, 'previous_48_page_goal_met': False}
            (artifact / 'audit/current/pdf-audit.json').write_text(json.dumps(stale))
            if paper:
                (root / 'paper').mkdir()
                (root / 'paper/main.pdf').write_bytes(b'owned fake PDF for binding test')
            current = {'schema': 'tidemark-current-pdf-audit-3', 'pages': 42,
                       'pdf_sha256': hashlib.sha256(b'owned fake PDF for binding test').hexdigest(),
                       'all_mechanical_checks_passed': True}
            calls = []

            def run(cmd, **kwargs):
                calls.append((cmd, kwargs['cwd']))
                key = 'paper-build' if cmd == ['bash', 'build.sh'] else Path(cmd[-1]).name
                output = json.dumps(current if audit is None else audit) if key == 'audit_final_pdf.py' else 'owned test component\n'
                return subprocess.CompletedProcess(cmd, int(key == fail), output)

            argv = [str(script)] + (['--include-paper'] if require_paper else [])
            with mock.patch.object(sys, 'argv', argv), mock.patch('subprocess.run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exited:
                    runpy.run_path(str(script), run_name='__main__')
            out = artifact / 'data/derived/verification-matrix-current.json'
            result = json.loads(out.read_text()) if out.exists() else None
            self.assertEqual(json.loads((artifact / 'audit/current/pdf-audit.json').read_text()), stale)
            return exited.exception.code, result, calls

    def test_complete_package_uses_build_entry_and_fresh_pdf_stdout(self):
        code, result, calls = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(any(cmd == ['bash', 'build.sh'] and cwd.name == 'paper' for cmd, cwd in calls))
        self.assertEqual(result['actual_pdf_pages'], 42)
        self.assertEqual(len(result['actual_pdf_sha256']), 64)
        self.assertEqual(result['paper_components_not_executed'], [])
        self.assertFalse(result['measurements_refreshed_in_this_invocation'])
        self.assertFalse(any('run_evaluation.py' in cmd for cmd, _ in calls))
        self.assertNotIn('earlier_exact_48_page_goal_met', result)

    def test_code_checkout_never_consumes_archived_pdf(self):
        code, result, calls = self.invoke(paper=False)
        self.assertEqual(code, 0)
        self.assertIsNone(result['actual_pdf_pages'])
        self.assertIsNone(result['actual_pdf_sha256'])
        self.assertFalse(result['paper_checks_available'])
        self.assertEqual(len(result['paper_components_not_executed']), 3)
        self.assertFalse(any(cmd == ['bash', 'build.sh'] for cmd, _ in calls))

    def test_include_paper_requires_the_paper_tree(self):
        code, result, calls = self.invoke(paper=False, require_paper=True)
        self.assertIsInstance(code, str)
        self.assertIn('Full-project input required', code)
        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_failures_do_not_reuse_stale_pages_or_claim_unrun_paper_checks(self):
        for fail in ('discover', 'paper-build', 'audit_references.py', 'audit_final_pdf.py'):
            # Unit-test command ends in -v; use it to fail before any paper component.
            with self.subTest(fail=fail):
                key = '-v' if fail == 'discover' else fail
                code, result, _ = self.invoke(fail=key)
                self.assertEqual(code, 1)
                self.assertIsNone(result['actual_pdf_pages'])
                self.assertFalse(result['all_executed_components_passed'])
                if fail == 'discover':
                    self.assertEqual(len(result['paper_components_not_executed']), 3)

    def test_success_exit_with_stale_or_unbound_metadata_fails(self):
        for audit in ({'schema': 'tidemark-current-pdf-audit-2', 'pages': 36},
                      {'schema': 'tidemark-current-pdf-audit-3', 'pages': 42,
                       'pdf_sha256': '0' * 64, 'all_mechanical_checks_passed': True},
                      {'schema': 'tidemark-current-pdf-audit-3', 'pages': 42,
                       'all_mechanical_checks_passed': False}):
            with self.subTest(audit=audit):
                code, result, _ = self.invoke(audit=audit)
                self.assertEqual(code, 1)
                self.assertIsNone(result['actual_pdf_pages'])
                self.assertFalse(result['all_executed_components_passed'])

    def test_complete_package_builds_main_with_xelatex(self):
        paper = ARTIFACT.parent / 'paper'
        if not paper.is_dir():
            self.skipTest('standalone code checkout has no manuscript build entry')
        build = (paper / 'build.sh').read_text()
        engines = [line.split()[0] for line in build.splitlines()
                   if line.startswith(('xelatex ', 'pdflatex '))]
        self.assertEqual(engines, ['xelatex'] * 3)
        self.assertIn('bash build.sh', (paper / 'Makefile').read_text())

    def test_pdf_auditor_has_no_packaging_page_goal(self):
        source = (ARTIFACT / 'scripts/audit_final_pdf.py').read_text()
        self.assertNotIn('previous_48_page_goal_met', source)
        self.assertIn('tidemark-current-pdf-audit-3', source)


if __name__ == '__main__':
    unittest.main()
