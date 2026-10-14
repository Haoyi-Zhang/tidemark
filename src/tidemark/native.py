"""Range-admitted lowering of owned, pure TideMark trees to scalar LLVM IR.

This is not an arbitrary-LLVM parser or a production compiler validator. The
separate wrapper checks exact generated IR; Mode-4 and historical data remain
unchanged. LLVM/ABI correctness is a stated trust boundary, not a Coq verdict.
"""
from __future__ import annotations

import json

from . import core

VERSION = "tidemark-pure-i64-lowering-1"
MIN = -(1 << 63)
MAX = (1 << 63) - 1


class NativeError(core.TideMarkError):
    pass


def admit(program, box):
    """Sound, nonrelational interval sufficient condition over ALL subtrees.

    Both arms of a pure conditional are checked: LLVM select eagerly computes
    them. Boolean parameters cover both values; the box has exactly Int names.
    """
    # Public dataclasses can be hand-built; enforce the serialized grammar too.
    core.parse_program(core.serialize_program(program))
    analysis = core.typecheck_program(program)
    if program.regions or any(t == core.Type.UNIT for _, t in program.params):
        raise NativeError("pure Int/Bool interface required")
    integers = {n for n, t in program.params if t == core.Type.INT}
    if not isinstance(box, dict) or set(box) != integers:
        raise NativeError("box domain")

    def checked(interval):
        lo, hi = interval
        if not MIN <= lo <= hi <= MAX:
            raise NativeError("signed-i64 range not established")
        return lo, hi

    env = {}
    for name, typ in program.params:
        if typ == core.Type.INT:
            value = box[name]
            if (not isinstance(value, (list, tuple)) or len(value) != 2
                    or any(type(x) is not int for x in value)):
                raise NativeError("box interval")
            env[name] = checked(value)
        else:
            env[name] = None

    def interval(e):
        tag, a = e.tag, e.args
        if tag == "var":
            return env[a[0]]
        if tag == "int":
            return checked((a[0], a[0]))
        if tag == "bool":
            return None
        if tag == "not":
            interval(a[0])
            return None
        if tag == "if":
            interval(a[0])
            left, right = interval(a[1]), interval(a[2])
            if left is None:
                return None
            return checked((min(left[0], right[0]), max(left[1], right[1])))
        if tag == "bin":
            op, l, r = a
            x, y = interval(l), interval(r)
            if op in {"eq", "lt"}:
                return None
            if op == "add":
                z = x[0] + y[0], x[1] + y[1]
            elif op == "sub":
                z = x[0] - y[1], x[1] - y[0]
            elif op == "mul":
                corners = [a * b for a in x for b in y]
                z = min(corners), max(corners)
            else:
                raise NativeError("unsupported arithmetic")
            return checked(z)
        raise NativeError("effectful or unsupported expression")

    audit = []
    for command in program.commands:
        value = interval(command.expr)
        env[command.name] = value
        audit.append([command.name, list(value) if value is not None else None])
    if analysis.result_type not in {core.Type.INT, core.Type.BOOL}:
        raise NativeError("pure result required")
    return audit


def _name(prefix, value):
    # Injective UTF-8 names and separate namespaces; no raw text interpolated.
    return "%" + prefix + value.encode("utf-8").hex()


def _types(program):
    analysis = core.typecheck_program(program)
    types = dict(program.params)
    types.update((c.name, t) for c, t in zip(program.commands, analysis.command_types))
    return types


def command_ir(command, program):
    """Names/temporaries depend on binder, not command ordinal or payload."""
    types = _types(program)
    params = dict(program.params)
    lines = []

    def typ(t):
        return "i64" if t == core.Type.INT else "i1"

    def instruction(rhs, t):
        result = _name("t", command.name) + "_" + str(len(lines))
        lines.append(f"  {result} = {rhs}")
        return result, t

    def expr(e):
        tag, a = e.tag, e.args
        if tag == "var":
            return _name("p" if a[0] in params else "c", a[0]), types[a[0]]
        if tag == "int":
            return str(a[0]), core.Type.INT
        if tag == "bool":
            return "true" if a[0] else "false", core.Type.BOOL
        if tag == "not":
            v, _ = expr(a[0])
            return instruction(f"xor i1 {v}, true", core.Type.BOOL)
        if tag == "if":
            c, _ = expr(a[0])
            l, t = expr(a[1])
            r, _ = expr(a[2])
            return instruction(f"select i1 {c}, {typ(t)} {l}, {typ(t)} {r}", t)
        if tag == "bin":
            op, left, right = a
            l, t = expr(left)
            r, _ = expr(right)
            if op in {"eq", "lt"}:
                return instruction(f"icmp {'eq' if op == 'eq' else 'slt'} {typ(t)} {l}, {r}", core.Type.BOOL)
            return instruction(f"{op} i64 {l}, {r}", core.Type.INT)
        raise NativeError("lowering subset")

    value, t = expr(command.expr)
    # Copy is explicit or-with-zero. Direct and expanded identities therefore
    # remain distinguishable in PRE-optimization IR even for literal bases.
    lines.append(f"  {_name('c', command.name)} = or {typ(t)} {value}, {'0' if t == core.Type.INT else 'false'}")
    return "\n".join(lines) + "\n"


def lower(program, box):
    admit(program, box)
    args = ", ".join(f"i64 {_name('a', n)}" for n, _ in program.params)
    text = f"; {VERSION}\ndefine i64 @run({args}) {{\nentry:\n"
    for name, typ in program.params:
        p, a = _name("p", name), _name("a", name)
        text += f"  {p} = " + (f"or i64 {a}, 0\n" if typ == core.Type.INT else f"trunc i64 {a} to i1\n")
    for index, command in enumerate(program.commands):
        text += f"; cmd {index}\n" + command_ir(command, program)
    text += "; end commands\n"
    types = _types(program)
    result = _name("p" if program.result in dict(program.params) else "c", program.result)
    if types[program.result] == core.Type.BOOL:
        text += f"  %return_bool = zext i1 {result} to i64\n"
        result = "%return_bool"
    return (text + f"  ret i64 {result}\n}}\n").encode("ascii")


def extract_ir(source, ir, box, policy="mode4"):
    """Decode generated command fragments, not a sidecar copy of Q/payload.

    Whole-IR authorization belongs to check(), just as core extraction alone
    does not constrain unrelated target syntax. Comments are coordinates, not
    authenticated truth: exact replay in check() constrains them too.
    """
    from . import overlap
    admit(source, box)
    text = ir.decode("ascii")
    chunks = []
    for i in range(len(source.commands)):
        start = f"; cmd {i}\n"
        end = f"; cmd {i + 1}\n" if i + 1 < len(source.commands) else "; end commands\n"
        if text.count(start) != 1 or text.count(end) != 1:
            raise NativeError("command coordinates")
        chunks.append(text.split(start, 1)[1].split(end, 1)[0])
    bits = []
    for site in overlap.select(core.discover_candidates(source), policy):
        actual = "".join(chunks[site.start:site.end + 1])
        choices = []
        for bit in (0, 1):
            # Type map is unchanged by every family in the pure subset.
            rendered = "".join(command_ir(c, source) for c in site.render(bit))
            choices.append(actual == rendered)
        if choices[0] == choices[1]:
            raise NativeError("lowered orientation not unique")
        bits.append(0 if choices[0] else 1)
    return core.unframe_bits(bits)


def embed(source, payload, box, policy="mode4"):
    from . import overlap
    admit(source, box)
    target, certificate = overlap.embed(source, payload, policy)
    ir = lower(target, box)  # target must independently pass range admission
    wrapper = core.canonical_json({"version": VERSION, "box": box, "policy": policy,
                                   "core_certificate": json.loads(certificate),
                                   "ir_sha256": core.digest_bytes(ir)})
    return target, ir, wrapper


def check(source_bytes, target_bytes, ir, wrapper):
    from . import overlap, reference
    value = reference.parse(wrapper)
    if set(value) != {"version", "box", "policy", "core_certificate", "ir_sha256"} or value["version"] != VERSION:
        raise NativeError("native wrapper")
    policy, box = value["policy"], value["box"]
    payload = overlap.check(source_bytes, target_bytes, core.canonical_json(value["core_certificate"]), policy)
    source, target = core.parse_program(source_bytes), core.parse_program(target_bytes)
    admit(source, box)
    if core.digest_bytes(ir) != value["ir_sha256"] or lower(target, box) != ir:
        raise NativeError("native exact replay")
    if extract_ir(source, ir, box, policy) != payload:
        raise NativeError("native extraction")
    return payload
