"""Finite structural replay traces for TideMark mode 4.

The production trace builder uses :mod:`tidemark.core`.  A second producer and
the verifier use :mod:`tidemark.reference`, which is separately written from the
production implementation.  This module is *not* an independent proof kernel:
it reuses the reference analyzer, discovery, selection, framing, replay, and
extraction functions.  Its purpose is to materialize and check the finite
replay trace consumed for each measured instance.
"""
from __future__ import annotations

import hashlib
import copy
from dataclasses import dataclass
from typing import Any, Sequence

from . import reference
from .core import (
    Program,
    canonical_json,
    discover_candidates,
    frame_bits,
    replay,
    select_sites,
    serialize_program,
    typecheck_program,
)

STEP_FIELDS = ("family", "interval", "bit", "before_sha256", "after_sha256")


@dataclass(frozen=True)
class Derivation:
    source_hash: str
    target_hash: str
    selected: tuple[tuple[str, int, int], ...]
    framed_bits: tuple[int, ...]
    steps: tuple[dict[str, Any], ...]

    def to_obj(self) -> dict[str, Any]:
        return {
            "source_hash": self.source_hash,
            "target_hash": self.target_hash,
            "selected": [list(item) for item in self.selected],
            "framed_bits": list(self.framed_bits),
            # Mutation campaigns need an independent object for each case.
            "steps": copy.deepcopy(list(self.steps)),
        }

    def to_bytes(self) -> bytes:
        return canonical_json(self.to_obj())

    @staticmethod
    def from_obj(obj: Any) -> "Derivation":
        if not isinstance(obj, dict) or set(obj) != {
            "source_hash", "target_hash", "selected", "framed_bits", "steps"
        }:
            raise ValueError("derivation root fields")
        if not isinstance(obj["selected"], list) or not isinstance(obj["framed_bits"], list) or not isinstance(obj["steps"], list):
            raise ValueError("derivation root shapes")
        return Derivation(
            obj["source_hash"],
            obj["target_hash"],
            tuple(tuple(item) for item in obj["selected"]),
            tuple(obj["framed_bits"]),
            tuple(copy.deepcopy(obj["steps"])),
        )


def _hash_fragment(fragment: Any) -> str:
    return hashlib.sha256(canonical_json(fragment)).hexdigest()


def _production_step(source: Program, site: Any, bit: int) -> dict[str, Any]:
    before = [command.to_obj() for command in source.commands[site.start : site.end + 1]]
    after = [command.to_obj() for command in site.render(bit)]
    return {
        "family": site.family,
        "interval": [site.start, site.end],
        "bit": bit,
        "before_sha256": _hash_fragment(before),
        "after_sha256": _hash_fragment(after),
    }


def _reference_step(source_obj: Any, site: tuple[Any, ...], bit: int) -> dict[str, Any]:
    before = source_obj["commands"][site[1] : site[2] + 1]
    after = site[3 + bit]
    return {
        "family": site[0],
        "interval": [site[1], site[2]],
        "bit": bit,
        "before_sha256": _hash_fragment(before),
        "after_sha256": _hash_fragment(after),
    }


def build_derivation(source: Program, payload: Sequence[int]) -> tuple[Program, Derivation]:
    """Build a trace from the production typed-tree representation."""
    typecheck_program(source)
    sites = select_sites(discover_candidates(source))
    bits = frame_bits(payload, len(sites))
    target = replay(source, sites, bits)
    steps = tuple(_production_step(source, site, bit) for site, bit in zip(sites, bits))
    derivation = Derivation(
        hashlib.sha256(serialize_program(source)).hexdigest(),
        hashlib.sha256(serialize_program(target)).hexdigest(),
        tuple((site.family, site.start, site.end) for site in sites),
        tuple(bits),
        steps,
    )
    return target, derivation


def build_reference_derivation(source: Program, payload: Sequence[int]) -> tuple[Program, Derivation]:
    """Build the same finite trace through the raw-tree reference model."""
    source_obj = source.to_obj()
    reference.analyze(source_obj)
    sites = reference.select(reference.candidates(source_obj))
    bits = reference.frame(list(payload), len(sites))
    target_obj = reference.replay(source_obj, sites, bits)
    target = Program.from_obj(target_obj)
    steps = tuple(_reference_step(source_obj, site, bit) for site, bit in zip(sites, bits))
    derivation = Derivation(
        hashlib.sha256(reference.canon(source_obj)).hexdigest(),
        hashlib.sha256(reference.canon(target_obj)).hexdigest(),
        tuple((site[0], site[1], site[2]) for site in sites),
        tuple(bits),
        steps,
    )
    return target, derivation


def verify_derivation_detailed(
    source: Program,
    target: Program,
    derivation: Derivation,
    payload: Sequence[int],
) -> tuple[bool, str]:
    """Return a verdict and the first failed structural condition."""
    try:
        source_obj = source.to_obj()
        target_obj = target.to_obj()
        source_bytes = reference.canon(source_obj)
        target_bytes = reference.canon(target_obj)
        if hashlib.sha256(source_bytes).hexdigest() != derivation.source_hash:
            return False, "source_hash"
        if hashlib.sha256(target_bytes).hexdigest() != derivation.target_hash:
            return False, "target_hash"
        try:
            reference.analyze(source_obj)
        except Exception:
            return False, "source_analysis"
        try:
            reference.analyze(target_obj)
        except Exception:
            return False, "target_analysis"
        sites = reference.select(reference.candidates(source_obj))
        bits = tuple(reference.frame(list(payload), len(sites)))
        selected = tuple((site[0], site[1], site[2]) for site in sites)
        # JSON distinguishes integer coordinates/bits from Boolean and float
        # values; Python equality alone treats False == 0 == 0.0.
        if reference.canon(derivation.selected) != reference.canon(selected):
            return False, "selected"
        if reference.canon(derivation.framed_bits) != reference.canon(bits):
            return False, "framed_bits"
        if len(derivation.steps) != len(sites):
            return False, "step_count"
        for ordinal, (row, site, bit) in enumerate(zip(derivation.steps, sites, bits)):
            if not isinstance(row, dict) or set(row) != set(STEP_FIELDS):
                return False, f"step[{ordinal}].schema"
            expected = _reference_step(source_obj, site, bit)
            for field in STEP_FIELDS:
                if reference.canon(row.get(field)) != reference.canon(expected[field]):
                    return False, f"step[{ordinal}].{field}"
        expected_target = reference.replay(source_obj, sites, list(bits))
        if reference.canon(expected_target) != target_bytes:
            return False, "exact_replay"
        if tuple(reference.extract(source_obj, target_obj)) != tuple(payload):
            return False, "extract"
        return True, "accepted"
    except Exception as exc:
        return False, f"exception:{type(exc).__name__}:{exc}"


def verify_derivation(
    source: Program,
    target: Program,
    derivation: Derivation,
    payload: Sequence[int],
) -> bool:
    """Compatibility wrapper returning only the structural verdict."""
    return verify_derivation_detailed(source, target, derivation, payload)[0]
