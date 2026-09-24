"""Separately written raw-JSON reference checker.

This module deliberately does not import tidemark.core.  It reimplements parsing,
carrier discovery, interval selection, framing, replay, and extraction over raw
JSON trees so agreement exercises a different representation.
"""
from __future__ import annotations
import hashlib, json
from typing import Any

SCHEMA="tidemark-certificate-3"; MODE="tidemark-mode-3"; CHECKER="tidemark-checker-3"

class RefError(ValueError): pass

def canon(x:Any)->bytes: return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def sha(x:bytes)->str: return hashlib.sha256(x).hexdigest()

def parse(data:bytes)->Any:
    try: x=json.loads(data.decode())
    except Exception as e: raise RefError("json") from e
    if canon(x)!=data: raise RefError("noncanonical")
    return x

def fv(e:Any)->set[str]:
    t=e[0]
    if t=="var": return {e[1]}
    if t in {"int","bool","get"}: return set()
    if t=="bin": return fv(e[2])|fv(e[3])
    if t in {"not","emit"}: return fv(e[1])
    if t=="put": return fv(e[2])
    if t=="if": return fv(e[1])|fv(e[2])|fv(e[3])
    raise RefError("expr")

def infer(e:Any, env:dict[str,str], regs:dict[str,str])->tuple[str,tuple[frozenset[str],frozenset[str],bool]]:
    t=e[0]; z=(frozenset(),frozenset(),False)
    if t=="var":
        if len(e)!=2 or not isinstance(e[1],str) or e[1] not in env: raise RefError("var")
        return env[e[1]],z
    if t=="int":
        if len(e)!=2 or type(e[1]) is not int: raise RefError("int")
        return "Int",z
    if t=="bool":
        if len(e)!=2 or type(e[1]) is not bool: raise RefError("bool")
        return "Bool",z
    if t=="get": return regs[e[1]],(frozenset([e[1]]),frozenset(),False)
    if t=="not":
        a,ef=infer(e[1],env,regs)
        if a!="Bool": raise RefError("type")
        return "Bool",ef
    if t=="bin":
        op=e[1]; a,ea=infer(e[2],env,regs); b,eb=infer(e[3],env,regs)
        ef=(ea[0]|eb[0],ea[1]|eb[1],ea[2] or eb[2])
        if op in {"add","sub","mul","lt"}:
            if a!="Int" or b!="Int": raise RefError("type")
            return ("Bool" if op=="lt" else "Int"),ef
        if op=="eq" and a==b and a!="Unit": return "Bool",ef
        raise RefError("type")
    if t=="put":
        a,ef=infer(e[2],env,regs)
        if regs[e[1]]!=a: raise RefError("type")
        return "Unit",(ef[0],ef[1]|{e[1]},ef[2])
    if t=="emit":
        a,ef=infer(e[1],env,regs)
        if a=="Unit": raise RefError("type")
        return "Unit",(ef[0],ef[1],True)
    if t=="if":
        c,ec=infer(e[1],env,regs); a,ea=infer(e[2],env,regs); b,eb=infer(e[3],env,regs)
        if c!="Bool" or a!=b: raise RefError("type")
        return a,(ec[0]|ea[0]|eb[0],ec[1]|ea[1]|eb[1],ec[2] or ea[2] or eb[2])
    raise RefError("expr")

def analyze(p:Any):
    if not isinstance(p,dict) or set(p)!={"schema","params","regions","commands","result"} or p["schema"]!="tidemark-ir-3": raise RefError("program")
    env={n:t for n,t in p["params"]}; regs={n:t for n,t in p["regions"]}; before=[]; effects=[]
    for c in p["commands"]:
        if c[0]!="let" or c[1] in env: raise RefError("command")
        before.append(dict(env)); typ,ef=infer(c[2],env,regs); env[c[1]]=typ; effects.append(ef)
    if p["result"] not in env: raise RefError("result")
    return before,effects

def commute(a,b):
    ar,aw,ae=a; br,bw,be=b
    return not (ae and be) and not (aw&(br|bw) or bw&(ar|aw))

def candidates(p:Any):
    before,effects=analyze(p); regs={n:t for n,t in p["regions"]}; out=[]; cs=p["commands"]
    for i,c in enumerate(cs):
        e=c[2]; identity=None
        base=None; typ=None
        if e[0]=="var": base=e; typ,_=infer(base,before[i],regs)
        elif e[0]=="bin" and ((e[1]=="add" and e[3]==["int",0]) or (e[1]=="eq" and e[3]==["bool",True])):
            base=e[2]; typ,_=infer(base,before[i],regs)
        if base is not None and typ in {"Int","Bool"}:
            c0=["let",c[1],base]; c1=["let",c[1],["bin","add",base,["int",0]] if typ=="Int" else ["bin","eq",base,["bool",True]]]
            identity=("identity",i,i,[c0],[c1]); out.append(identity)
        if e[0]=="bin" and e[1] in {"add","mul","eq"} and identity is None:
            _,le=infer(e[2],before[i],regs); _,re=infer(e[3],before[i],regs)
            if le==(frozenset(),frozenset(),False) and re==(frozenset(),frozenset(),False) and canon(e[2])!=canon(e[3]):
                lo,hi=(e[2],e[3]) if canon(e[2])<canon(e[3]) else (e[3],e[2])
                out.append(("operand",i,i,[["let",c[1],["bin",e[1],lo,hi]]],[["let",c[1],["bin",e[1],hi,lo]]]))
    for i in range(len(cs)-1):
        a,b=cs[i],cs[i+1]
        if b[1] in fv(a[2]) or a[1] in fv(b[2]) or not commute(effects[i],effects[i+1]): continue
        if canon(a)==canon(b): continue
        lo=(a,b) if canon(a)<canon(b) else (b,a); hi=(b,a) if canon(a)<canon(b) else (a,b)
        out.append(("adjacent",i,i+1,list(lo),list(hi)))
    return sorted(out,key=lambda s:(s[1],s[2],s[0]))

def select(xs):
    rank={"operand":0,"identity":1,"adjacent":2}; out=[]; end=-1
    for s in sorted(xs,key=lambda s:(s[2],s[1],rank[s[0]])):
        if s[1]>end: out.append(s); end=s[2]
    return sorted(out,key=lambda s:(s[1],s[2],s[0]))

def hw(n):
    if type(n) is not int or n<0: raise RefError("site count")
    return n.bit_length()
def frame(payload,n):
    if any(type(bit) is not int or bit not in (0,1) for bit in payload): raise RefError("payload")
    h=hw(n); c=n-h
    if len(payload)>c: raise RefError("capacity")
    if n==0: return []
    return [((len(payload)>>k)&1) for k in reversed(range(h))]+payload+[0]*(n-h-len(payload))
def unframe(bits):
    if any(type(bit) is not int or bit not in (0,1) for bit in bits): raise RefError("frame bits")
    n=len(bits); h=hw(n)
    if not n: return []
    L=0
    for b in bits[:h]: L=2*L+b
    if L>n-h or any(bits[h+L:]): raise RefError("frame")
    return bits[h:h+L]
def replay(p,sites,bits):
    q=json.loads(json.dumps(p)); cs=q["commands"]
    for s,b in sorted(zip(sites,bits),key=lambda x:x[0][1],reverse=True): cs[s[1]:s[2]+1]=s[3+b]
    analyze(q); return q
def extract(p,q):
    ss=select(candidates(p)); bits=[]
    for s in ss:
        frag=q["commands"][s[1]:s[2]+1]; m0=frag==s[3]; m1=frag==s[4]
        if m0==m1: raise RefError("orientation")
        bits.append(0 if m0 else 1)
    return unframe(bits)
def check(source:bytes,target:bytes,certificate:bytes):
    c=parse(certificate)
    if set(c)!={"schema","checker","mode","source_sha256","target_sha256","payload"}: raise RefError("cert")
    if c["schema"]!=SCHEMA or c["mode"]!=MODE or c["checker"]!=CHECKER: raise RefError("version")
    if sha(source)!=c["source_sha256"] or sha(target)!=c["target_sha256"]: raise RefError("digest")
    if not isinstance(c["payload"],str) or any(ch not in "01" for ch in c["payload"]): raise RefError("payload")
    p=parse(source); q=parse(target); payload=[int(x) for x in c["payload"]]
    ss=select(candidates(p)); expected=replay(p,ss,frame(payload,len(ss)))
    if canon(expected)!=target: raise RefError("target")
    got=extract(p,q)
    if got!=payload: raise RefError("extract")
    return tuple(got)

def _eval_expr(e,env,store,trace):
    t=e[0]
    if t=="var": return env[e[1]]
    if t in {"int","bool"}: return e[1]
    if t=="get": return store[e[1]]
    if t=="not": return not _eval_expr(e[1],env,store,trace)
    if t=="bin":
        a=_eval_expr(e[2],env,store,trace); b=_eval_expr(e[3],env,store,trace); op=e[1]
        return {"add":lambda:a+b,"sub":lambda:a-b,"mul":lambda:a*b,"eq":lambda:a==b,"lt":lambda:a<b}[op]()
    if t=="put": store[e[1]]=_eval_expr(e[2],env,store,trace); return None
    if t=="emit": trace.append(_eval_expr(e[1],env,store,trace)); return None
    if t=="if": return _eval_expr(e[2] if _eval_expr(e[1],env,store,trace) else e[3],env,store,trace)
    raise RefError("eval")

def _runtime_type_ok(value,typ):
    return ((typ=="Int" and type(value) is int) or
            (typ=="Bool" and type(value) is bool) or
            (typ=="Unit" and value is None))

def evaluate(program,params,initial_store):
    before,_=analyze(program); env=dict(params); store=dict(initial_store); trace=[]
    param_types={name:typ for name,typ in program["params"]}; region_types={name:typ for name,typ in program["regions"]}
    if set(env)!=set(param_types) or set(store)!=set(region_types): raise RefError("runtime domain")
    if any(not _runtime_type_ok(env[name],typ) for name,typ in param_types.items()): raise RefError("parameter type")
    if any(not _runtime_type_ok(store[name],typ) for name,typ in region_types.items()): raise RefError("store type")
    for index,c in enumerate(program["commands"]):
        typ,_=infer(c[2],before[index],region_types); value=_eval_expr(c[2],env,store,trace)
        if not _runtime_type_ok(value,typ): raise RefError("command result type")
        env[c[1]]=value
    if any(not _runtime_type_ok(store[name],typ) for name,typ in region_types.items()): raise RefError("final store type")
    return env[program["result"]],store,tuple(trace)
