"""Deterministic quota-constructed proof-stress corpus.

The family totals in :data:`FAMILIES` are design inputs, not measurements of a
natural program distribution.  ``build_specs`` allocates those requested
selected-site counts, user-bit totals, carrier-family contributions, and the
13,464-binding aggregate across 400 programs.  ``build_program`` is the current
public corpus constructor: it deterministically realizes one ``ProgramSpec``
under the mode-4 IR and is used by tests and evaluation.

Consequently, family-level capacity differences from this corpus are
construction checks and controlled stress cases.  They must not be interpreted
as independent evidence about capacity in naturally occurring programs.
"""
from __future__ import annotations
import hashlib, random
from dataclasses import dataclass
from typing import Iterable
from .core import Program, Command, Expr, Type, header_width

FAMILIES = {
    "pure-arithmetic": (1091, 880, 694, 272, 125),
    "dependence-heavy": (832, 641, 400, 211, 221),
    "region-state": (733, 551, 232, 201, 300),
    "ordered-trace": (904, 710, 430, 249, 225),
    "branches": (785, 598, 193, 217, 375),
    "mixed": (717, 539, 258, 63, 396),
    "random": (720, 542, 273, 77, 370),
    "state-conflict-control": (0, 0, 0, 0, 0),
    "subtraction-control": (0, 0, 0, 0, 0),
    "trace-order-control": (0, 0, 0, 0, 0),
}

@dataclass(frozen=True)
class ProgramSpec:
    family: str
    index: int
    operand: int
    identity: int
    adjacent: int
    filler: int
    capacity: int


def _capacity_vector(total:int, header_total:int)->list[int]:
    # Forty capacities with exact sum and exact sum ceil(log2(N+1)).
    # Search a compact class-count solution, then distribute the residual.
    for n4 in range(41):
      for n5 in range(41-n4):
        n6=40-n4-n5
        if 4*n4+5*n5+6*n6 != header_total: continue
        lows=[8]*n4+[16]*n5+[32]*n6; highs=[15]*n4+[31]*n5+[63]*n6
        if sum(lows)<=total<=sum(highs):
            vals=lows[:]; rem=total-sum(vals); i=0
            while rem:
                j=i%40
                if vals[j]<highs[j]: vals[j]+=1; rem-=1
                i+=1
            return vals
    raise RuntimeError((total,header_total))

def _allocate(total:int,caps:list[int],seed:str)->list[int]:
    rng=random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:16],16)); out=[0]*len(caps)
    slots=[i for i,c in enumerate(caps) for _ in range(c)]
    rng.shuffle(slots)
    for i in slots[:total]: out[i]+=1
    return out

def build_specs()->list[ProgramSpec]:
    """Allocate the fixed paper-era quotas across forty programs per family."""
    specs=[]; carrier_bindings=0
    for family,(selected,user,o,i,a) in FAMILIES.items():
        if selected:
            caps=_capacity_vector(selected,selected-user)
            os=_allocate(o,caps,f"{family}-o")
            rem=[c-x for c,x in zip(caps,os)]; ids=_allocate(i,rem,f"{family}-i")
            ad=[c-x-y for c,x,y in zip(caps,os,ids)]
            assert sum(ad)==a
        else: caps=os=ids=ad=[0]*40
        for idx in range(40):
            carrier_bindings += os[idx]+ids[idx]+3*ad[idx]
            specs.append(ProgramSpec(family,idx,os[idx],ids[idx],ad[idx],0,caps[idx]))
    # Add exactly enough noncarrier bindings to reach the paper's 13,464 total.
    need=13464-carrier_bindings
    base,extra=divmod(need,len(specs)); out=[]
    for k,s in enumerate(specs): out.append(ProgramSpec(s.family,s.index,s.operand,s.identity,s.adjacent,base+(k<extra),s.capacity))
    assert sum(s.operand+s.identity+3*s.adjacent+s.filler for s in out)==13464
    assert sum(s.capacity for s in out)==5782
    assert sum(header_width(s.capacity) for s in out)==1321
    return out

def build_program(spec:ProgramSpec)->Program:
    """Deterministically realize one current-schema program from ``spec``."""
    cmds=[]; current="arg"; serial=0
    def name(prefix):
        nonlocal serial; serial+=1; return f"{prefix}{spec.index:02d}_{serial:03d}"

    # Deliberately hostile zero-capacity controls.
    if spec.family=="state-conflict-control":
        for _ in range(max(1,spec.filler)):
            n=name("sw"); cmds.append(Command(n,Expr.put("r",Expr.var("arg"))))
        return Program((("arg",Type.INT),),( ("r",Type.INT), ),tuple(cmds),"arg")
    if spec.family=="trace-order-control":
        for _ in range(max(1,spec.filler)):
            n=name("te"); cmds.append(Command(n,Expr.emit(Expr.var("arg"))))
        return Program((("arg",Type.INT),),( ("r",Type.INT), ),tuple(cmds),"arg")
    if spec.family=="subtraction-control":
        for j in range(max(1,spec.filler)):
            n=name("zs"); cmds.append(Command(n,Expr.binary("sub",Expr.var(current),Expr.integer(j+1)))); current=n
        return Program((("arg",Type.INT),),( ("r",Type.INT), ),tuple(cmds),current)

    # Carrier blocks are shuffled, but each block consumes the previous result.
    # Hence the only dependency-free neighboring pair is the intended adjacent carrier.
    blocks=["operand"]*spec.operand+["identity"]*spec.identity+["adjacent"]*spec.adjacent
    rng=random.Random(int(hashlib.sha256(f"{spec.family}:{spec.index}".encode()).hexdigest()[:16],16)); rng.shuffle(blocks)
    for kind in blocks:
        if kind=="operand":
            n=name("o"); cmds.append(Command(n,Expr.binary("add",Expr.var(current),Expr.integer(serial+3)))); current=n
        elif kind=="identity":
            n=name("i"); expanded=((serial+spec.index)&1)==1
            base=Expr.var(current); cmds.append(Command(n,Expr.binary("add",base,Expr.integer(0)) if expanded else base)); current=n
        else:
            a=name("a"); b=name("b"); merge=name("m")
            cmds.append(Command(a,Expr.binary("sub",Expr.var(current),Expr.integer(serial+5))))
            cmds.append(Command(b,Expr.binary("sub",Expr.var(current),Expr.integer(serial+11))))
            cmds.append(Command(merge,Expr.binary("sub",Expr.var(a),Expr.var(b)))); current=merge

    # Reserve a small suffix for the state/trace families.  The suffix is placed
    # after all carrier blocks so it cannot create an accidental pure adjacent site.
    remaining=spec.filler
    suffix=[]
    if spec.family=="region-state" and remaining>=2:
        remaining-=2; suffix=["put","get"]
    elif spec.family=="ordered-trace" and remaining>=2:
        remaining-=2; suffix=["emit","emit"]
    elif spec.family=="mixed" and remaining>=4:
        remaining-=4; suffix=["put","get","emit","emit"]

    for j in range(remaining):
        n=name("f")
        if spec.family=="branches" and j%3==0:
            cmds.append(Command(n,Expr.choose(Expr.boolean(((j+spec.index)&1)==0),Expr.var(current),Expr.binary("sub",Expr.var(current),Expr.integer(j+1)))))
        else:
            cmds.append(Command(n,Expr.binary("sub",Expr.var(current),Expr.integer(serial+17))))
        current=n

    for kind in suffix:
        if kind=="put":
            n=name("rw"); cmds.append(Command(n,Expr.put("r",Expr.var(current))))
        elif kind=="get":
            n=name("rr"); cmds.append(Command(n,Expr.get("r"))); current=n
        else:
            n=name("tr"); cmds.append(Command(n,Expr.emit(Expr.var(current))))
    return Program((("arg",Type.INT),),( ("r",Type.INT), ),tuple(cmds),current)

def corpus()->Iterable[tuple[ProgramSpec,Program]]:
    for spec in build_specs(): yield spec,build_program(spec)
