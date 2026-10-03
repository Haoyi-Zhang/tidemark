"""Run one verification component, persisting its actual exit and transcript."""
from pathlib import Path
import subprocess,sys,time,hashlib,json,os
A=Path(__file__).resolve().parents[1];R=A.parent;L=A/'audit/current';L.mkdir(exist_ok=True)
commands={'tests':['-m','unittest','discover','-s','tests','-v'],'boundaries':['scripts/run_static_risk_regressions.py'],'evaluation':['scripts/run_evaluation.py'],'finite':['formal/check_finite_algebra_mode4.py'],'llvm':['scripts/run_external_llvm.py']}
name=sys.argv[1];cmd=[sys.executable,*commands[name]];t=time.perf_counter()
e=dict(os.environ,PYTHONPATH=str(A/'src'),PYTHONDONTWRITEBYTECODE='1')
p=subprocess.run(cmd,cwd=A,env=e,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
s=p.stdout.replace(str(R),'.');(L/(name+'.log')).write_text(s)
r={'component':name,'cwd':'artifact' if (R/'paper').is_dir() else '.','command':['python3',*commands[name]],'exit_code':p.returncode,'wall_seconds':time.perf_counter()-t,'log':f'artifact/audit/current/{name}.log' if (R/'paper').is_dir() else f'audit/current/{name}.log','log_sha256':hashlib.sha256(s.encode()).hexdigest()}
(L/(name+'-run.json')).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r));print(s[-500:]);sys.exit(p.returncode)
