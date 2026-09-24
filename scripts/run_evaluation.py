#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from tidemark.evaluation import run
out=run(); path=ROOT/'data'/'derived'/'evaluation-summary.json'; path.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print(json.dumps({k:v for k,v in out.items() if k!='family_rows'},indent=2,sort_keys=True)); print(path.relative_to(ROOT).as_posix())
