"""Tie the running figure to Mode 4 and require the complete Python inventory."""
import ast
from pathlib import Path
import runpy
import tempfile
import types
import unittest
from unittest import mock
from tidemark import core, reference

A=Path(__file__).resolve().parents[1]

class FigureContractTests(unittest.TestCase):
    def test_running_example_frame_and_target(self):
        E,C,T=core.Expr,core.Command,core.Type
        p=core.Program(tuple((n,T.INT) for n in ('a','b','c','d')),(),
            (C('u',E.binary('add',E.var('a'),E.var('b'))),C('v',E.var('u')),
             C('p',E.binary('sub',E.var('c'),E.integer(1))),
             C('q',E.binary('sub',E.var('d'),E.integer(2))),
             C('z',E.binary('sub',E.var('p'),E.var('q')))), 'z')
        sites=core.select_sites(core.discover_candidates(p))
        self.assertEqual([(s.family,s.start+1,s.end+1) for s in sites],
                         [('operand',1,1),('identity',2,2),('adjacent',3,4)])
        self.assertEqual(core.frame_bits((1,),len(sites)),(0,1,1))
        target,cert=core.embed(p,(1,))
        self.assertEqual([c.name for c in target.commands],['u','v','q','p','z'])
        self.assertEqual(target.commands[0],p.commands[0])
        self.assertEqual(target.commands[1].expr,E.binary('add',E.var('u'),E.integer(0)))
        args=core.serialize_program(p),core.serialize_program(target),cert.to_bytes()
        self.assertEqual(core.check_certificate(*args),(1,))
        self.assertEqual(reference.check(*args),(1,))

    def test_generator_has_five_explicit_schematics(self):
        tree=ast.parse((A/'figures/draw_schematics.py').read_text(encoding='utf-8'))
        inventory=next(ast.literal_eval(n.value) for n in tree.body
                       if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SCHEMATICS' for t in n.targets))
        self.assertEqual(inventory,('figure-01','figure-02','figure-03','figure-04','native-connection'))
        self.assertIn("'text.usetex':False",(A/'figures/draw_schematics.py').read_text(encoding='utf-8'))

    def test_complete_builder_needs_no_figure_tex_subprocess(self):
        script=A.parent/'paper/figures/build_figures.py'
        if not script.is_file():self.skipTest('standalone checkout has no sibling manuscript')
        builder=runpy.run_path(str(script))
        self.assertEqual(builder['SCHEMATICS'][-1],'native-connection')
        with tempfile.TemporaryDirectory(prefix='tidemark-python-figure-') as temp:
            out=Path(temp)
            def schematics(folder):
                for name in builder['SCHEMATICS']:(folder/(name+'.pdf')).write_bytes(b'owned fixture')
            stats=types.SimpleNamespace(HERE=None,register_fonts=lambda family:None)
            def draw():
                for name in ('evaluation-capacity','evaluation-cost'):
                    (stats.HERE/(name+'.pdf')).write_bytes(b'owned retained fixture')
            stats.draw=draw
            load=lambda name,path:types.SimpleNamespace(draw=schematics) if name=='tidemark_schematics' else stats
            with mock.patch.dict(builder['build'].__globals__,{'load':load}), mock.patch('subprocess.run',side_effect=AssertionError('figure TeX subprocess')):
                result=builder['build'](out)
            self.assertEqual(len(result),7)
            self.assertTrue(all((out/(name+'.pdf')).is_file() for name in result))

if __name__=='__main__':unittest.main()
