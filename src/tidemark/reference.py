"""Separately written raw-JSON reference checker for TideMark mode 4.

This module intentionally does not import :mod:`tidemark.core`.  It implements
strict parsing, typing, effects, candidate discovery, canonical scheduling,
framing, replay, extraction, and evaluation over plain JSON values.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

SCHEMA = "tidemark-certificate-4"
MODE = "tidemark-mode-4"
CHECKER = "tidemark-checker-4"
IR_SCHEMA = "tidemark-ir-3"
BASE_TYPES = {"Int", "Bool", "Unit"}
FAMILY_RANK = {"identity": 0, "operand": 1, "adjacent": 2}
PURE = (frozenset(), frozenset(), False)


class RefError(ValueError):
    pass


def canon(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse(data: bytes) -> Any:
    try:
        value = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise RefError("invalid UTF-8 JSON") from exc
    if canon(value) != data:
        raise RefError("noncanonical JSON bytes")
    return value


def _binding_map(rows: Any, label: str) -> dict[str, str]:
    if not isinstance(rows, list):
        raise RefError(f"{label} must be a list")
    result: dict[str, str] = {}
    for row in rows:
        if (
            not isinstance(row, list)
            or len(row) != 2
            or not isinstance(row[0], str)
            or not row[0]
            or row[1] not in BASE_TYPES
        ):
            raise RefError(f"malformed {label} declaration")
        if row[0] in result:
            raise RefError(f"duplicate {label} declaration")
        result[row[0]] = row[1]
    return result


def _expect_expr(expr: Any, tag: str, arity: int) -> None:
    if not isinstance(expr, list) or len(expr) != arity + 1 or expr[0] != tag:
        raise RefError(f"malformed {tag} expression")


def infer(expr: Any, env: dict[str, str], regions: dict[str, str]) -> tuple[str, tuple[frozenset[str], frozenset[str], bool]]:
    if not isinstance(expr, list) or not expr or not isinstance(expr[0], str):
        raise RefError("expression must be a nonempty array")
    tag = expr[0]
    if tag == "var":
        _expect_expr(expr, "var", 1)
        if not isinstance(expr[1], str) or not expr[1] or expr[1] not in env:
            raise RefError("unknown variable")
        return env[expr[1]], PURE
    if tag == "int":
        _expect_expr(expr, "int", 1)
        if type(expr[1]) is not int:
            raise RefError("integer literal")
        return "Int", PURE
    if tag == "bool":
        _expect_expr(expr, "bool", 1)
        if type(expr[1]) is not bool:
            raise RefError("Boolean literal")
        return "Bool", PURE
    if tag == "get":
        _expect_expr(expr, "get", 1)
        if not isinstance(expr[1], str) or expr[1] not in regions:
            raise RefError("unknown region")
        return regions[expr[1]], (frozenset({expr[1]}), frozenset(), False)
    if tag == "not":
        _expect_expr(expr, "not", 1)
        typ, effect = infer(expr[1], env, regions)
        if typ != "Bool":
            raise RefError("not expects Bool")
        return "Bool", effect
    if tag == "bin":
        _expect_expr(expr, "bin", 3)
        if not isinstance(expr[1], str):
            raise RefError("binary operator")
        left_type, left_effect = infer(expr[2], env, regions)
        right_type, right_effect = infer(expr[3], env, regions)
        effect = (
            left_effect[0] | right_effect[0],
            left_effect[1] | right_effect[1],
            left_effect[2] or right_effect[2],
        )
        op = expr[1]
        if op in {"add", "sub", "mul", "lt"}:
            if left_type != "Int" or right_type != "Int":
                raise RefError(f"{op} expects Int operands")
            return ("Bool" if op == "lt" else "Int"), effect
        if op == "eq":
            if left_type != right_type or left_type == "Unit":
                raise RefError("eq expects equal non-Unit types")
            return "Bool", effect
        raise RefError("unknown binary operator")
    if tag == "put":
        _expect_expr(expr, "put", 2)
        if not isinstance(expr[1], str) or expr[1] not in regions:
            raise RefError("unknown region")
        value_type, effect = infer(expr[2], env, regions)
        if value_type != regions[expr[1]]:
            raise RefError("put type mismatch")
        return "Unit", (effect[0], effect[1] | {expr[1]}, effect[2])
    if tag == "emit":
        _expect_expr(expr, "emit", 1)
        value_type, effect = infer(expr[1], env, regions)
        if value_type == "Unit":
            raise RefError("emit cannot observe Unit")
        return "Unit", (effect[0], effect[1], True)
    if tag == "if":
        _expect_expr(expr, "if", 3)
        cond_type, cond_effect = infer(expr[1], env, regions)
        yes_type, yes_effect = infer(expr[2], env, regions)
        no_type, no_effect = infer(expr[3], env, regions)
        if cond_type != "Bool" or yes_type != no_type:
            raise RefError("if type mismatch")
        return yes_type, (
            cond_effect[0] | yes_effect[0] | no_effect[0],
            cond_effect[1] | yes_effect[1] | no_effect[1],
            cond_effect[2] or yes_effect[2] or no_effect[2],
        )
    raise RefError("unknown expression tag")


def free_variables(expr: Any) -> set[str]:
    # Calling infer before discovery guarantees shape, but this function remains
    # strict so it is safe when used independently in tests.
    if not isinstance(expr, list) or not expr:
        raise RefError("malformed expression")
    tag = expr[0]
    if tag == "var":
        _expect_expr(expr, "var", 1)
        return {expr[1]}
    if tag in {"int", "bool", "get"}:
        _expect_expr(expr, tag, 1)
        return set()
    if tag == "bin":
        _expect_expr(expr, "bin", 3)
        return free_variables(expr[2]) | free_variables(expr[3])
    if tag in {"not", "emit"}:
        _expect_expr(expr, tag, 1)
        return free_variables(expr[1])
    if tag == "put":
        _expect_expr(expr, "put", 2)
        return free_variables(expr[2])
    if tag == "if":
        _expect_expr(expr, "if", 3)
        return free_variables(expr[1]) | free_variables(expr[2]) | free_variables(expr[3])
    raise RefError("unknown expression tag")


def analyze(program: Any) -> tuple[list[dict[str, str]], list[tuple[frozenset[str], frozenset[str], bool]], list[str], str]:
    if not isinstance(program, dict) or set(program) != {"schema", "params", "regions", "commands", "result"}:
        raise RefError("program object has unknown or missing fields")
    if program["schema"] != IR_SCHEMA:
        raise RefError("unsupported IR schema")
    env = _binding_map(program["params"], "parameter")
    regions = _binding_map(program["regions"], "region")
    if not isinstance(program["commands"], list):
        raise RefError("commands must be a list")
    before: list[dict[str, str]] = []
    effects: list[tuple[frozenset[str], frozenset[str], bool]] = []
    command_types: list[str] = []
    for command in program["commands"]:
        if (
            not isinstance(command, list)
            or len(command) != 3
            or command[0] != "let"
            or not isinstance(command[1], str)
            or not command[1]
        ):
            raise RefError("malformed command")
        if command[1] in env:
            raise RefError("duplicate variable")
        before.append(dict(env))
        typ, effect = infer(command[2], env, regions)
        env[command[1]] = typ
        command_types.append(typ)
        effects.append(effect)
    if not isinstance(program["result"], str) or program["result"] not in env:
        raise RefError("result variable is unbound")
    return before, effects, command_types, env[program["result"]]


def commute(left: tuple[frozenset[str], frozenset[str], bool], right: tuple[frozenset[str], frozenset[str], bool]) -> bool:
    left_reads, left_writes, left_emits = left
    right_reads, right_writes, right_emits = right
    return not (left_emits and right_emits) and not (
        left_writes & (right_reads | right_writes)
        or right_writes & (left_reads | left_writes)
    )


def _identity_atom(expr: Any, env: dict[str, str], regions: dict[str, str]) -> tuple[Any, str] | None:
    if not isinstance(expr, list) or not expr or expr[0] not in {"var", "int", "bool"}:
        return None
    typ, effect = infer(expr, env, regions)
    if effect != PURE or typ not in {"Int", "Bool"}:
        return None
    return expr, typ


def _site_descriptor(site: tuple[Any, ...]) -> bytes:
    return canon([site[0], site[1], site[2], site[3], site[4]])


def candidates(program: Any) -> list[tuple[Any, ...]]:
    before, effects, _, _ = analyze(program)
    regions = {name: typ for name, typ in program["regions"]}
    commands = program["commands"]
    result: list[tuple[Any, ...]] = []
    for index, command in enumerate(commands):
        expr = command[2]
        identity: tuple[Any, ...] | None = None
        base_info = _identity_atom(expr, before[index], regions)
        if base_info is None and expr[0] == "bin":
            op, left, right = expr[1], expr[2], expr[3]
            candidate = _identity_atom(left, before[index], regions)
            if candidate is not None:
                _, typ = candidate
                if op == "add" and typ == "Int" and right == ["int", 0]:
                    base_info = candidate
                elif op == "eq" and typ == "Bool" and right == ["bool", True]:
                    base_info = candidate
        if base_info is not None:
            base, typ = base_info
            direct = ["let", command[1], base]
            expanded = [
                "let",
                command[1],
                ["bin", "add", base, ["int", 0]]
                if typ == "Int"
                else ["bin", "eq", base, ["bool", True]],
            ]
            identity = ("identity", index, index, [direct], [expanded])
            result.append(identity)
        elif expr[0] == "bin" and expr[1] in {"add", "mul", "eq"}:
            _, left_effect = infer(expr[2], before[index], regions)
            _, right_effect = infer(expr[3], before[index], regions)
            if left_effect == PURE and right_effect == PURE and canon(expr[2]) != canon(expr[3]):
                low, high = (expr[2], expr[3]) if canon(expr[2]) < canon(expr[3]) else (expr[3], expr[2])
                result.append((
                    "operand",
                    index,
                    index,
                    [["let", command[1], ["bin", expr[1], low, high]]],
                    [["let", command[1], ["bin", expr[1], high, low]]],
                ))
    for index in range(len(commands) - 1):
        left, right = commands[index], commands[index + 1]
        if right[1] in free_variables(left[2]) or left[1] in free_variables(right[2]):
            continue
        if not commute(effects[index], effects[index + 1]):
            continue
        if canon(left) == canon(right):
            continue
        low = (left, right) if canon(left) < canon(right) else (right, left)
        high = (right, left) if canon(left) < canon(right) else (left, right)
        result.append(("adjacent", index, index + 1, list(low), list(high)))
    return sorted(
        result,
        key=lambda site: (site[1], site[2], FAMILY_RANK[site[0]], _site_descriptor(site)),
    )


def select(sites: Iterable[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    selected: list[tuple[Any, ...]] = []
    last_end = -1
    for site in sorted(
        sites,
        key=lambda value: (value[2], value[1], FAMILY_RANK[value[0]], _site_descriptor(value)),
    ):
        if site[1] > last_end:
            selected.append(site)
            last_end = site[2]
    return sorted(
        selected,
        key=lambda value: (value[1], value[2], FAMILY_RANK[value[0]], _site_descriptor(value)),
    )


def header_width(site_count: int) -> int:
    if type(site_count) is not int or site_count < 0:
        raise RefError("site count")
    return site_count.bit_length()


def frame(payload: list[int], site_count: int) -> list[int]:
    if any(type(bit) is not int or bit not in (0, 1) for bit in payload):
        raise RefError("payload")
    width = header_width(site_count)
    capacity = site_count - width
    if len(payload) > capacity:
        raise RefError("capacity")
    if site_count == 0:
        return []
    return [((len(payload) >> shift) & 1) for shift in reversed(range(width))] + payload + [0] * (site_count - width - len(payload))


def unframe(bits: list[int]) -> list[int]:
    if any(type(bit) is not int or bit not in (0, 1) for bit in bits):
        raise RefError("frame bits")
    site_count = len(bits)
    width = header_width(site_count)
    if site_count == 0:
        return []
    length = 0
    for bit in bits[:width]:
        length = 2 * length + bit
    if length > site_count - width or any(bits[width + length :]):
        raise RefError("invalid frame")
    return bits[width : width + length]


def replay(program: Any, sites: list[tuple[Any, ...]], bits: list[int]) -> Any:
    if len(sites) != len(bits):
        raise RefError("site/bit length mismatch")
    target = json.loads(json.dumps(program))
    commands = target["commands"]
    for site, bit in sorted(zip(sites, bits), key=lambda pair: pair[0][1], reverse=True):
        if type(bit) is not int or bit not in (0, 1):
            raise RefError("orientation bit")
        commands[site[1] : site[2] + 1] = site[3 + bit]
    analyze(target)
    return target


def extract(source: Any, target: Any) -> list[int]:
    analyze(source)
    analyze(target)
    sites = select(candidates(source))
    if len(source["commands"]) != len(target["commands"]):
        raise RefError("target length mismatch")
    bits: list[int] = []
    for site in sites:
        fragment = target["commands"][site[1] : site[2] + 1]
        match0 = fragment == site[3]
        match1 = fragment == site[4]
        if match0 == match1:
            raise RefError("non-unique orientation")
        bits.append(0 if match0 else 1)
    return unframe(bits)


def check(source: bytes, target: bytes, certificate: bytes) -> tuple[int, ...]:
    cert = parse(certificate)
    expected_fields = {"schema", "checker", "mode", "source_sha256", "target_sha256", "payload"}
    if not isinstance(cert, dict) or set(cert) != expected_fields:
        raise RefError("certificate fields")
    if cert["schema"] != SCHEMA or cert["mode"] != MODE or cert["checker"] != CHECKER:
        raise RefError("unsupported version")
    if sha(source) != cert["source_sha256"] or sha(target) != cert["target_sha256"]:
        raise RefError("digest mismatch")
    if not isinstance(cert["payload"], str) or any(char not in "01" for char in cert["payload"]):
        raise RefError("payload")
    source_obj = parse(source)
    target_obj = parse(target)
    payload = [int(char) for char in cert["payload"]]
    sites = select(candidates(source_obj))
    expected_target = replay(source_obj, sites, frame(payload, len(sites)))
    if canon(expected_target) != target:
        raise RefError("target differs from exact replay")
    recovered = extract(source_obj, target_obj)
    if recovered != payload:
        raise RefError("extractor disagreement")
    return tuple(recovered)


def _eval_expr(expr: Any, env: dict[str, Any], store: dict[str, Any], trace: list[Any]) -> Any:
    tag = expr[0]
    if tag == "var": return env[expr[1]]
    if tag in {"int", "bool"}: return expr[1]
    if tag == "get": return store[expr[1]]
    if tag == "not": return not _eval_expr(expr[1], env, store, trace)
    if tag == "bin":
        left = _eval_expr(expr[2], env, store, trace)
        right = _eval_expr(expr[3], env, store, trace)
        op = expr[1]
        if op == "add": return left + right
        if op == "sub": return left - right
        if op == "mul": return left * right
        if op == "eq": return left == right
        if op == "lt": return left < right
        raise RefError("unknown operator")
    if tag == "put":
        store[expr[1]] = _eval_expr(expr[2], env, store, trace)
        return None
    if tag == "emit":
        trace.append(_eval_expr(expr[1], env, store, trace))
        return None
    if tag == "if":
        branch = expr[2] if _eval_expr(expr[1], env, store, trace) else expr[3]
        return _eval_expr(branch, env, store, trace)
    raise RefError("evaluation")


def _runtime_type_ok(value: Any, typ: str) -> bool:
    return (
        (typ == "Int" and type(value) is int)
        or (typ == "Bool" and type(value) is bool)
        or (typ == "Unit" and value is None)
    )


def evaluate(program: Any, params: dict[str, Any], initial_store: dict[str, Any]) -> tuple[Any, dict[str, Any], tuple[Any, ...]]:
    before, _, command_types, result_type = analyze(program)
    env = dict(params)
    store = dict(initial_store)
    trace: list[Any] = []
    param_types = _binding_map(program["params"], "parameter")
    region_types = _binding_map(program["regions"], "region")
    if set(env) != set(param_types) or set(store) != set(region_types):
        raise RefError("runtime domain")
    if any(not _runtime_type_ok(env[name], typ) for name, typ in param_types.items()):
        raise RefError("parameter type")
    if any(not _runtime_type_ok(store[name], typ) for name, typ in region_types.items()):
        raise RefError("store type")
    for index, command in enumerate(program["commands"]):
        value = _eval_expr(command[2], env, store, trace)
        if not _runtime_type_ok(value, command_types[index]):
            raise RefError("command result type")
        env[command[1]] = value
    if any(not _runtime_type_ok(store[name], typ) for name, typ in region_types.items()):
        raise RefError("final store type")
    result = env[program["result"]]
    if not _runtime_type_ok(result, result_type):
        raise RefError("result type")
    return result, store, tuple(trace)
