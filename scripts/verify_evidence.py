#!/usr/bin/env python3
"""Cross-check current aggregates against the saved raw evidence, without editing it."""
from pathlib import Path
import json,csv,hashlib,collections,sys,math
A=Path(__file__).resolve().parents[1];sys.path.insert(0,str(A/'src'))
from tidemark.core import Program,serialize_program,check_certificate
D=A/'data/derived';RAW=A/'data/raw/mode4'
S=json.loads((D/'evaluation-summary-mode4.json').read_text());issues=[];checks={}
def check(name,actual,expected):
 checks[name]={'actual':actual,'expected':expected,'passed':actual==expected}
 if actual!=expected:issues.append(name)
def csv_rows(name):
 with (RAW/name).open(newline='') as f:yield from csv.DictReader(f)
def json_rows(name):
 with (RAW/name).open() as f:
  for line in f:yield json.loads(line)
rows=list(csv_rows('program-results.csv'))
check('program count',len(rows),S['programs'])
for key in ['bindings','selected','payload_bits','header_bits','source_bytes','target_bytes','certificate_bytes','descriptor_rich_bytes','operand','identity','adjacent']:
 check('aggregate '+key,sum(int(r[key]) for r in rows),S[key])
family=collections.defaultdict(lambda:collections.Counter())
for r in rows:
 for key in ['bindings','selected','payload_bits','header_bits','operand','identity','adjacent']:family[r['family']][key]+=int(r[key])
 family[r['family']]['programs']+=1
for name,counts in family.items():
 for key,value in counts.items():check('family '+name+' '+key,value,S['family_summary'][name][key])
h=hashlib.sha256();program_count=0;source_keys=[]
for r in json_rows('programs.jsonl'):
 obj=r.get('program',r.get('source'))
 if obj is None:raise RuntimeError('unrecognized raw program record')
 data=serialize_program(Program.from_obj(obj));h.update(len(data).to_bytes(8,'big'));h.update(data);source_keys.append(hashlib.sha256(data).hexdigest());program_count+=1
check('corpus size',program_count,S['programs']);check('corpus hash',h.hexdigest(),S['corpus_digest'])
for name,key in [('full-executions.csv','full_executions'),('local-carrier-checks.csv','local_carrier_cases'),('interval-audit.csv','interval_instances'),('adjacent-pairs.jsonl','adjacent_pairs'),('derivations.jsonl','derivations')]:
 n=sum(1 for _ in (json_rows(name) if name.endswith('.jsonl') else csv_rows(name)));check('raw '+name,n,S[key])
mutants=list(json_rows('certificate-mutations.jsonl'))
check('certificate mutations',len(mutants),S['certificate_mutations'])
# Record keys are inspected rather than treating process exit as a scientific verdict.
accepted=0;refaccepted=0
for r in mutants:
 for prefix in ['production','reference']:
  key=prefix+'_accepted';reason_key=prefix+'_first_failure_reason'
  if key not in r or type(r[key]) is not bool:raise RuntimeError('missing/non-Boolean mutation verdict: '+key)
  if r[key] is False and not isinstance(r.get(reason_key),str):raise RuntimeError('missing first rejection reason: '+reason_key)
  if r[key] is False and not r[reason_key].strip():raise RuntimeError('empty first rejection reason: '+reason_key)
 accepted+=r['production_accepted'];refaccepted+=r['reference_accepted']
check('mutation production acceptance',accepted,0);check('mutation reference acceptance',refaccepted,0)
# The trace-verifier schema is flat and deliberately distinct from certificate verdicts.
dmut=list(json_rows('derivation-mutations.jsonl'))
applicable=no_steps=accepted_records=0
for r in dmut:
 for key in ['applicable','accepted']:
  if type(r.get(key)) is not bool:raise RuntimeError('missing structural mutation flag: '+key)
 if not isinstance(r.get('first_failure_reason'),str) or not r['first_failure_reason']:raise RuntimeError('missing structural first-failure reason')
 applicable+=r['applicable'];no_steps+=not r['applicable'];accepted_records+=r['accepted']
 if not r['applicable'] and r['first_failure_reason']!='no_steps':raise RuntimeError('nonapplicable mutation has no explicit no_steps reason')
check('structural applicable mutation rows',applicable,S['proof_mutations'])
check('structural inapplicable mutation rows',no_steps,S['derivation_mutations_not_applicable'])
check('structural accepted mutation rows',accepted_records,S['accepted_proof_mutations'])
frame_count=valid=0
for r in csv_rows('frame-audit.csv'):
 n=int(r.get('site_count',r.get('sites',r.get('n',-1))));bits=r.get('bits',r.get('frame_bits',''))
 if n<0:raise RuntimeError('unknown frame schema '+repr(r))
 width=n.bit_length();length=int(bits[:width],2) if width else 0
 expected=length<=n-width and not any(x!='0' for x in bits[width+length:])
 actual=str(r.get('accepted',r.get('valid',r.get('valid_frame','')))).lower() in {'true','1'}
 if expected!=actual:issues.append('frame row mismatch')
 frame_count+=1;valid+=actual
check('frame vector count',frame_count,S['frame_vectors']);check('valid frame count',valid,S['legal_frames'])
# Match quantile recomputation to the explicit R-7 rule.
def q7(xs,p):
 xs=sorted(xs);u=(len(xs)-1)*p;a=int(u);return xs[a] if a==len(xs)-1 else xs[a]+(u-a)*(xs[a+1]-xs[a])
for phase,stat in S['timing_summary'].items():
 xs=[float(r[phase]) for r in rows]
 for key,p in [('median',.5),('p75',.75),('p95',.95)]:
  got=q7(xs,p)
  if not math.isclose(got,stat[key],rel_tol=1e-10,abs_tol=1e-10):issues.append('quantile '+phase+' '+key)
checks['quantiles_recomputed']={'passed':not any(i.startswith('quantile') for i in issues)}
zero_keys=[k for k in S if k.endswith('_differences') or k.endswith('_failures')]+['accepted_mutations','reference_accepted_mutations','accepted_proof_mutations']
for key in zero_keys:check('zero '+key,S[key],0)
finite=json.loads((D/'finite-algebra-mode4.json').read_text());check('finite cases',finite['total_cases'],sum(r['cases'] for r in finite['obligations']))
check('countermodels',finite['countermodels_found'],finite['countermodels_expected'])
llvm=json.loads((D/'llvm-projection-mode4.json').read_text())
llvmraw=A/llvm['raw_rows'] if not str(llvm['raw_rows']).startswith('artifact/') else A.parent/llvm['raw_rows']
# The returned path is artifact-relative.
if not llvmraw.exists():
 options=list((A/'data/raw').rglob('*llvm*.csv'))
 if len(options)!=1:raise RuntimeError('cannot uniquely resolve LLVM rows')
 llvmraw=options[0]
with llvmraw.open(newline='') as f:lrows=list(csv.DictReader(f))
check('llvm attempts',len(lrows),llvm['attempts'])
for stage,data in llvm['stages'].items():
 selected=[r for r in lrows if r['stage']==stage]
 check(stage+' success',sum(int(r['returncode'])==0 for r in selected),data['successful_modules'])
 for field in ['instructions','payload_bits','selected_sites','operand_only_payload_bits','identity_only_payload_bits','adjacent_only_payload_bits']:
  check(stage+' '+field,sum(int(r[field]) for r in selected),data[field])
result={'schema':'tidemark-raw-derived-review-1','all_checks_passed':not issues,'issues':issues,'checks':checks,'input_sha256':{p.relative_to(A.parent).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [D/'evaluation-summary-mode4.json',D/'finite-algebra-mode4.json',D/'llvm-projection-mode4.json']},'boundary':'These are current-data consistency checks, not a proof-assistant refinement or an external scientific validation.'}
(A/'audit/current/evidence-consistency.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':not issues,'check_count':len(checks),'issues':issues},indent=2));raise SystemExit(0 if not issues else 1)
