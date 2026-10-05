from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "tidemark-certificate-4"
MODE_VERSION = "tidemark-mode-4"
CHECKER_VERSION = "tidemark-checker-4"
FAMILY_RANK = {"identity": 0, "operand": 1, "adjacent": 2}


class TideMarkError(ValueError):
    pass


class Type(str, Enum):
    INT = "Int"
    BOOL = "Bool"
    UNIT = "Unit"


@dataclass(frozen=True)
class Effect:
    reads: frozenset[str] = frozenset()
    writes: frozenset[str] = frozenset()
    emits: bool = False

    def join(self, other: "Effect") -> "Effect":
        return Effect(self.reads | other.reads, self.writes | other.writes, self.emits or other.emits)

    def commutes_with(self, other: "Effect") -> bool:
        if self.emits and other.emits:
            return False
        return not (
            self.writes & (other.reads | other.writes)
            or other.writes & (self.reads | self.writes)
        )

    def to_obj(self) -> dict[str, Any]:
        return {"reads": sorted(self.reads), "writes": sorted(self.writes), "emits": self.emits}


@dataclass(frozen=True)
class Expr:
    tag: str
    args: tuple[Any, ...] = ()

    @staticmethod
    def var(name: str) -> "Expr":
        if not isinstance(name, str) or not name:
            raise TideMarkError("variable name must be a nonempty string")
        return Expr("var", (name,))

    @staticmethod
    def integer(value: int) -> "Expr":
        if type(value) is not int:
            raise TideMarkError("integer literal must have exact Python int type")
        return Expr("int", (value,))

    @staticmethod
    def boolean(value: bool) -> "Expr":
        if type(value) is not bool:
            raise TideMarkError("boolean literal must have exact Python bool type")
        return Expr("bool", (value,))
    @staticmethod
    def binary(op: str, left: "Expr", right: "Expr") -> "Expr": return Expr("bin", (op, left, right))
    @staticmethod
    def logical_not(value: "Expr") -> "Expr": return Expr("not", (value,))
    @staticmethod
    def get(region: str) -> "Expr": return Expr("get", (region,))
    @staticmethod
    def put(region: str, value: "Expr") -> "Expr": return Expr("put", (region, value))
    @staticmethod
    def emit(value: "Expr") -> "Expr": return Expr("emit", (value,))
    @staticmethod
    def choose(cond: "Expr", yes: "Expr", no: "Expr") -> "Expr": return Expr("if", (cond, yes, no))

    def to_obj(self) -> Any:
        def conv(x: Any) -> Any:
            if isinstance(x, Expr): return x.to_obj()
            return x
        return [self.tag, *[conv(a) for a in self.args]]

    @staticmethod
    def from_obj(obj: Any) -> "Expr":
        if not isinstance(obj, list) or not obj or not isinstance(obj[0], str):
            raise TideMarkError("expression must be a nonempty JSON array")
        tag = obj[0]
        if tag == "var" and len(obj) == 2 and isinstance(obj[1], str): return Expr.var(obj[1])
        if tag == "int" and len(obj) == 2 and isinstance(obj[1], int) and not isinstance(obj[1], bool): return Expr.integer(obj[1])
        if tag == "bool" and len(obj) == 2 and isinstance(obj[1], bool): return Expr.boolean(obj[1])
        if tag == "bin" and len(obj) == 4 and isinstance(obj[1], str): return Expr.binary(obj[1], Expr.from_obj(obj[2]), Expr.from_obj(obj[3]))
        if tag == "not" and len(obj) == 2: return Expr.logical_not(Expr.from_obj(obj[1]))
        if tag == "get" and len(obj) == 2 and isinstance(obj[1], str): return Expr.get(obj[1])
        if tag == "put" and len(obj) == 3 and isinstance(obj[1], str): return Expr.put(obj[1], Expr.from_obj(obj[2]))
        if tag == "emit" and len(obj) == 2: return Expr.emit(Expr.from_obj(obj[1]))
        if tag == "if" and len(obj) == 4: return Expr.choose(Expr.from_obj(obj[1]), Expr.from_obj(obj[2]), Expr.from_obj(obj[3]))
        raise TideMarkError(f"malformed expression tag {tag!r}")


@dataclass(frozen=True)
class Command:
    name: str
    expr: Expr

    def to_obj(self) -> Any: return ["let", self.name, self.expr.to_obj()]

    @staticmethod
    def from_obj(obj: Any) -> "Command":
        if not isinstance(obj, list) or len(obj) != 3 or obj[0] != "let" or not isinstance(obj[1], str) or not obj[1]:
            raise TideMarkError("command must be ['let', name, expression]")
        return Command(obj[1], Expr.from_obj(obj[2]))


@dataclass(frozen=True)
class Program:
    params: tuple[tuple[str, Type], ...]
    regions: tuple[tuple[str, Type], ...]
    commands: tuple[Command, ...]
    result: str

    def to_obj(self) -> dict[str, Any]:
        return {
            "commands": [c.to_obj() for c in self.commands],
            "params": [[n, t.value] for n, t in self.params],
            "regions": [[n, t.value] for n, t in self.regions],
            "result": self.result,
            "schema": "tidemark-ir-3",
        }

    @staticmethod
    def from_obj(obj: Any) -> "Program":
        if not isinstance(obj, dict) or set(obj) != {"schema", "params", "regions", "commands", "result"}:
            raise TideMarkError("program object has unknown or missing fields")
        if obj["schema"] != "tidemark-ir-3": raise TideMarkError("unsupported IR schema")
        def bindings(xs: Any) -> tuple[tuple[str, Type], ...]:
            if not isinstance(xs, list): raise TideMarkError("bindings must be a list")
            out: list[tuple[str, Type]] = []
            seen: set[str] = set()
            for row in xs:
                if not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str) or not row[0]: raise TideMarkError("malformed binding")
                if row[0] in seen: raise TideMarkError("duplicate binding")
                try: typ = Type(row[1])
                except Exception as exc: raise TideMarkError("unknown type") from exc
                seen.add(row[0]); out.append((row[0], typ))
            return tuple(out)
        params = bindings(obj["params"]); regions = bindings(obj["regions"])
        if not isinstance(obj["commands"], list): raise TideMarkError("commands must be a list")
        commands = tuple(Command.from_obj(x) for x in obj["commands"])
        if not isinstance(obj["result"], str) or not obj["result"]: raise TideMarkError("result must be a nonempty string")
        return Program(params, regions, commands, obj["result"])


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def serialize_program(program: Program) -> bytes:
    return canonical_json(program.to_obj())


def parse_program(data: bytes | str) -> Program:
    if isinstance(data, str): data = data.encode("utf-8")
    try:
        text = data.decode("utf-8")
        obj = json.loads(text)
    except Exception as exc:
        raise TideMarkError("invalid UTF-8 JSON program") from exc
    program = Program.from_obj(obj)
    if canonical_json(obj) != data:
        raise TideMarkError("program encoding is not canonical")
    return program


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expr_free_vars(expr: Expr) -> frozenset[str]:
    tag, a = expr.tag, expr.args
    if tag == "var": return frozenset([a[0]])
    if tag in {"int", "bool", "get"}: return frozenset()
    if tag == "bin": return expr_free_vars(a[1]) | expr_free_vars(a[2])
    if tag in {"not", "emit"}: return expr_free_vars(a[0])
    if tag == "put": return expr_free_vars(a[1])
    if tag == "if": return expr_free_vars(a[0]) | expr_free_vars(a[1]) | expr_free_vars(a[2])
    raise TideMarkError(f"unknown expression {tag}")


def infer_expr(expr: Expr, env: Mapping[str, Type], regions: Mapping[str, Type]) -> tuple[Type, Effect]:
    tag, a = expr.tag, expr.args
    if tag == "var":
        if a[0] not in env: raise TideMarkError(f"unbound variable {a[0]}")
        return env[a[0]], Effect()
    if tag == "int": return Type.INT, Effect()
    if tag == "bool": return Type.BOOL, Effect()
    if tag == "get":
        if a[0] not in regions: raise TideMarkError(f"unknown region {a[0]}")
        return regions[a[0]], Effect(reads=frozenset([a[0]]))
    if tag == "not":
        t, e = infer_expr(a[0], env, regions)
        if t != Type.BOOL: raise TideMarkError("not expects Bool")
        return Type.BOOL, e
    if tag == "bin":
        op, l, r = a
        tl, el = infer_expr(l, env, regions); tr, er = infer_expr(r, env, regions)
        eff = el.join(er)
        if op in {"add", "sub", "mul", "lt"}:
            if tl != Type.INT or tr != Type.INT: raise TideMarkError(f"{op} expects Int operands")
            return (Type.BOOL if op == "lt" else Type.INT), eff
        if op == "eq":
            if tl != tr or tl == Type.UNIT: raise TideMarkError("eq expects equal non-Unit types")
            return Type.BOOL, eff
        raise TideMarkError(f"unknown binary operator {op}")
    if tag == "put":
        region, value = a
        if region not in regions: raise TideMarkError(f"unknown region {region}")
        t, e = infer_expr(value, env, regions)
        if t != regions[region]: raise TideMarkError("put type mismatch")
        return Type.UNIT, e.join(Effect(writes=frozenset([region])))
    if tag == "emit":
        t, e = infer_expr(a[0], env, regions)
        if t == Type.UNIT: raise TideMarkError("emit cannot observe Unit")
        return Type.UNIT, e.join(Effect(emits=True))
    if tag == "if":
        tc, ec = infer_expr(a[0], env, regions); ty, ey = infer_expr(a[1], env, regions); tn, en = infer_expr(a[2], env, regions)
        if tc != Type.BOOL or ty != tn: raise TideMarkError("if type mismatch")
        return ty, ec.join(ey).join(en)
    raise TideMarkError(f"unknown expression {tag}")


@dataclass(frozen=True)
class Analysis:
    types_before: tuple[Mapping[str, Type], ...]
    command_types: tuple[Type, ...]
    command_effects: tuple[Effect, ...]
    result_type: Type


def typecheck_program(program: Program) -> Analysis:
    env: dict[str, Type] = dict(program.params)
    regions = dict(program.regions)
    if len(env) != len(program.params) or len(regions) != len(program.regions): raise TideMarkError("duplicate declarations")
    before: list[Mapping[str, Type]] = []
    types: list[Type] = []
    effects: list[Effect] = []
    for command in program.commands:
        if command.name in env: raise TideMarkError(f"duplicate variable {command.name}")
        before.append(dict(env))
        typ, eff = infer_expr(command.expr, env, regions)
        env[command.name] = typ; types.append(typ); effects.append(eff)
    if program.result not in env: raise TideMarkError("result variable is unbound")
    return Analysis(tuple(before), tuple(types), tuple(effects), env[program.result])


def eval_expr(expr: Expr, env: Mapping[str, Any], store: dict[str, Any], trace: list[Any]) -> Any:
    tag, a = expr.tag, expr.args
    if tag == "var": return env[a[0]]
    if tag in {"int", "bool"}: return a[0]
    if tag == "get": return store[a[0]]
    if tag == "not": return not eval_expr(a[0], env, store, trace)
    if tag == "bin":
        op, l, r = a; lv = eval_expr(l, env, store, trace); rv = eval_expr(r, env, store, trace)
        if op == "add": return lv + rv
        if op == "sub": return lv - rv
        if op == "mul": return lv * rv
        if op == "eq": return lv == rv
        if op == "lt": return lv < rv
        raise TideMarkError("unknown operator")
    if tag == "put":
        store[a[0]] = eval_expr(a[1], env, store, trace); return None
    if tag == "emit":
        trace.append(eval_expr(a[0], env, store, trace)); return None
    if tag == "if": return eval_expr(a[1] if eval_expr(a[0], env, store, trace) else a[2], env, store, trace)
    raise TideMarkError("unknown expression")


def _value_has_type(value: Any, typ: Type) -> bool:
    if typ == Type.INT:
        return type(value) is int
    if typ == Type.BOOL:
        return type(value) is bool
    if typ == Type.UNIT:
        return value is None
    return False


def evaluate_program(program: Program, params: Mapping[str, Any], initial_store: Mapping[str, Any]) -> tuple[Any, dict[str, Any], tuple[Any, ...]]:
    analysis = typecheck_program(program)
    env: dict[str, Any] = dict(params); store = dict(initial_store); trace: list[Any] = []
    parameter_types = dict(program.params); region_types = dict(program.regions)
    if set(env) != set(parameter_types):
        raise TideMarkError("parameter domain mismatch")
    if set(store) != set(region_types):
        raise TideMarkError("store domain mismatch")
    for name, typ in parameter_types.items():
        if not _value_has_type(env[name], typ):
            raise TideMarkError(f"parameter {name} has the wrong runtime type")
    for name, typ in region_types.items():
        if not _value_has_type(store[name], typ):
            raise TideMarkError(f"region {name} has the wrong runtime type")
    for index, command in enumerate(program.commands):
        value = eval_expr(command.expr, env, store, trace)
        if not _value_has_type(value, analysis.command_types[index]):
            raise TideMarkError(f"command {command.name} produced the wrong runtime type")
        env[command.name] = value
    for name, typ in region_types.items():
        if not _value_has_type(store[name], typ):
            raise TideMarkError(f"region {name} ended with the wrong runtime type")
    result = env[program.result]
    if not _value_has_type(result, analysis.result_type):
        raise TideMarkError("program result has the wrong runtime type")
    return result, store, tuple(trace)


@dataclass(frozen=True)
class Site:
    family: str
    start: int
    end: int
    orientation0: tuple[Command, ...]
    orientation1: tuple[Command, ...]

    @property
    def descriptor_bytes(self) -> bytes:
        return canonical_json([
            self.family,
            self.start,
            self.end,
            [command.to_obj() for command in self.orientation0],
            [command.to_obj() for command in self.orientation1],
        ])

    @property
    def key(self) -> tuple[Any, ...]:
        # Earliest finishing endpoint is the optimal interval-scheduling key.
        # The remaining components make the maximum schedule unique for a mode.
        return (self.end, self.start, FAMILY_RANK[self.family], self.descriptor_bytes)

    @property
    def footprint(self) -> tuple[int, int]: return self.start, self.end
    def render(self, bit: int) -> tuple[Command, ...]:
        if type(bit) is not int or bit not in (0, 1):
            raise TideMarkError("bit must have exact integer value 0 or 1")
        return self.orientation0 if bit == 0 else self.orientation1


def command_bytes(command: Command) -> bytes: return canonical_json(command.to_obj())


def _identity_atom(expr: Expr, env: Mapping[str, Type], regions: Mapping[str, Type]) -> tuple[Expr, Type] | None:
    """Return the shared mode-4 identity base domain.

    Direct and expanded identity representations are admitted only for pure
    atoms: variables, integer literals, and Boolean literals.  In particular,
    ``get r + 0`` and ``(x + y) + 0`` are not identity carriers.
    """
    if expr.tag not in {"var", "int", "bool"}:
        return None
    typ, effect = infer_expr(expr, env, regions)
    if effect != Effect() or typ not in {Type.INT, Type.BOOL}:
        return None
    return expr, typ


def _operand_site(index: int, command: Command, env: Mapping[str, Type], regions: Mapping[str, Type]) -> Site | None:
    expr = command.expr
    if expr.tag != "bin": return None
    op, left, right = expr.args
    if op not in {"add", "mul", "eq"}: return None
    _, left_effect = infer_expr(left, env, regions)
    _, right_effect = infer_expr(right, env, regions)
    if left_effect != Effect() or right_effect != Effect(): return None
    left_bytes = canonical_json(left.to_obj())
    right_bytes = canonical_json(right.to_obj())
    if left_bytes == right_bytes: return None
    low, high = (left, right) if left_bytes < right_bytes else (right, left)
    orientation0 = Command(command.name, Expr.binary(op, low, high))
    orientation1 = Command(command.name, Expr.binary(op, high, low))
    return Site("operand", index, index, (orientation0,), (orientation1,))


def _identity_site(index: int, command: Command, env: Mapping[str, Type], regions: Mapping[str, Type]) -> Site | None:
    """Recognize either canonical representation of one typed identity carrier."""
    expr = command.expr
    base_info: tuple[Expr, Type] | None = _identity_atom(expr, env, regions)
    if base_info is None and expr.tag == "bin":
        op, left, right = expr.args
        candidate = _identity_atom(left, env, regions)
        if candidate is not None:
            _, typ = candidate
            if op == "add" and typ == Type.INT and right == Expr.integer(0):
                base_info = candidate
            elif op == "eq" and typ == Type.BOOL and right == Expr.boolean(True):
                base_info = candidate
    if base_info is None:
        return None
    base, typ = base_info
    direct = Command(command.name, base)
    expanded = Command(
        command.name,
        Expr.binary("add", base, Expr.integer(0))
        if typ == Type.INT
        else Expr.binary("eq", base, Expr.boolean(True)),
    )
    return Site("identity", index, index, (direct,), (expanded,))


def _adjacent_site(index: int, left: Command, right: Command, analysis: Analysis) -> Site | None:
    if right.name in expr_free_vars(left.expr) or left.name in expr_free_vars(right.expr): return None
    if not analysis.command_effects[index].commutes_with(analysis.command_effects[index + 1]): return None
    left_bytes, right_bytes = command_bytes(left), command_bytes(right)
    if left_bytes == right_bytes: return None
    low = (left, right) if left_bytes < right_bytes else (right, left)
    high = (right, left) if left_bytes < right_bytes else (left, right)
    return Site("adjacent", index, index + 1, low, high)


def discover_candidates(program: Program) -> tuple[Site, ...]:
    """Discover every mode-4 candidate before conflict resolution.

    Identity takes precedence over operand classification at one command.
    That precedence does not suppress a separately legal adjacent interval.
    """
    analysis = typecheck_program(program)
    regions = dict(program.regions)
    sites: list[Site] = []
    for index, command in enumerate(program.commands):
        env = analysis.types_before[index]
        identity = _identity_site(index, command, env, regions)
        if identity is not None:
            sites.append(identity)
        else:
            operand = _operand_site(index, command, env, regions)
            if operand is not None:
                sites.append(operand)
    for index in range(len(program.commands) - 1):
        adjacent = _adjacent_site(index, program.commands[index], program.commands[index + 1], analysis)
        if adjacent is not None:
            sites.append(adjacent)
    return tuple(
        sorted(
            sites,
            key=lambda site: (site.start, site.end, FAMILY_RANK[site.family], site.descriptor_bytes),
        )
    )


def select_sites(candidates: Sequence[Site]) -> tuple[Site, ...]:
    selected: list[Site] = []; last_end = -1
    for site in sorted(candidates, key=lambda s: s.key):
        if site.start > last_end:
            selected.append(site); last_end = site.end
    return tuple(sorted(selected, key=lambda s: (s.start, s.end, s.family)))


def header_width(n: int) -> int:
    if type(n) is not int or n < 0:
        raise TideMarkError("site count must be a nonnegative integer")
    # For n >= 1, bit_length(n) is exactly ceil(log2(n + 1)).
    # This avoids floating-point rounding at large powers of two.
    return n.bit_length()


def payload_capacity(n: int) -> int: return n - header_width(n)


def frame_bits(payload: Sequence[int], n: int) -> tuple[int, ...]:
    if any(type(bit) is not int or bit not in (0, 1) for bit in payload):
        raise TideMarkError("payload is not an exact integer bit sequence")
    h = header_width(n); c = n - h; length = len(payload)
    if length > c: raise TideMarkError(f"payload length {length} exceeds capacity {c}")
    if n == 0:
        if length: raise TideMarkError("nonempty payload for zero capacity")
        return ()
    header = tuple((length >> shift) & 1 for shift in reversed(range(h)))
    return header + tuple(payload) + (0,) * (n - h - length)


def unframe_bits(bits: Sequence[int]) -> tuple[int, ...]:
    n = len(bits); h = header_width(n)
    if any(type(bit) is not int or bit not in (0, 1) for bit in bits):
        raise TideMarkError("frame is not an exact integer bit sequence")
    if n == 0: return ()
    length = 0
    for bit in bits[:h]: length = 2 * length + bit
    c = n - h
    if length > c: raise TideMarkError("frame length exceeds capacity")
    payload = tuple(bits[h:h + length])
    if any(bits[h + length:]): raise TideMarkError("nonzero frame padding")
    return payload


def replay(program: Program, sites: Sequence[Site], bits: Sequence[int]) -> Program:
    if len(sites) != len(bits): raise TideMarkError("site/bit length mismatch")
    commands = list(program.commands)
    for site, bit in sorted(zip(sites, bits), key=lambda x: x[0].start, reverse=True):
        commands[site.start:site.end + 1] = list(site.render(bit))
    target = Program(program.params, program.regions, tuple(commands), program.result)
    typecheck_program(target)
    return target


def decode_site(site: Site, target: Program) -> int:
    fragment = tuple(target.commands[site.start:site.end + 1])
    m0 = fragment == site.orientation0; m1 = fragment == site.orientation1
    if m0 == m1: raise TideMarkError("target fragment does not have a unique carrier orientation")
    return 0 if m0 else 1


def extract_payload(source: Program, target: Program, mode: str = MODE_VERSION) -> tuple[int, ...]:
    if mode != MODE_VERSION: raise TideMarkError("unsupported mode")
    typecheck_program(source); typecheck_program(target)
    sites = select_sites(discover_candidates(source))
    if len(source.commands) != len(target.commands): raise TideMarkError("target length mismatch")
    bits = tuple(decode_site(site, target) for site in sites)
    return unframe_bits(bits)


@dataclass(frozen=True)
class Certificate:
    mode: str
    checker: str
    source_sha256: str
    target_sha256: str
    payload: tuple[int, ...]

    def to_obj(self) -> dict[str, Any]:
        return {
            "checker": self.checker,
            "mode": self.mode,
            "payload": "".join(map(str, self.payload)),
            "schema": SCHEMA,
            "source_sha256": self.source_sha256,
            "target_sha256": self.target_sha256,
        }

    def to_bytes(self) -> bytes: return canonical_json(self.to_obj())

    @staticmethod
    def from_bytes(data: bytes | str) -> "Certificate":
        if isinstance(data, str): data = data.encode("utf-8")
        try: obj = json.loads(data.decode("utf-8"))
        except Exception as exc: raise TideMarkError("invalid certificate JSON") from exc
        expected = {"checker", "mode", "payload", "schema", "source_sha256", "target_sha256"}
        if not isinstance(obj, dict) or set(obj) != expected: raise TideMarkError("certificate has unknown or missing fields")
        if canonical_json(obj) != data: raise TideMarkError("certificate encoding is not canonical")
        if obj["schema"] != SCHEMA: raise TideMarkError("unsupported certificate schema")
        if not isinstance(obj["payload"], str) or any(ch not in "01" for ch in obj["payload"]): raise TideMarkError("invalid payload encoding")
        for field in ("source_sha256", "target_sha256"):
            if not isinstance(obj[field], str) or len(obj[field]) != 64 or any(ch not in "0123456789abcdef" for ch in obj[field]): raise TideMarkError("invalid digest")
        return Certificate(obj["mode"], obj["checker"], obj["source_sha256"], obj["target_sha256"], tuple(int(ch) for ch in obj["payload"]))


def embed(source: Program, payload: Sequence[int], mode: str = MODE_VERSION) -> tuple[Program, Certificate]:
    if mode != MODE_VERSION: raise TideMarkError("unsupported mode")
    typecheck_program(source)
    sites = select_sites(discover_candidates(source)); bits = frame_bits(payload, len(sites)); target = replay(source, sites, bits)
    source_bytes = serialize_program(source); target_bytes = serialize_program(target)
    cert = Certificate(mode, CHECKER_VERSION, digest_bytes(source_bytes), digest_bytes(target_bytes), tuple(payload))
    return target, cert


def check_certificate(source_bytes: bytes, target_bytes: bytes, certificate_bytes: bytes) -> tuple[int, ...]:
    cert = Certificate.from_bytes(certificate_bytes)
    if cert.mode != MODE_VERSION or cert.checker != CHECKER_VERSION: raise TideMarkError("unsupported version")
    if digest_bytes(source_bytes) != cert.source_sha256 or digest_bytes(target_bytes) != cert.target_sha256: raise TideMarkError("digest mismatch")
    source = parse_program(source_bytes); target = parse_program(target_bytes)
    sites = select_sites(discover_candidates(source)); expected = replay(source, sites, frame_bits(cert.payload, len(sites)))
    if serialize_program(expected) != target_bytes: raise TideMarkError("target is not exact canonical replay")
    extracted = extract_payload(source, target, cert.mode)
    if extracted != cert.payload: raise TideMarkError("extractor disagreement")
    return extracted


def optimal_interval_count(candidates: Sequence[Site]) -> int:
    ordered = sorted(candidates, key=lambda s: (s.end, s.start, s.family))
    if not ordered: return 0
    dp = [0] * (len(ordered) + 1)
    for i, site in enumerate(ordered, start=1):
        j = i - 1
        while j > 0 and ordered[j - 1].end >= site.start: j -= 1
        dp[i] = max(dp[i - 1], 1 + dp[j])
    return dp[-1]
