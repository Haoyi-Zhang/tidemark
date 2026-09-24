#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; ART=ROOT/'artifact'; LOG=ART/'audit/command-logs'; LOG.mkdir(parents=True,exist_ok=True)
env=dict(os.environ); env['PYTHONPATH']=str(ART/'src'); env['PYTHONDONTWRITEBYTECODE']='1'; env['TERM']='xterm'
commands=[('unit-tests',[sys.executable,'-m','unittest','discover','-s','artifact/tests','-v']),('evaluation',[sys.executable,'artifact/scripts/run_evaluation.py']),('external-llvm',[sys.executable,'artifact/scripts/run_external_llvm.py']),('static-verification',[sys.executable,'artifact/scripts/verify_submission.py'])]
rows=[]
for name,cmd in commands:
 t=time.perf_counter(); p=subprocess.run(cmd,cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT); out=p.stdout.replace(str(ROOT),'.'); (LOG/f'{name}.log').write_text(out); print(out)
 rows.append({'component':name,'returncode':p.returncode,'elapsed_seconds':round(time.perf_counter()-t,6),'output_sha256':hashlib.sha256(out.encode()).hexdigest(),'log':(LOG/f'{name}.log').relative_to(ROOT).as_posix(),'status':'PASS' if p.returncode==0 else 'FAIL'})
 if p.returncode: break
result={'schema':'verification-matrix','all_passed':all(r['returncode']==0 for r in rows),'components':rows,'environment':{'python':sys.version.split()[0],'coqc_available':__import__('shutil').which('coqc') is not None,'z3_available':__import__('shutil').which('z3') is not None}}
(ART/'data/derived/verification-matrix.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); sys.exit(0 if result['all_passed'] else 1)
