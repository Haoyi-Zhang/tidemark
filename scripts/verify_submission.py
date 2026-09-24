#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; PAPER=ROOT/'paper'; ART=ROOT/'artifact'; PDF=PAPER/'main.pdf'; findings=[]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(a): return subprocess.run(a,cwd=ROOT,text=True,capture_output=True)
def csvrows(p):
 try: return list(csv.DictReader(p.open(encoding='utf-8',newline='')))
 except Exception as e: findings.append(f'cannot read {p.relative_to(ROOT)}: {e}'); return []
if set(p.name for p in ROOT.iterdir())!={'paper','artifact','research-plan.md','CURRENT-STATE.md'}: findings.append('root contract')
info=run(['pdfinfo',str(PDF)]).stdout; text=run(['pdftotext','-layout',str(PDF),'-']).stdout
for x in ['Pages:           48','Page size:       486 x 720 pts','Author:          Haoyi Zhang; Huaijin Ran; Xunzhu Tang']:
 if x not in info: findings.append('pdf info '+x)
required_patterns={
 'HAOYI ZHANG':r'HAOYI\s+ZHANG',
 'HUAJIN RAN':r'HUA?IJIN\s+RAN',
 'XUNZHU TANG':r'XUNZHU\s+TANG',
 'Corresponding author: Huaijin Ran':r'Corresponding\s+author:\s+Hua?ijin\s+Ran'
}
for label,pattern in required_patterns.items():
 if not re.search(pattern,text,re.I): findings.append('missing pdf field '+label)
for x in ['YI YANG','MD MARUF HASAN','Anonymous Submission','Vol. 1, No. 1','Publication date:']:
 if x.lower() in text.lower(): findings.append('forbidden pdf field '+x)
fonts=run(['pdffonts',str(PDF)]).stdout.splitlines()[2:]
if not fonts or any(not re.search(r'\s+yes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$',l) for l in fonts if l.strip()): findings.append('font embedding')
auth=json.loads((PAPER/'author-metadata.json').read_text())
if len(auth.get('slots',[]))!=6 or [s['status'] for s in auth['slots']]!=['assigned']*3+['unassigned']*3: findings.append('author slots')
if auth.get('corresponding_author_position')!=2: findings.append('corresponding author')
figtex=sorted((PAPER/'figures').glob('figure-*.tex')); figpdf=sorted((PAPER/'figures').glob('figure-*.pdf'))
if len(figtex)!=6 or len(figpdf)!=6 or any('includegraphics' in p.read_text() for p in figtex): findings.append('figures')
if any(p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'} for p in PAPER.rglob('*')): findings.append('paper bitmap')
bib=(PAPER/'references.bib').read_text(); entries=re.findall(r'(?im)^@(article|inproceedings|incollection)\s*\{',bib); dois=re.findall(r'(?im)^\s*doi\s*=\s*\{([^}]+)\}',bib)
if len(entries)!=75 or len(dois)!=75 or len(set(d.lower() for d in dois))!=75: findings.append('bibliography')
refs=csvrows(ART/'reference/reference-audit.csv'); prov=csvrows(ART/'reference/reference-provenance.csv'); occ=csvrows(ART/'reference/citation-occurrence-audit.csv'); sup=csvrows(ART/'reference/citation-support.csv')
if (len(refs),len(prov),len(occ),len(sup))!=(75,75,85,85): findings.append('reference ledgers')
if any(r.get('verification_status')!='PASS_ONE_DIRECT_CITATION_FOR_ONE_NEARBY_CLAIM' for r in sup): findings.append('citation support')
if any(r.get('verification_status')!='VERIFIED_DOI_METADATA_SCHOLARLY_STATUS_AND_PROJECT_RELEVANCE' for r in prov): findings.append('provenance')
for f in ['page_fit_audit.json','citation_shape_audit.json']:
 if not (PAPER/f).is_file(): findings.append('missing '+f)
for f in ['visual-audit.json','figure-source-audit.json','doi-link-audit.json','manuscript-surface-audit.json','renderer-parity.json']:
 if not (ART/'audit'/f).is_file(): findings.append('missing audit '+f)

pagefit=json.loads((PAPER/'page_fit_audit.json').read_text())
if pagefit.get('total_pages')!=48 or not pagefit.get('within_one_ordinary_line'): findings.append('page fit')
visual=json.loads((ART/'audit/visual-audit.json').read_text())
if not str(visual.get('verdict','')).startswith('PASS'): findings.append('visual audit')
figaudit=json.loads((ART/'audit/figure-source-audit.json').read_text())
if not all(figaudit.get(k) for k in ['all_six_present','all_recompiled','all_warning_free','all_native','all_fonts_embedded']): findings.append('figure source audit')
doi_audit=json.loads((ART/'audit/doi-link-audit.json').read_text())
if not doi_audit.get('all_match') or doi_audit.get('pdf_sha256')!=sha(PDF): findings.append('DOI link audit')
surface=json.loads((ART/'audit/manuscript-surface-audit.json').read_text())
if surface.get('verdict')!='PASS': findings.append('public surface audit')
coq=(ART/'formal/coq/TideMarkCore.v').read_text()
for forbidden in ['Admitted.','Axiom ','Parameter ','Abort.']:
 if forbidden in coq: findings.append('formal source contains '+forbidden.strip())
summary=json.loads((ART/'data/derived/evaluation-summary.json').read_text()); expected={'programs':400,'bindings':13464,'selected':5782,'header_bits':1321,'payload_bits':4461,'full_executions':3200,'local_carrier_cases':809,'certificate_mutations':2000,'proof_mutations':3000,'interval_instances':65536,'frame_cases':12309,'derivations':800}
for k,v in expected.items():
 if summary.get(k)!=v: findings.append(f'evaluation {k}')
for k in ['accepted_mutations','accepted_proof_mutations','selector_differences','frame_failures','reference_selection_differences','reference_target_differences','reference_acceptance_differences','reference_evaluator_differences','full_semantic_differences','local_carrier_differences','derivation_failures','derivation_producer_differences']:
 if summary.get(k)!=0: findings.append('nonzero '+k)
ext=json.loads((ART/'data/derived/llvm-projection.json').read_text())
if ext.get('attempts')!=396 or ext.get('snapshot_source_files')!=132: findings.append('external denominator')
for stage,bits in [('O0',40),('O1',90),('O2',99)]:
 if ext['stages'][stage]['successful_modules']!=78 or ext['stages'][stage]['payload_bits']!=bits: findings.append('external '+stage)
# snapshot digests
snap=ART/'external/go-source-snapshot'; rows=csvrows(snap/'FILES.csv'); actual=sorted(p.relative_to(snap/'src').as_posix() for p in (snap/'src').rglob('*') if p.is_file())
if sorted(r['path'] for r in rows)!=actual: findings.append('snapshot file set')
for r in rows:
 p=snap/'src'/r['path']
 if len(p.read_bytes())!=int(r['bytes']) or sha(p)!=r['sha256']: findings.append('snapshot digest '+r['path']); break
# hygiene
for p in ROOT.rglob('*'):
 if p.is_dir() and p.name in {'__pycache__','.git','.pytest_cache'}: findings.append('cache '+str(p.relative_to(ROOT)))
 if p.is_file() and p.suffix.lower() in {'.pyc','.pyo','.aux','.out','.toc','.fls','.fdb_latexmk','.synctex.gz','.blg','.bbl'}: findings.append('debris '+str(p.relative_to(ROOT)))
result={'schema':'submission-verification','all_passed':not findings,'findings':findings,'pdf_sha256':sha(PDF),'pages':48,'assigned_authors':3,'reserved_author_slots':3,'unit_tests_expected':80,'reference_entries':75,'citation_occurrences':85,'native_figures':6}
print(json.dumps(result,indent=2,sort_keys=True)); sys.exit(0 if not findings else 1)
