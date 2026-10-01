#!/usr/bin/env python3
"""Export exact current result paths to alphabetic LaTeX commands. No expected-output search."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[2];D=R/'artifact/data/derived';P=R/'paper'
files={'eval':D/'evaluation-summary-mode4.json','llvm':D/'llvm-projection-mode4.json','algebra':D/'finite-algebra-mode4.json'}
x={k:json.loads(p.read_text()) for k,p in files.items()};v={};paths={}
def put(name,which,path):
 y=x[which]
 for k in path.split('.'):y=y[int(k)] if isinstance(y,list) else y[k]
 if not isinstance(y,(int,float)) or isinstance(y,bool):raise ValueError((name,y))
 v[name]=y;paths[name]={'file':files[which].relative_to(R).as_posix(),'key':path}
for n,k in {'Programs':'programs','Bindings':'bindings','SelectedSites':'selected','HeaderBits':'header_bits','PayloadBits':'payload_bits','FullExecutions':'full_executions','LocalChecks':'local_carrier_cases','CertificateMutations':'certificate_mutations','IntervalInstances':'interval_instances','FrameVectors':'frame_vectors','ValidFrames':'legal_frames','OperandSites':'operand','IdentitySites':'identity','AdjacentSites':'adjacent','StructuralRecords':'derivations','ApplicableProofMutations':'proof_mutations','NoStepRows':'derivation_mutations_not_applicable','ReferenceCalls':'reference_evaluator_calls','SourceBytes':'source_bytes','TargetBytes':'target_bytes','CertificateBytes':'certificate_bytes','RssKiB':'peak_rss_kb','CertificatePercent':'aggregate_certificate_source_percent','TargetGrowthPercent':'aggregate_target_growth_percent','DescriptorPercent':'aggregate_descriptor_rich_source_percent'}.items():put(n,'eval',k)
put('FiniteCases','algebra','total_cases');put('Countermodels','algebra','countermodels_found')
for stage in ['analysis','discovery','selection','embed','check','reference','derivation','evaluation']:
 key=stage+'_ms'
 if key not in x['eval']['timing_summary'] and stage=='reference':key='reference_check_ms'
 for q,suf in [('median','MedianMs'),('p95','PninetyfiveMs')]:put(stage.title()+suf,'eval','timing_summary.'+key+'.'+q)
put('ExternalAttempts','llvm','attempts');put('ExternalSources','llvm','snapshot_source_files')
for st,word in [('O0','OZero'),('O1','OOne'),('O2','OTwo')]:
 for key,suf in [('payload_bits','Bits'),('adjacent_only_payload_bits','AdjacentBits'),('operand_only_payload_bits','OperandBits'),('successful_modules','Modules'),('instructions','Instructions')]:put('Llvm'+word+suf,'llvm','stages.'+st+'.'+key)
for family,name in [('pure-arithmetic','Pure'),('dependence-heavy','Dependence'),('region-state','Region'),('ordered-trace','Trace'),('branches','Branch'),('mixed','Mixed'),('random','Random')]:put(name+'Bits','eval','family_summary.'+family+'.payload_bits')
for i,s in enumerate('ABCDE'):put('Length'+s,'eval',f'length_groups.{i}.programs')
put('DescriptorBytes','eval','descriptor_rich_bytes')
put('DescriptorRatio','eval','descriptor_rich_to_compact_ratio')
put('StructuralFieldValues','eval','derivation_step_fields_per_producer')
put('AdjacentPairs','eval','adjacent_pairs')
put('CorrCheck','eval','correlations.bindings_check_ms_spearman')
put('CorrEmbed','eval','correlations.bindings_embed_ms_spearman')
put('CorrSites','eval','correlations.bindings_selected_spearman')
(P/'tables').mkdir(exist_ok=True)
abl=x['eval']['carrier_ablation']
labels={'operand':'Operand','identity':'Identity','adjacent':'Adjacent','identity+operand':'Identity + operand','identity+adjacent':'Identity + adjacent','operand+adjacent':'Operand + adjacent','identity+operand+adjacent':'All three families'}
order=['operand','identity','adjacent','identity+operand','identity+adjacent','operand+adjacent','identity+operand+adjacent']
rows=[]
for key in order:
 d=abl[key];rows.append(f"{labels[key]} & {d['selected_sites']:,} & {d['payload_bits']:,} & {d['zero_capacity_programs']} "+r"\\")
(P/'tables'/'carrier-ablation-rows.tex').write_text(r'''\begin{tabular}{@{}lrrr@{}}
\toprule
Library & Selected sites & User bits & Zero-capacity programs\\
\midrule
'''+ '\n'.join(rows)+r'''
\bottomrule
\end{tabular}
''')
lines=['% Generated from exact current result paths. Do not edit values by hand.']
for name,y in sorted(v.items()):
 if not name.isalpha():raise ValueError(name)
 text=f'{y:.3f}'.rstrip('0').rstrip('.') if isinstance(y,float) else str(y)
 lines.append(r'\newcommand{\TM'+name+'}{'+text+'}')
(P/'data-macros.tex').write_text('\n'.join(lines)+'\n')
(P/'data-macros.json').write_text(json.dumps({'values':v,'sources':paths,'input_sha256':{p.relative_to(R).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files.values()}},indent=2)+'\n')
print('Exported',len(v),'bound values')
