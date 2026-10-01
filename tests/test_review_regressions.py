"""Boundary cases used to keep the revised manuscript's examples precise."""
import unittest
from tidemark.core import Program,Command,Expr,Type,discover_candidates,canonical_json
from tidemark import reference

class ManuscriptBoundaryRegressions(unittest.TestCase):
    def program(self,expr):
        return Program((('a',Type.INT),('b',Type.INT)),(),(Command('x',expr),),'x')
    def families(self,program):
        prod=discover_candidates(program)
        ref=reference.candidates(program.to_obj())
        self.assertEqual([s.family for s in prod],[s[0] for s in ref])
        return [s.family for s in prod]
    def test_compound_plus_zero_is_operand_not_identity(self):
        p=self.program(Expr.binary('add',Expr.binary('add',Expr.var('a'),Expr.var('b')),Expr.integer(0)))
        self.assertEqual(self.families(p),['operand'])
    def test_equal_zero_operands_can_be_identity(self):
        p=self.program(Expr.binary('add',Expr.integer(0),Expr.integer(0)))
        self.assertEqual(self.families(p),['identity'])
    def test_equal_variable_operands_have_no_singleton(self):
        p=self.program(Expr.binary('add',Expr.var('a'),Expr.var('a')))
        self.assertEqual(self.families(p),[])
