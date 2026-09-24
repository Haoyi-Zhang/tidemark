"""Explicit finite replay derivations with two independent producers.

The production-tree producer uses :mod:`tidemark.core`.  The raw-tree producer
uses :mod:`tidemark.reference`, which does not import production code.  The
verifier follows the raw-tree path, so it does not call production discovery,
selection, framing, replay, extraction, or evaluation.
"""
from __future__ import annotations

import hashlib
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
            "steps": list(self.steps),
        }

    def to_bytes(self) -> bytes:
        return canonical_json(self.to_obj())


def _orientation_hash(fragment: Any) -> str:
    return hashlib.sha256(canonical_json(fragment)).hexdigest()


def build_derivation(source: Program, payload: Sequence[int]) -> tuple[Program, Derivation]:
    """Build a derivation from the production typed-tree representation."""
    typecheck_program(source)
    sites = select_sites(discover_candidates(source))
    bits = frame_bits(payload, len(sites))
    target = replay(source, sites, bits)
    steps = tuple(
        {
            "family": site.family,
            "start": site.start,
            "end": site.end,
            "bit": bit,
            "orientation_hash": _orientation_hash([command.to_obj() for command in site.render(bit)]),
        }
        for site, bit in zip(sites, bits)
    )
    derivation = Derivation(
        hashlib.sha256(serialize_program(source)).hexdigest(),
        hashlib.sha256(serialize_program(target)).hexdigest(),
        tuple((site.family, site.start, site.end) for site in sites),
        tuple(bits),
        steps,
    )
    return target, derivation


def build_reference_derivation(source: Program, payload: Sequence[int]) -> tuple[Program, Derivation]:
    """Build the same derivation through the separately written raw-tree model."""
    source_obj = source.to_obj()
    reference.analyze(source_obj)
    sites = reference.select(reference.candidates(source_obj))
    bits = reference.frame(list(payload), len(sites))
    target_obj = reference.replay(source_obj, sites, bits)
    target = Program.from_obj(target_obj)
    steps = tuple(
        {
            "family": site[0],
            "start": site[1],
            "end": site[2],
            "bit": bit,
            "orientation_hash": _orientation_hash(site[3 + bit]),
        }
        for site, bit in zip(sites, bits)
    )
    derivation = Derivation(
        hashlib.sha256(canonical_json(source_obj)).hexdigest(),
        hashlib.sha256(canonical_json(target_obj)).hexdigest(),
        tuple((site[0], site[1], site[2]) for site in sites),
        tuple(bits),
        steps,
    )
    return target, derivation


def verify_derivation(
    source: Program,
    target: Program,
    derivation: Derivation,
    payload: Sequence[int],
) -> bool:
    """Verify a derivation through the raw-tree representation only."""
    try:
        source_obj = source.to_obj()
        target_obj = target.to_obj()
        source_bytes = canonical_json(source_obj)
        target_bytes = canonical_json(target_obj)
        if hashlib.sha256(source_bytes).hexdigest() != derivation.source_hash:
            return False
        if hashlib.sha256(target_bytes).hexdigest() != derivation.target_hash:
            return False
        reference.analyze(source_obj)
        reference.analyze(target_obj)
        sites = reference.select(reference.candidates(source_obj))
        bits = tuple(reference.frame(list(payload), len(sites)))
        selected = tuple((site[0], site[1], site[2]) for site in sites)
        if derivation.selected != selected or derivation.framed_bits != bits:
            return False
        if len(derivation.steps) != len(sites):
            return False
        for row, site, bit in zip(derivation.steps, sites, bits):
            expected = {
                "family": site[0],
                "start": site[1],
                "end": site[2],
                "bit": bit,
                "orientation_hash": _orientation_hash(site[3 + bit]),
            }
            if row != expected:
                return False
        expected_target = reference.replay(source_obj, sites, list(bits))
        if canonical_json(expected_target) != target_bytes:
            return False
        if tuple(reference.extract(source_obj, target_obj)) != tuple(payload):
            return False
        return True
    except Exception:
        return False
