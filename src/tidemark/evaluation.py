from __future__ import annotations
import json, random, time, resource
from collections import Counter,defaultdict
from dataclasses import replace
from .core import *
from .corpus import corpus, FAMILIES
from . import reference
from .structural import build_derivation, build_reference_derivation, verify_derivation, Derivation

def _inputs(program_index:int):
    for j in range(8): yield {"arg":program_index*17+j-31},{"r":j-4}

def _payload(index:int,cap:int):
    rng=random.Random(index*0x9E3779B1+17); return tuple(rng.randrange(2) for _ in range(cap))

def run()->dict:
    start=time.perf_counter(); rows=[]; totals=Counter(); family=defaultdict(Counter); corpus_hash=__import__('hashlib').sha256(); local_budget=809
    zero_keys=["accepted_mutations","reference_accepted_mutations","accepted_proof_mutations","selector_differences","frame_failures","reference_selection_differences","reference_target_differences","reference_acceptance_differences","reference_evaluator_differences","full_semantic_differences","local_carrier_differences","derivation_failures","derivation_producer_differences"]
    for k in zero_keys: totals[k]=0
    for pidx,(spec,source) in enumerate(corpus()):
        analysis=typecheck_program(source); candidates=discover_candidates(source); sites=select_sites(candidates)
        if len(sites)!=spec.capacity: raise AssertionError((spec,len(sites),[(s.family,s.start,s.end) for s in sites][:20]))
        cap=payload_capacity(len(sites)); payload=_payload(pidx,cap); target,cert=embed(source,payload)
        sb=serialize_program(source); tb=serialize_program(target); cb=cert.to_bytes(); corpus_hash.update(sb)
        got=check_certificate(sb,tb,cb)
        if got!=payload: raise AssertionError("extract")
        try: rgot=reference.check(sb,tb,cb)
        except Exception: totals["reference_acceptance_differences"]+=1; raise
        if rgot!=payload: totals["reference_acceptance_differences"]+=1; raise AssertionError("reference")
        rp=reference.parse(sb); rq=reference.parse(tb)
        rs=reference.select(reference.candidates(rp))
        prod_sig=[(s.family,s.start,s.end) for s in sites]; ref_sig=[(s[0],s[1],s[2]) for s in rs]
        if prod_sig!=ref_sig: totals["reference_selection_differences"]+=1; raise AssertionError("selection")
        if reference.canon(reference.replay(rp,rs,reference.frame(list(payload),len(rs))))!=tb: totals["reference_target_differences"]+=1; raise AssertionError("target")
        for input_no,(params,store) in enumerate(_inputs(pidx)):
            ps=evaluate_program(source,params,store); pt=evaluate_program(target,params,store)
            if ps!=pt: totals["full_semantic_differences"]+=1; raise AssertionError("semantic")
            totals["full_executions"]+=1
            if input_no<2:
                if reference.evaluate(rp,params,store)!=ps or reference.evaluate(rq,params,store)!=pt: totals["reference_evaluator_differences"]+=1; raise AssertionError("reference evaluator")
                totals["reference_evaluator_calls"]+=1
        # Sample exactly 809 local carrier equations across the frozen corpus.
        if local_budget:
            take=min(local_budget,len(sites))
            params,store=next(_inputs(pidx))
            for site in sites[:take]:
                q0=replay(source,(site,),(0,)); q1=replay(source,(site,),(1,))
                if evaluate_program(q0,params,store)!=evaluate_program(q1,params,store): totals["local_carrier_differences"]+=1; raise AssertionError("local law")
                totals["local_carrier_cases"]+=1
            local_budget-=take
        # Five deterministic nontrivial mutations per program.
        obj=json.loads(cb); mutations=[]
        for field in ("mode","checker","source_sha256","target_sha256"):
            x=dict(obj); x[field]=(x[field][::-1] if field.endswith("sha256") else x[field]+"x"); mutations.append(canonical_json(x))
        x=dict(obj); x["payload"]=("1" if not x["payload"] else ("1" if x["payload"][0]=="0" else "0")+x["payload"][1:]); mutations.append(canonical_json(x))
        for m in mutations:
            try: check_certificate(sb,tb,m); totals["accepted_mutations"]+=1
            except Exception: pass
            try: reference.check(sb,tb,m); totals["reference_accepted_mutations"]+=1
            except Exception: pass
            totals["certificate_mutations"]+=1
        t1,d1=build_derivation(source,payload); t2,d2=build_reference_derivation(source,payload)
        if d1.to_bytes()!=d2.to_bytes(): totals["derivation_producer_differences"]+=1; raise AssertionError("derivation producer")
        if serialize_program(t1)!=serialize_program(target) or not verify_derivation(source,target,d1,payload): totals["derivation_failures"]+=1; raise AssertionError("derivation")
        totals["derivations"]+=2
        # Alternate seven and eight proof mutations to total 3,000.
        nmut=8 if pidx<200 else 7; dobj=d1.to_obj()
        for k in range(nmut):
            m=json.loads(json.dumps(dobj))
            if m["steps"]:
                row=m["steps"][k%len(m["steps"])]
                if k%4==0: row["bit"]=1-row["bit"]
                elif k%4==1: row["family"]="bad"
                elif k%4==2: row["orientation_hash"]="0"*64
                else: row["start"]+=1
            else: m["source_hash"]="0"*64
            md=Derivation(m["source_hash"],m["target_hash"],tuple(tuple(x) for x in m["selected"]),tuple(m["framed_bits"]),tuple(m["steps"]))
            if verify_derivation(source,target,md,payload): totals["accepted_proof_mutations"]+=1
            totals["proof_mutations"]+=1
        fam=Counter(s.family for s in sites)
        row={"family":spec.family,"index":spec.index,"bindings":len(source.commands),"selected":len(sites),"payload_bits":cap,"operand":fam["operand"],"identity":fam["identity"],"adjacent":fam["adjacent"],"source_bytes":len(sb),"target_bytes":len(tb),"certificate_bytes":len(cb)}
        rows.append(row); family[spec.family].update(row)
        totals.update({"programs":1,"bindings":len(source.commands),"selected":len(sites),"payload_bits":cap,"header_bits":len(sites)-cap,"operand":fam["operand"],"identity":fam["identity"],"adjacent":fam["adjacent"],"source_bytes":len(sb),"target_bytes":len(tb),"certificate_bytes":len(cb)})
    if local_budget!=0: raise AssertionError(("local budget",local_budget))
    # Exhaust all masks of a fixed 16-interval universe against independent DP count.
    intervals=[Site("operand",i//2,i//2,(),()) if i%3 else Site("adjacent",i//2,i//2+1,(),()) for i in range(16)]
    for mask in range(1<<16):
        xs=[intervals[i] for i in range(16) if mask>>i&1]
        if len(select_sites(xs))!=optimal_interval_count(xs): totals["selector_differences"]+=1
        totals["interval_instances"]+=1
    # Exhaust every legal message for site counts 0..16.
    for n in range(17):
        c=payload_capacity(n)
        for L in range(c+1):
            for value in range(1<<L):
                msg=tuple((value>>k)&1 for k in reversed(range(L)))
                if unframe_bits(frame_bits(msg,n))!=msg: totals["frame_failures"]+=1
                totals["frame_cases"]+=1
    elapsed=time.perf_counter()-start
    summary={
      "schema":"tidemark-evaluation",
      "seed":"tidemark-fixed-seed",
      **{k:int(v) for k,v in totals.items()},
      "corpus_digest":corpus_hash.hexdigest(),
      "derivation_steps_per_producer":totals["selected"],
      "derivation_nodes_per_producer":totals["selected"]+totals["programs"],
      "derivation_premises_per_producer":5*totals["selected"],
      "elapsed_seconds":elapsed,
      "peak_rss_kb":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
      "aggregate_target_growth_percent":100*(totals["target_bytes"]/totals["source_bytes"]-1),
      "aggregate_certificate_source_percent":100*totals["certificate_bytes"]/totals["source_bytes"],
      "family_rows":rows,
      "claim_boundary":"Finite executions, independent implementations, mutations, and bounded exhaustive audits validate this executable implementation. Universal semantic and extraction claims depend on the paper metatheory; capacity and cost remain corpus dependent."
    }
    return summary

