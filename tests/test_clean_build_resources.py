"""PDF resources close before temporary cleanup, including exceptional exits.

The fixture uses inert fake PDF pages; default core tests do not require fitz,
TeX or a real compiler. Actual clean builds are a separate full-project check.
"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class CleanBuildResourceTests(unittest.TestCase):
    def invoke(self, *, fail_open=False, fail_page=False, difference=False, fail_cleanup=False, omit_native=False):
        with tempfile.TemporaryDirectory(prefix='tidemark-resource-test-') as td:
            root = Path(td) / 'project'
            artifact = root / 'artifact'
            (artifact / 'scripts').mkdir(parents=True)
            (root / 'paper/figures').mkdir(parents=True)
            (root / 'paper/tables').mkdir()
            script = artifact / 'scripts/check_clean_build.py'
            shutil.copy2(ROOT / 'scripts/check_clean_build.py', script)
            names = ['main.pdf', 'data-macros.tex', 'data-macros.json',
                     'tables/carrier-ablation-rows.tex', 'overlap-data.tex',
                     'tables/overlap-comparison.tex'] + [f'figures/figure-{i:02}.pdf' for i in range(1, 7)] + ['figures/native-connection.pdf', 'figures/evaluation-capacity.pdf', 'figures/evaluation-cost.pdf']
            for name in names: (root / 'paper' / name).write_bytes(b'owned inert fixture')
            opened = []
            cleaned = []
            real_temp = tempfile.TemporaryDirectory

            @contextlib.contextmanager
            def tempdir(*args, **kwargs):
                with real_temp(*args, **kwargs) as temp:
                    try:
                        yield temp
                    finally:
                        self.assertTrue(all(doc.closed for doc in opened), 'PDF handle leaked before tree cleanup')
                        cleaned.append(temp)
                        if fail_cleanup: raise OSError('owned cleanup failure must propagate')

            class Page:
                def get_text(self):
                    if fail_page: raise RuntimeError('owned page-read failure')
                    return 'owned page'

                def get_pixmap(self, **kwargs):
                    return types.SimpleNamespace(samples=b'owned pixels')

            class Document:
                def __init__(self): self.closed = False
                def __enter__(self): return self
                def __exit__(self, *args): self.closed = True
                def __len__(self): return 1
                def __iter__(self): return iter([Page()])

            def pdf_open(path):
                if not Path(path).is_file(): raise FileNotFoundError(path)
                if fail_open and len(opened) == 1: raise RuntimeError('owned second-open failure')
                doc = Document()
                if difference and len(opened) == 1:
                    doc.__class__ = type('DifferentDocument', (Document,), {'__iter__': lambda self: iter([types.SimpleNamespace(get_text=lambda: 'different page', get_pixmap=lambda **kwargs: types.SimpleNamespace(samples=b'different pixels'))])})
                opened.append(doc)
                return doc

            def build(cmd, cwd, **kwargs):
                self.assertEqual(cmd, ['bash', 'build.sh'])
                for name in names:
                    if omit_native and name == 'figures/native-connection.pdf': continue
                    (cwd / name).write_bytes(b'owned inert fixture')
                return subprocess.CompletedProcess(cmd, 0, 'owned build output\n')

            fake_fitz = types.SimpleNamespace(open=pdf_open, Matrix=lambda *args: args)
            error = None
            with mock.patch.dict(sys.modules, {'fitz': fake_fitz}), mock.patch('subprocess.run', side_effect=build), mock.patch('tempfile.TemporaryDirectory', side_effect=tempdir), contextlib.redirect_stdout(io.StringIO()):
                try:
                    runpy.run_path(str(script), run_name='__main__')
                except (SystemExit, RuntimeError, OSError) as exc:
                    error = exc
            self.assertTrue(all(doc.closed for doc in opened))
            self.assertEqual(len(cleaned), 1)
            self.assertFalse(Path(cleaned[0]).exists())
            output = artifact / 'audit/current/clean-build.json'
            record = json.loads(output.read_text()) if output.exists() else None
            return error, record, len(opened)

    def test_all_sixteen_documents_closed_before_success_cleanup(self):
        error, record, count = self.invoke()
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(error.code, 0)
        self.assertEqual(count, 16)
        self.assertTrue(record['passed'])
        self.assertEqual(len(record['comparisons']), 8)
        self.assertIn('paper/figures/native-connection.pdf', [r['file'] for r in record['comparisons']])
        self.assertIn('paper/figures/native-connection.pdf', record['generated_files_deleted_before_build'])

    def test_stale_native_figure_cannot_survive_an_incomplete_build(self):
        error, record, count = self.invoke(omit_native=True)
        self.assertIsInstance(error, FileNotFoundError)
        self.assertEqual(count, 15)
        self.assertIsNone(record)

    def test_first_document_closes_when_second_open_fails(self):
        error, record, count = self.invoke(fail_open=True)
        self.assertIsInstance(error, RuntimeError)
        self.assertIn('second-open', str(error))
        self.assertEqual(count, 1)
        self.assertIsNone(record)

    def test_both_documents_close_when_page_read_raises(self):
        error, record, count = self.invoke(fail_page=True)
        self.assertIsInstance(error, RuntimeError)
        self.assertIn('page-read', str(error))
        self.assertEqual(count, 2)
        self.assertIsNone(record)

    def test_real_comparison_difference_still_fails(self):
        error, record, count = self.invoke(difference=True)
        self.assertEqual(error.code, 1)
        self.assertEqual(count, 16)
        self.assertFalse(record['passed'])
        self.assertFalse(record['comparisons'][0]['text_equal'])
        self.assertFalse(record['comparisons'][0]['render_equal_at_108dpi'])

    def test_cleanup_errors_are_not_ignored_or_swallowed(self):
        error, record, count = self.invoke(fail_cleanup=True)
        self.assertIsInstance(error, OSError)
        self.assertIn('cleanup failure', str(error))
        self.assertTrue(record['passed'])
        self.assertEqual(count, 16)


if __name__ == '__main__':
    unittest.main()
