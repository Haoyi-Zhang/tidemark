"""The retained numeric export has one byte format on Windows and Linux."""
from pathlib import Path
import contextlib,io,json,runpy,shutil,sys,tempfile,types,unittest
from unittest import mock

A=Path(__file__).resolve().parents[1]

class ExportNewlineTests(unittest.TestCase):
    def test_macro_json_and_table_are_utf8_with_lf(self):
        with tempfile.TemporaryDirectory(prefix='tidemark-export-format-') as temp:
            root=Path(temp)
            scripts=root/'artifact/scripts';scripts.mkdir(parents=True)
            data=root/'artifact/data/derived';data.mkdir(parents=True)
            paper=root/'paper';paper.mkdir()
            for name in ('evaluation-summary-mode4.json','llvm-projection-mode4.json','finite-algebra-mode4.json'):
                shutil.copy2(A/'data/derived'/name,data/name)
            path=scripts/'export_paper_data.py'
            shutil.copy2(A/'scripts/export_paper_data.py',path)
            with mock.patch.dict(sys.modules,{'export_overlap_data':types.SimpleNamespace(export=lambda:None)}),contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(path),run_name='__main__')
            for name in ('data-macros.tex','data-macros.json','tables/carrier-ablation-rows.tex'):
                value=(paper/name).read_bytes()
                self.assertNotIn(b'\r',value)
                self.assertTrue(value.endswith(b'\n'))
                value.decode('utf-8')
            record=json.loads((paper/'data-macros.json').read_text(encoding='utf-8'))
            self.assertEqual(record['values']['Programs'],400)
            self.assertEqual(record['values']['PayloadBits'],4461)

if __name__=='__main__':unittest.main()
