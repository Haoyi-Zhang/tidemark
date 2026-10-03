#!/usr/bin/env python3
"""Run actual components; optional --rerun refreshes CPU measurements first.
Default checks saved raw/derived evidence, tests, and rebuilds the manuscript.
No unavailable proof assistant is represented as a successful component.
"""
from pathlib import Path
import argparse,os,json,subprocess,sys,time,hashlib,shutil
A=Path(__file__).resolve().parents[1];P=A.parent/'paper';R=A.parent if P.is_dir() else A;O=A/'audit/current'
O.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--rerun',action='store_true');parser.add_argument('--include-paper',action='store_true',help='Require the sibling paper tree and run manuscript checks.');args=parser.parse_args()
if args.include_paper and not P.is_dir():
 raise SystemExit('Full-project input required: the standalone artifact has no sibling paper tree. Omit --include-paper to run code/evidence checks.')
env=dict(os.environ,PYTHONPATH=str(A/'src'),PYTHONDONTWRITEBYTECODE='1');rows=[]
components=[('unit-tests',[sys.executable,'-m','unittest','discover','-s','tests','-v'],A),('static-risk',[sys.executable,'scripts/run_static_risk_regressions.py'],A)]
if args.rerun:
 components += [('evaluation',[sys.executable,'scripts/run_evaluation.py'],A),('finite-algebra',[sys.executable,'formal/check_finite_algebra_mode4.py'],A),('external-llvm',[sys.executable,'scripts/run_external_llvm.py'],A)]
components += [('raw-derived-evidence',[sys.executable,'scripts/verify_evidence.py'],A)]
paper_components=[('paper-build',['bash','build.sh'],P),('reference-consistency',[sys.executable,'scripts/audit_references.py'],A),('pdf-source-audit',[sys.executable,'scripts/audit_final_pdf.py'],A)]
if P.is_dir():components += paper_components
for name,cmd,cwd in components:
 start=time.perf_counter();cp=subprocess.run(cmd,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 output=cp.stdout.replace(str(R),'.');log=O/(name+'.log');log.write_text(output)
 rows.append({'component':name,'cwd':cwd.relative_to(R).as_posix(),'command':['python3' if c==sys.executable else c for c in cmd],'exit_code':cp.returncode,'wall_seconds':time.perf_counter()-start,'log':str(log.relative_to(R)),'log_sha256':hashlib.sha256(output.encode()).hexdigest()})
 print(name,cp.returncode,flush=True)
 if cp.returncode:break
pdfaudit=json.loads((O/'pdf-audit.json').read_text()) if (O/'pdf-audit.json').exists() else None
result={'schema':'tidemark-current-verification-matrix-2','all_executed_components_passed':len(rows)==len(components) and all(r['exit_code']==0 for r in rows),'components':rows,'measurements_refreshed_in_this_invocation':args.rerun,'paper_checks_available':P.is_dir(),'paper_components_not_executed':[] if P.is_dir() else [name for name,_,_ in paper_components],'actual_pdf_pages':pdfaudit['pages'] if pdfaudit and P.is_dir() else None,'earlier_exact_48_page_goal_met':bool(pdfaudit and P.is_dir() and pdfaudit['pages']==48),'not_executed':[{'tool':'coqc','available':bool(shutil.which('coqc')),'effect':'No current Coq kernel recheck is claimed.'},{'tool':'z3','available':bool(shutil.which('z3')),'effect':'The finite algebra suite is Python enumeration, not an SMT solver run.'}],'not_claimed':['independent peer review','natural-program capacity estimation','production LLVM validation','post-transformation persistence','security or ownership guarantee']}
(A/'data/derived/verification-matrix-current.json').write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if result['all_executed_components_passed'] else 1)
