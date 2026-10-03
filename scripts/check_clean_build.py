#!/usr/bin/env python3
"""Delete all seven PDFs and generated data in a copy; rebuild and compare."""
from pathlib import Path
import shutil,tempfile,subprocess,json,hashlib,os
import fitz
A=Path(__file__).resolve().parents[1];R=A.parent
if not (R/'paper').is_dir():raise SystemExit('Full-project input required: clean manuscript rebuilding needs the sibling paper tree.')
O=A/'audit/current';O.mkdir(exist_ok=True,parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='tidemark-clean-build-') as temp:
 T=Path(temp)/'TOPLAS-20';shutil.copytree(R,T,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 P=T/'paper';to_delete=[P/'main.pdf',P/'data-macros.tex',P/'data-macros.json',P/'tables/carrier-ablation-rows.tex']+list((P/'figures').glob('figure-*.pdf'))
 for f in to_delete:f.unlink(missing_ok=True)
 for ext in ['*.aux','*.bbl','*.blg','*.log','*.out','*.fls','*.fdb_latexmk']:
  for f in P.glob(ext):f.unlink()
 cp=subprocess.run(['bash','build.sh'],cwd=P,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (O/'clean-build.log').write_text(cp.stdout.replace(str(T),'.'))
 if cp.returncode:raise SystemExit('clean build failed '+str(cp.returncode))
 results=[]
 for rel in ['paper/main.pdf']+[f'paper/figures/figure-{i:02}.pdf' for i in range(1,7)]:
  a=fitz.open(R/rel);b=fitz.open(T/rel)
  same_pages=len(a)==len(b)
  texts=same_pages and all(x.get_text()==y.get_text() for x,y in zip(a,b))
  pixels=same_pages and all(x.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).samples==y.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).samples for x,y in zip(a,b))
  results.append({'file':rel,'pages':len(a),'rebuilt_pages':len(b),'text_equal':texts,'render_equal_at_108dpi':pixels,'byte_equal':sha(R/rel)==sha(T/rel),'delivered_sha256':sha(R/rel),'rebuilt_sha256':sha(T/rel)})
 macros_same=(R/'paper/data-macros.tex').read_bytes()==(P/'data-macros.tex').read_bytes()
 result={'schema':'tidemark-from-source-clean-build-1','exit_code':cp.returncode,'generated_files_deleted_before_build':[f.relative_to(T).as_posix() for f in to_delete],'macro_bytes_equal':macros_same,'comparisons':results,'passed':macros_same and all(r['text_equal'] and r['render_equal_at_108dpi'] for r in results),'note':'Byte differences, when present, are reported rather than hidden. Acceptance requires identical text and rendered pages from the included current sources and frozen results.'}
 (O/'clean-build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
