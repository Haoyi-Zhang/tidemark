"""Saved-run control-flow tests with an explicit non-native backend double.

The tiny owned source uses actual generation, admission, embed/check and both
interpreters. LLVM/object replay is replaced; this creates no native evidence.
"""
import gzip
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from tidemark import core, native

ROOT = Path(__file__).resolve().parents[1]

def load_driver():
    jit = types.ModuleType('tidemark.native_jit')
    llvm = types.ModuleType('llvmlite')
    llvm.binding = types.ModuleType('llvmlite.binding')
    spec = importlib.util.spec_from_file_location('saved_goal_test_driver', ROOT/'scripts/run_native_study.py')
    driver = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {'tidemark.native_jit': jit, 'llvmlite': llvm,
                                      'llvmlite.binding': llvm.binding}):
        spec.loader.exec_module(driver)
    return driver

class NativeSavedGoalTests(unittest.TestCase):
    def setUp(self):
        self.d = load_driver()
        self.name, self.source = next(self.d.sources(True))
        self.values = self.d.oracle(self.source)

    def projected_measure(self, name, source, policy, goal, payload, values):
        target, ir, wrapper = native.embed(source, payload, self.d.BOX, policy)
        self.assertEqual(native.check(core.serialize_program(source), core.serialize_program(target), ir, wrapper), tuple(payload))
        self.assertEqual(self.d.oracle(target), values)
        return dict(kind='attempt', id=name, policy=policy, goal=goal,
                    payload=list(payload), status='embedded', native=values,
                    optimized_native=values, oracle=values, orientations=[],
                    mutations=[], object_base64='', optimized_object_base64='',
                    optimized_ir='NON-NATIVE TEST DOUBLE', ir=ir.decode(),
                    wrapper=json.loads(wrapper), target=target.to_obj())

    def fixture(self, out, small, changed=None, changed_goal=None):
        d, p = self.d, self.source
        candidates = core.discover_candidates(p)
        refs = d.reference.candidates(p.to_obj())
        plan = d.overlap.select(candidates, 'mode4')
        cap = core.payload_capacity(len(plan))
        goals = ([(f'all-{n}-{k}', bits) for n in range(cap+1)
                  for k,bits in enumerate(itertools.product((0,1), repeat=n))] if small else
                 [('empty', ()), ('fixed8', (0,1)*4), ('saturation', tuple(i%2 for i in range(cap)))])
        # For this six-body toy the full fixed8 case is capacity-rejected;
        # retain that normal path instead of increasing the source cohort.
        rows = [dict(kind='source', id=self.name, source=p.to_obj(), box=d.BOX,
                     inputs=d.INPUTS, source_ir=native.lower(p,d.BOX).decode(),
                     candidates=refs, optimum=d.overlap.optimum_count(refs,len(p.commands)),
                     conflicts=sum(not(a.end<b.start or b.end<a.start) for i,a in enumerate(candidates) for b in candidates[i+1:]),
                     policies={'mode4':dict(sites=len(plan), capacity=cap,
                                           schedule=[json.loads(s.descriptor_bytes) for s in plan])},
                     range_audit=native.admit(p,d.BOX), native_source=self.values)]
        for index,(goal,payload) in enumerate(goals):
            if changed is not None and (goal == changed_goal if changed_goal else index == 0): payload = changed
            rows.append(self.fake_measure(self.name,p,'mode4',goal,payload,self.values))
        summary = d.summarize(rows)
        summary.update(small=small, source_versions=d.hashes())
        (out/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
        with gzip.open(out/'raw.jsonl.gz','wt',encoding='utf-8') as stream:
            stream.write('\n'.join(json.dumps(row) for row in rows)+'\n')
        return summary

    def fake_measure(self, name, source, policy, goal, payload, values):
        capacity = core.payload_capacity(len(self.d.overlap.select(core.discover_candidates(source),policy)))
        if len(payload)>capacity:
            return dict(kind='attempt',id=name,policy=policy,goal=goal,payload=list(payload),status='capacity-rejected',reason='NON-NATIVE TEST DOUBLE')
        return self.projected_measure(name,source,policy,goal,payload,values)

    def exercise(self, small, changed=None, changed_goal=None, valid_before=0):
        d = self.d
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(d, 'sources', return_value=iter([(self.name,self.source)])), \
             mock.patch.object(d.overlap, 'POLICIES', ('mode4',)), \
             mock.patch.object(d.native_jit, 'initialize', create=True), \
             mock.patch.object(d.native_jit, 'execute', return_value=(self.values,'NON-NATIVE TEST DOUBLE',b''),create=True) as replay, \
             mock.patch.object(d, 'measure', side_effect=self.fake_measure) as measure:
            out=Path(temp)
            expected=self.fixture(out,small,changed,changed_goal)
            if changed is None:
                result=d.verify(out)
                self.assertEqual(result['counts'],expected['counts'])
                self.assertGreater(measure.call_count,0)
            else:
                with self.assertRaisesRegex(ValueError, 'goal/payload mismatch'):
                    d.verify(out)
                self.assertEqual(measure.call_count,valid_before,'bad attempt and later attempts must not replay')
                self.assertEqual(replay.call_count,1,'only the admitted source, no target or later replay')

    def test_correct_small_and_controlled_goals(self):
        for small in (True,False):
            with self.subTest(small=small): self.exercise(small)

    def test_source_identity_is_exact_except_one_named_predecessor(self):
        current=self.d.hashes()
        legacy=dict(current, **{'scripts/run_native_study.py': self.d.LEGACY_DRIVER_SHA256})
        self.d.check_source_versions(current)
        self.d.check_source_versions(legacy)
        for versions in (current,legacy):
            for key in versions:
                with self.subTest(key=key,legacy=versions==legacy):
                    bad=dict(versions,**{key:'0'*64})
                    with self.assertRaisesRegex(ValueError,'source version mismatch'):
                        self.d.check_source_versions(bad)
        with self.assertRaisesRegex(ValueError,'source version mismatch'):
            self.d.check_source_versions(dict(legacy, unexpected='0'*64))

    def test_goal_indices_and_policy_capacity_bind_exact_bits(self):
        for cap in range(5):
            expected=[(f'all-{n}-{k}', tuple(int(b) for b in format(k,f'0{n}b')) if n else ())
                      for n in range(cap+1) for k in range(1<<n)]
            self.assertEqual(self.d.study_goals(cap,True),expected)
            self.assertEqual(self.d.study_goals(cap,False),
                             [('empty',()),('fixed8',(0,1)*4),('saturation',tuple(i%2 for i in range(cap)))])

    def test_small_empty_goal_cannot_carry_nonempty_payload(self):
        self.exercise(True,(0,))

    def test_controlled_empty_goal_cannot_carry_nonempty_payload(self):
        self.exercise(False,(0,))

    def test_small_same_length_wrong_index_payload_is_rejected(self):
        self.exercise(True,(1,),changed_goal='all-1-0',valid_before=1)

    def test_controlled_same_length_wrong_saturation_is_rejected(self):
        cap=core.payload_capacity(len(self.d.overlap.select(core.discover_candidates(self.source),'mode4')))
        self.assertGreater(cap,0)
        self.exercise(False,tuple(1-i%2 for i in range(cap)),changed_goal='saturation',valid_before=2)

    def test_goal_only_fixed8_relabel_is_rejected(self):
        # A row labelled fixed8 with an empty payload is internally replayable,
        # but does not establish a fixed-eight-bit success.
        d=self.d
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(d,'sources',return_value=iter([(self.name,self.source)])), \
             mock.patch.object(d.overlap,'POLICIES',('mode4',)), \
             mock.patch.object(d.native_jit,'initialize',create=True), \
             mock.patch.object(d.native_jit,'execute',return_value=(self.values,'TEST DOUBLE',b''),create=True), \
             mock.patch.object(d,'measure',side_effect=self.fake_measure) as measure:
            out=Path(temp); self.fixture(out,False)
            with gzip.open(out/'raw.jsonl.gz','rt',encoding='utf-8') as stream:
                rows=[json.loads(line) for line in stream]
            rows[2]=self.fake_measure(self.name,self.source,'mode4','fixed8',(),self.values)
            summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
            summary.update(d.summarize(rows))
            (out/'summary.json').write_text(json.dumps(summary),encoding='utf-8')
            with gzip.open(out/'raw.jsonl.gz','wt',encoding='utf-8') as stream:
                stream.write('\n'.join(json.dumps(row) for row in rows)+'\n')
            with self.assertRaisesRegex(ValueError,'goal/payload mismatch'): d.verify(out)
            self.assertEqual(measure.call_count,1,'only the earlier valid empty attempt may replay')

if __name__=='__main__': unittest.main()
