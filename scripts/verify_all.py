#!/usr/bin/env python3
"""Run actual components; optional --rerun refreshes CPU measurements first.
Default checks saved raw/derived evidence, tests, and rebuilds the manuscript.
No unavailable proof assistant is represented as a successful component.
"""
from pathlib import Path
import argparse,os,json,subprocess,sys,time,hashlib,shutil
R=Path(__file__).resolve().parents[2];A=R/'Artifacts';P=R/'paper';O=A/'audit/current'
O.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--rerun',action='store_true');args=parser.parse_args()
env=dict(os.environ,PYTHONPATH=str(A/'src'),PYTHONDONTWRITEBYTECODE='1');rows=[]
components=[('unit-tests',[sys.executable,'-m','unittest','discover','-s','tests','-v'],A),('static-risk',[sys.executable,'scripts/run_static_risk_regressions.py'],A)]
if args.rerun:
 components += [('evaluation',[sys.executable,'scripts/run_evaluation.py'],A),('finite-algebra',[sys.executable,'formal/check_finite_algebra_mode4.py'],A),('external-llvm',[sys.executable,'scripts/run_external_llvm.py'],A)]
components += [('raw-derived-evidence',[sys.executable,'scripts/verify_evidence.py'],A),('paper-build',['bash','build.sh'],P),('reference-consistency',[sys.executable,'scripts/audit_references.py'],A),('pdf-source-audit',[sys.executable,'scripts/audit_final_pdf.py'],A)]
for name,cmd,cwd in components:
 start=time.perf_counter();cp=subprocess.run(cmd,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 output=cp.stdout.replace(str(R),'.');log=O/(name+'.log');log.write_text(output)
 rows.append({'component':name,'cwd':cwd.relative_to(R).as_posix(),'command':['python3' if c==sys.executable else c for c in cmd],'exit_code':cp.returncode,'wall_seconds':time.perf_counter()-start,'log':str(log.relative_to(R)),'log_sha256':hashlib.sha256(output.encode()).hexdigest()})
 print(name,cp.returncode,flush=True)
 if cp.returncode:break
pdfaudit=json.loads((O/'pdf-audit.json').read_text()) if (O/'pdf-audit.json').exists() else None
result={'schema':'tidemark-current-verification-matrix-2','all_executed_components_passed':len(rows)==len(components) and all(r['exit_code']==0 for r in rows),'components':rows,'measurements_refreshed_in_this_invocation':args.rerun,'actual_pdf_pages':pdfaudit['pages'] if pdfaudit else None,'earlier_exact_48_page_goal_met':bool(pdfaudit and pdfaudit['pages']==48),'not_executed':[{'tool':'coqc','available':bool(shutil.which('coqc')),'effect':'No current Coq kernel recheck is claimed.'},{'tool':'z3','available':bool(shutil.which('z3')),'effect':'The finite algebra suite is Python enumeration, not an SMT solver run.'}],'not_claimed':['independent peer review','natural-program capacity estimation','production LLVM validation','post-transformation persistence','security or ownership guarantee']}
(A/'data/derived/verification-matrix-current.json').write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if result['all_executed_components_passed'] else 1)
