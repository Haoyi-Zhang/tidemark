"""Owned overlap-bearing IR comparison, separate from the quota corpus.

Baselines share Mode-4's typed carrier equations, serializer and frame, but
have explicit source-only selection policies. Their certificates are a separate
schema: they are not accepted Mode-4 certificates. No LLVM execution occurs.
"""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Sequence

from . import core, reference

POLICIES = ("mode4", "source-first", "singleton-first", "adjacent-only")
FAMILIES = ("identity-run", "operand-run", "adjacent-chain", "state-trace")
SIZES = (8, 16, 32, 64)
VARIANTS = tuple(range(12))
SCHEMA = "tidemark-selector-comparison-1"
STATES = tuple(
    ({"a": a, "b": b, "flag": flag}, {"r": r, "s": s})
    for a, b, flag, r, s in (
        (-3, 2, False, -1, 4), (0, 0, True, 0, 0),
        (2, -5, False, 7, -2), (9, 3, True, -8, 6),
        (-11, -1, True, 4, 4), (1, 8, False, 3, -7),
    )
)


def sources():
    """192 fixed grammar constructions; no capacity quotas or seed search.

    A dependent subtraction suffix consumes every non-Unit generated value.
    Store updates and emissions are visible in the complete observation.
    The twelve variants change renaming, operand order and dependence/effects.
    """
    E, C, T = core.Expr, core.Command, core.Type
    a, b, flag = E.var("a"), E.var("b"), E.var("flag")
    for family in FAMILIES:
        for size in SIZES:
            for variant in VARIANTS:
                commands, values = [], []
                for i in range(size):
                    name = f"v{variant:02d}_{size - i:03d}"
                    # Dependence decisions precede discovery; only Int results
                    # enter the later arithmetic of this construction.
                    left = (E.var(values[-1][0]) if values and
                            values[-1][1] == T.INT and (i + variant) % 4 == 1
                            else a)
                    typ = T.INT
                    if family == "identity-run":
                        base = flag if (i + variant) % 3 == 0 else left
                        typ = T.BOOL if base == flag else T.INT
                        neutral = E.boolean(True) if typ == T.BOOL else E.integer(0)
                        op = "eq" if typ == T.BOOL else "add"
                        expr = E.binary(op, base, neutral) if (i + variant) % 2 else base
                    elif family == "operand-run":
                        op = ("add", "mul", "eq")[(i + variant) % 3]
                        l, r = (left, b) if (i + variant) % 2 else (b, left)
                        expr = E.binary(op, l, r)
                        typ = T.BOOL if op == "eq" else T.INT
                    elif family == "adjacent-chain":
                        expr = E.binary("sub", left, E.integer(i + variant + 1))
                    else:
                        shape = (i + variant) % 8
                        if shape == 0:
                            expr, typ = E.put("r", left), T.UNIT
                        elif shape == 1:
                            expr = E.get("r" if variant % 2 else "s")
                        elif shape in (2, 3):
                            expr, typ = E.emit(left if shape == 2 else b), T.UNIT
                        elif shape == 4:
                            expr = left
                        elif shape == 5:
                            expr = E.binary("mul", left, b)
                        elif shape == 6:
                            expr = E.choose(flag, E.get("r"), E.get("s"))
                        else:
                            expr = E.binary("sub", left, b)
                    commands.append(C(name, expr))
                    if typ != T.UNIT:
                        values.append((name, typ))
                accumulator = "a"
                for j, (name, typ) in enumerate(values):
                    term = E.var(name) if typ == T.INT else E.choose(
                        E.var(name), E.integer(1), E.integer(0))
                    dest = f"out{j:03d}"
                    commands.append(C(dest, E.binary("sub", E.var(accumulator), term)))
                    accumulator = dest
                source = core.Program(
                    (("a", T.INT), ("b", T.INT), ("flag", T.BOOL)),
                    (("r", T.INT), ("s", T.INT)), tuple(commands), accumulator)
                yield f"{family}-{size}-{variant:02d}", family, size, variant, source


def select(candidates: Sequence[core.Site], policy: str) -> tuple[core.Site, ...]:
    if policy not in POLICIES:
        raise core.TideMarkError("unsupported comparison policy")
    if policy == "mode4":
        return core.select_sites(candidates)
    if policy == "adjacent-only":
        return core.select_sites([s for s in candidates if s.family == "adjacent"])
    if policy == "source-first":
        # A one-pass scan, considering a legal adjacent exchange before a
        # singleton beginning at the same source command.
        ordered = sorted(candidates, key=lambda s: (
            s.start, -s.end, core.FAMILY_RANK[s.family], s.descriptor_bytes))
    else:
        # Take all legal singleton rewrites first; fill remaining gaps with
        # earliest-finishing adjacent exchanges.
        ordered = sorted(candidates, key=lambda s: (s.end - s.start, *s.key))
    selected = []
    for site in ordered:
        if all(site.end < old.start or old.end < site.start for old in selected):
            selected.append(site)
    return tuple(sorted(selected, key=lambda s: (s.start, s.end, s.family)))


def reference_select(candidates, policy):
    """Raw-tree policy implementation with a command-coordinate occupancy set."""
    if policy not in POLICIES:
        raise reference.RefError("comparison policy")
    if policy == "mode4":
        return reference.select(candidates)
    rank = {"identity": 0, "operand": 1, "adjacent": 2}
    if policy == "adjacent-only":
        ordered = sorted((s for s in candidates if s[0] == "adjacent"),
                         key=lambda s: (s[2], s[1], rank[s[0]], reference.canon(s)))
    elif policy == "source-first":
        ordered = sorted(candidates, key=lambda s: (
            s[1], -s[2], rank[s[0]], reference.canon(s)))
    else:
        singles = sorted((s for s in candidates if s[1] == s[2]),
                         key=lambda s: (s[2], s[1], rank[s[0]], reference.canon(s)))
        pairs = sorted((s for s in candidates if s[1] != s[2]),
                       key=lambda s: (s[2], s[1], rank[s[0]], reference.canon(s)))
        ordered = singles + pairs
    used, result = set(), []
    for site in ordered:
        coords = set(range(site[1], site[2] + 1))
        if not used.intersection(coords):
            result.append(site)
            used.update(coords)
    return sorted(result, key=lambda s: (s[1], s[2], s[0]))


def optimum_count(candidates, commands: int) -> int:
    """Coordinate DP, unlike the sorted-interval production/reference selectors."""
    endings = [[] for _ in range(commands)]
    for family, start, end, *_ in candidates:
        if not 0 <= start <= end < commands:
            raise ValueError("interval outside source")
        endings[end].append(start)
    best = [0] * (commands + 1)
    for end in range(commands):
        best[end + 1] = max([best[end]] + [best[start] + 1 for start in endings[end]])
    return best[-1]


def extract(source: core.Program, target: core.Program, policy: str):
    if policy == "mode4":
        return core.extract_payload(source, target)
    core.typecheck_program(source)
    core.typecheck_program(target)
    if (source.params, source.regions, len(source.commands)) != (
            target.params, target.regions, len(target.commands)):
        raise core.TideMarkError("comparison target interface or length")
    sites = select(core.discover_candidates(source), policy)
    return core.unframe_bits(tuple(core.decode_site(s, target) for s in sites))


def embed(source, payload, policy):
    if policy == "mode4":
        target, cert = core.embed(source, payload)
        return target, cert.to_bytes()
    sites = select(core.discover_candidates(source), policy)
    target = core.replay(source, sites, core.frame_bits(payload, len(sites)))
    return target, core.canonical_json({
        "schema": SCHEMA, "policy": policy, "mode": core.MODE_VERSION,
        "source_sha256": core.digest_bytes(core.serialize_program(source)),
        "target_sha256": core.digest_bytes(core.serialize_program(target)),
        "payload": "".join(map(str, payload)),
    })


def check(source_bytes, target_bytes, cert_bytes, policy):
    if policy == "mode4":
        return core.check_certificate(source_bytes, target_bytes, cert_bytes)
    if policy not in POLICIES:
        raise core.TideMarkError("unsupported comparison policy")
    cert = reference.parse(cert_bytes)
    if (set(cert) != {"schema", "policy", "mode", "source_sha256", "target_sha256", "payload"}
            or cert["schema"] != SCHEMA or cert["policy"] != policy
            or cert["mode"] != core.MODE_VERSION):
        raise core.TideMarkError("comparison certificate schema or version")
    if (cert["source_sha256"] != core.digest_bytes(source_bytes)
            or cert["target_sha256"] != core.digest_bytes(target_bytes)):
        raise core.TideMarkError("comparison digest mismatch")
    if not isinstance(cert["payload"], str) or any(b not in "01" for b in cert["payload"]):
        raise core.TideMarkError("comparison payload encoding")
    payload = tuple(int(b) for b in cert["payload"])
    source, target = core.parse_program(source_bytes), core.parse_program(target_bytes)
    core.typecheck_program(target)
    sites = select(core.discover_candidates(source), policy)
    expected = core.replay(source, sites, core.frame_bits(payload, len(sites)))
    if core.serialize_program(expected) != target_bytes:
        raise core.TideMarkError("comparison target is not exact replay")
    recovered = extract(source, target, policy)
    if recovered != payload:
        raise core.TideMarkError("comparison extractor disagreement")
    return recovered


def reference_check(source_bytes, target_bytes, cert_bytes, policy):
    if policy == "mode4":
        return reference.check(source_bytes, target_bytes, cert_bytes)
    if policy not in POLICIES:
        raise reference.RefError("comparison policy")
    cert = reference.parse(cert_bytes)
    if (set(cert) != {"schema", "policy", "mode", "source_sha256", "target_sha256", "payload"}
            or cert["schema"] != SCHEMA or cert["policy"] != policy
            or cert["mode"] != reference.MODE):
        raise reference.RefError("comparison schema or version")
    if cert["source_sha256"] != reference.sha(source_bytes) or cert["target_sha256"] != reference.sha(target_bytes):
        raise reference.RefError("comparison digest")
    if not isinstance(cert["payload"], str) or any(b not in "01" for b in cert["payload"]):
        raise reference.RefError("comparison payload")
    source, target = reference.parse(source_bytes), reference.parse(target_bytes)
    reference.analyze(target)
    sites = reference_select(reference.candidates(source), policy)
    payload = [int(b) for b in cert["payload"]]
    expected = reference.replay(source, sites, reference.frame(payload, len(sites)))
    if reference.canon(expected) != target_bytes:
        raise reference.RefError("comparison replay")
    recovered_bits = []
    for site in sites:
        fragment = target["commands"][site[1]:site[2] + 1]
        if (fragment == site[3]) == (fragment == site[4]):
            raise reference.RefError("comparison orientation")
        recovered_bits.append(0 if fragment == site[3] else 1)
    recovered = reference.unframe(recovered_bits)
    if recovered != payload:
        raise reference.RefError("comparison extraction")
    return tuple(recovered)


def mutations(target, cert_bytes):
    """Two isolated mutations; changed target is rehashed, still not replay."""
    changed = replace(target, result="b")
    changed_bytes = core.serialize_program(changed)
    cert = json.loads(cert_bytes)
    cert["target_sha256"] = core.digest_bytes(changed_bytes)
    yield "rehashed-return", changed_bytes, core.canonical_json(cert)
    cert = json.loads(cert_bytes)
    bits = cert["payload"]
    cert["payload"] = (("1" if bits[0] == "0" else "0") + bits[1:]) if bits else "1"
    yield "payload", core.serialize_program(target), core.canonical_json(cert)
