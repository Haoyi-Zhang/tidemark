#!/usr/bin/env python3
"""Bind the reviewed bibliography and every current citation to exact source bytes.

This is a local consistency check, not an online DOI resolver. External review
sources and its limited scope are recorded separately in reference-review.md.
"""
from pathlib import Path
import re,json,csv,hashlib
from bibliography_tools import parse_bib
A=Path(__file__).resolve().parents[1];R=A.parent;P=R/'paper';O=A/'reference'
if not P.is_dir():raise SystemExit('Full-project input required: manuscript citation auditing needs the sibling paper tree.')
O.mkdir(exist_ok=True)
B=P/'references.bib';E=parse_bib(B.read_text());K={e['key']:e for e in E};rows=[];multi=[]
for p in [P/'main.tex',*sorted((P/'sections').glob('*.tex'))]:
 s=p.read_text()
 for m in re.finditer(r'\\cite(?:t|p)?\{([^}]+)\}',s):
  keys=[k.strip() for k in m[1].split(',')]
  if len(keys)>1:multi.append({'source':str(p.relative_to(R)),'line':s.count('\n',0,m.start())+1,'keys':keys})
  prefix=s[:m.start()];a=max(prefix.rfind('.  '),prefix.rfind('. '),prefix.rfind('\n\n'))
  claim=re.sub(r'\s+',' ',s[a+2:m.end()]).strip()
  for k in keys:
   e=K.get(k,{})
   rows.append({'occurrence':len(rows)+1,'source':p.relative_to(R).as_posix(),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'line':s.count('\n',0,m.start())+1,'key':k,'nearby_claim':claim,'paper_title':e.get('title',''),'doi':e.get('doi',''),'review_scope':'bounded nearby literature-positioning claim; see reference-review.md'})
used={r['key'] for r in rows};doi=[e.get('doi','').lower() for e in E]
undefined=sorted(used-set(K));uncited=sorted(set(K)-used)
summary={'schema':'tidemark-current-reference-consistency-1','bib_sha256':hashlib.sha256(B.read_bytes()).hexdigest(),'bibliography_entries':len(E),'minimum_requested':60,'meets_reference_floor':len(E)>=60,'unique_dois':len(set(doi)),'missing_dois':[e['key'] for e in E if not e.get('doi')],'undefined_citations':undefined,'uncited_entries':uncited,'citation_occurrences':len(rows),'unique_cited_keys':len(used),'multi_key_citations':multi,'online_checks_executed_by_this_script':False,'full_text_research_correctness_certified':False}
summary['all_local_checks_passed']=len(E)>=60 and len(E)==len(K)==len(set(doi)) and '' not in doi and not undefined and not uncited and not multi
with (O/'citation-support.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
fields=['key','title','author','year','journal','booktitle','volume','number','pages','articleno','numpages','doi','primary_locator','current_bib_sha256']
with (O/'bibliography-current.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for e in E:w.writerow({**{k:e.get(k,'') for k in fields},'primary_locator':'https://doi.org/'+e['doi'],'current_bib_sha256':summary['bib_sha256']})
# Key-to-rendered number is read from the actual BibTeX output, not inferred from rXX.
aux=(P/'main.aux').read_text() if (P/'main.aux').exists() else ''
number_map=dict(re.findall(r'\\bibcite\{([^}]+)\}\{\{(\d+)\}',aux))
(O/'rendered-key-number-map.json').write_text(json.dumps(number_map,indent=2)+'\n')
(O/'reference-consistency.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2));raise SystemExit(0 if summary['all_local_checks_passed'] else 1)
