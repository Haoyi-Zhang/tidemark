"""Straight-line typed Python-to-owned-IR adapter, with no guessing fallback."""
from __future__ import annotations
import ast
from . import core


def translate(text: str) -> core.Program:
    tree = ast.parse(text)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise core.TideMarkError("one synchronous function required")
    fn = tree.body[0]
    args = fn.args
    if (fn.decorator_list or getattr(fn, "type_params", ()) or args.posonlyargs or args.kwonlyargs
            or args.vararg or args.kwarg or args.defaults or args.kw_defaults
            or fn.type_comment or not isinstance(fn.returns, ast.Name)
            or fn.returns.id != "int"):
        raise core.TideMarkError("unsupported function interface")
    params = []
    for arg in args.args:
        if (not isinstance(arg.annotation, ast.Name)
                or arg.annotation.id not in {"int", "bool"} or arg.type_comment):
            raise core.TideMarkError("exact int/bool annotations required")
        params.append((arg.arg, core.Type.INT if arg.annotation.id == "int" else core.Type.BOOL))

    def expr(node):
        E = core.Expr
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            return E.var(node.id)
        if isinstance(node, ast.Constant):
            if type(node.value) is bool:
                return E.boolean(node.value)
            if type(node.value) is int:
                return E.integer(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in {ast.Add, ast.Sub, ast.Mult}:
            return E.binary({ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul"}[type(node.op)],
                            expr(node.left), expr(node.right))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in {ast.Eq, ast.Lt}:
            return E.binary("eq" if isinstance(node.ops[0], ast.Eq) else "lt",
                            expr(node.left), expr(node.comparators[0]))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return E.logical_not(expr(node.operand))
        if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
                and isinstance(node.operand, ast.Constant) and type(node.operand.value) is int):
            return E.integer(-node.operand.value)
        if isinstance(node, ast.IfExp):
            return E.choose(expr(node.test), expr(node.body), expr(node.orelse))
        raise core.TideMarkError("unsupported expression")

    if not fn.body or not isinstance(fn.body[-1], ast.Return) or not isinstance(fn.body[-1].value, ast.Name):
        raise core.TideMarkError("final named return required")
    commands = []
    for statement in fn.body[:-1]:
        if (not isinstance(statement, ast.Assign) or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name) or statement.type_comment):
            raise core.TideMarkError("single-name immutable assignment required")
        commands.append(core.Command(statement.targets[0].id, expr(statement.value)))
    program = core.Program(tuple(params), (), tuple(commands), fn.body[-1].value.id)
    if core.typecheck_program(program).result_type != core.Type.INT:
        raise core.TideMarkError("int result required")
    core.parse_program(core.serialize_program(program))
    return program


def validated_function(text: str):
    """Execute only the already-admitted, call/effect-free Python grammar."""
    translate(text)
    tree = ast.parse(text)
    namespace = {"__builtins__": {}, "int": int, "bool": bool}
    exec(compile(tree, "<typed-straight-line-function>", "exec"), namespace)
    return namespace[tree.body[0].name]
