#!/usr/bin/env python3
"""Audit actual PDF structure, fonts, source bindings, and generated assets.

Geometry and warning checks do not replace the separately recorded visual review.
No page count is invented or enforced by selecting extra paragraphs.
"""
from pathlib import Path
import json,re,subprocess,hashlib
import fitz
R=Path(__file__).resolve().parents[2];P=R/'paper';A=R/'Artifacts';O=A/'audit/current'
O.mkdir(parents=True,exist_ok=True);issues=[]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
required=[P/'main.tex',P/'main.pdf',P/'data-macros.tex',P/'data-macros.json',P/'references.bib',P/'figures/preamble.tex',P/'build.sh',P/'Makefile']
for n in range(1,7):required.extend([P/f'figures/figure-{n:02}.tex',P/f'figures/figure-{n:02}.pdf'])
for f in required:
 if not f.is_file():issues.append('missing '+str(f.relative_to(R)))
if issues:raise SystemExit(json.dumps(issues))
D=fitz.open(P/'main.pdf');text='\n'.join(pg.get_text() for pg in D);captions={}
for i,pg in enumerate(D,1):
 t=' '.join(pg.get_text().split())
 for n in range(1,7):
  if re.search(r'(?:Figure|Fig\.) '+str(n)+r'\.',t):captions[str(n)]=i
font_log=subprocess.check_output(['pdffonts',str(P/'main.pdf')],text=True)
font_rows=[]
for line in font_log.splitlines()[2:]:
 m=re.search(r'\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$',line)
 if m:font_rows.append({'font':line.split()[0],'embedded':m[1]=='yes','unicode':m[3]=='yes'})
if not font_rows or any(not r['embedded'] for r in font_rows):issues.append('font embedding')
log=(P/'main.log').read_text(errors='replace');blg=(P/'main.blg').read_text(errors='replace')
errors=[line for line in log.splitlines() if re.search(r'Overfull|Undefined control sequence|Citation .* undefined|Reference .* undefined|^! ',line)]
if errors:issues.append('LaTeX errors or overfull boxes')
if 'Warning--' in blg:issues.append('BibTeX warning')
if len(captions)!=6:issues.append('not all six captions located')
source=(P/'main.tex').read_text();auth=re.findall(r'\\author\{([^}]+)\}',source)
if auth!=['Haoyi Zhang','Yi Yang','Md Maruf Hasan']:issues.append('author list changed')
for n in range(1,7):
 fd=fitz.open(P/f'figures/figure-{n:02}.pdf')
 if len(fd)!=1:issues.append('standalone figure page count')
record=json.loads((P/'data-macros.json').read_text())
for rel,digest in record['input_sha256'].items():
 if sha(R/rel)!=digest:issues.append('data source changed after export: '+rel)
last=[w for w in D[-1].get_text('words') if w[0]>=38 and 45<w[1]<680 and not re.fullmatch(r'\d+',w[4])]
y=max(w[3] for w in last)
result={'schema':'tidemark-current-pdf-audit-2','all_mechanical_checks_passed':not issues,'issues':issues,'pages':len(D),'previous_48_page_goal_met':len(D)==48,'figure_pages':captions,'font_objects':font_rows,'pdf_sha256':sha(P/'main.pdf'),'page_size_points':list(D[0].rect),'last_real_text_y1':y,'overfull_or_undefined_lines':errors,'bibtex_warning_count':blg.count('Warning--'),'author_order':auth,'source_kind':'editable evidence-grounded reconstruction already present in the supplied source package','review_mode':'acmsmall,screen,review,nonacm; nonacm suppresses unassigned publication metadata without changing journal geometry','scope':'Mechanical check of this source/PDF pair; not a journal-policy clearance, peer review, or universal scientific correctness certificate.'}
(O/'pdf-audit.json').write_text(json.dumps(result,indent=2)+'\n');(O/'fonts.txt').write_text(font_log)
(O/'compile-record.txt').write_text(log+'\n---BIBTEX---\n'+blg)
print(json.dumps({k:v for k,v in result.items() if k!='font_objects'},indent=2));raise SystemExit(0 if not issues else 1)
