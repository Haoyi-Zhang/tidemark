"""Read-only LLVM opportunity projection used by the external-corpus audit.

The adapter deliberately recognizes only a conservative textual subset.  It is
not a semantic refinement of LLVM: poison, undef, memory, calls, exceptional
control flow, metadata, and target-specific behavior remain outside the paper's
small-language theorem.  Candidate coordinates are closed instruction
intervals and use the same earliest-finish selection and self-delimiting frame
accounting as the core implementation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Instruction:
    ordinal: int
    block: int
    text: str
    result: str | None
    opcode: str
    rhs: str
    uses: frozenset[str]


@dataclass(frozen=True)
class LLVMSite:
    family: str
    start: int
    end: int

    @property
    def key(self) -> tuple[int, int, int]:
        rank = {"operand": 0, "identity": 1, "adjacent": 2}
        return (self.end, self.start, rank[self.family])


@dataclass(frozen=True)
class Projection:
    instructions: int
    operand_sites: int
    identity_sites: int
    adjacent_sites: int
    selected_sites: int
    payload_bits: int
    operand_only_payload_bits: int
    identity_only_payload_bits: int
    adjacent_only_payload_bits: int


# Result-producing, side-effect-free instructions for which direct SSA
# dependence is enough for this *opportunity projection*.  Memory operations,
# calls, PHIs, EH pads, and terminators are intentionally absent.
PURE_OPS = {
    "add", "sub", "mul", "udiv", "sdiv", "urem", "srem",
    "shl", "lshr", "ashr", "and", "or", "xor",
    "fadd", "fsub", "fmul", "fdiv", "frem", "fneg",
    "icmp", "fcmp", "select", "freeze", "getelementptr",
    "trunc", "zext", "sext", "fptrunc", "fpext", "fptoui",
    "fptosi", "uitofp", "sitofp", "ptrtoint", "inttoptr",
    "bitcast", "addrspacecast", "extractvalue", "insertvalue",
    "extractelement", "insertelement", "shufflevector",
}

_PREFIXES = {"tail", "musttail", "notail"}
_SSA = re.compile(r"(%[-A-Za-z$._0-9]+)\s*=\s*(.*)$")
_LABEL = re.compile(r"(?:[-A-Za-z$._0-9]+|\d+):(?:\s*;.*)?$")
_SSA_USE = re.compile(r"%[-A-Za-z$._0-9]+")


def _opcode(rhs: str) -> str:
    words = rhs.split()
    while words and words[0] in _PREFIXES:
        words.pop(0)
    return words[0] if words else ""


def parse_instructions(text: str) -> tuple[tuple[Instruction, ...], tuple[tuple[Instruction, ...], ...]]:
    """Parse function-body instruction lines and basic-block boundaries.

    This is intentionally a textual parser, not an LLVM parser.  It is strict
    about the small features it recognizes and ignores top-level declarations,
    attributes, metadata, and module directives.
    """
    instructions: list[Instruction] = []
    blocks: list[list[Instruction]] = []
    current: list[Instruction] = []
    in_function = False
    block_no = -1

    def finish_block() -> None:
        nonlocal current
        if current:
            blocks.append(current)
            current = []

    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if line.startswith("define "):
            finish_block()
            in_function = True
            block_no += 1
            continue
        if in_function and line == "}":
            finish_block()
            in_function = False
            continue
        if not in_function or not line:
            continue
        if _LABEL.fullmatch(line):
            finish_block()
            block_no += 1
            continue
        if line.startswith(("attributes ", "!", "uselistorder")):
            continue
        match = _SSA.fullmatch(line)
        result = match.group(1) if match else None
        rhs = match.group(2) if match else line
        inst = Instruction(
            ordinal=len(instructions),
            block=block_no,
            text=line,
            result=result,
            opcode=_opcode(rhs),
            rhs=rhs,
            uses=frozenset(_SSA_USE.findall(rhs)),
        )
        instructions.append(inst)
        current.append(inst)
    finish_block()
    return tuple(instructions), tuple(tuple(block) for block in blocks)


def _strip_binary_flags(rhs: str, opcode: str) -> str:
    rest = rhs[len(opcode):].lstrip()
    flags = {"nuw", "nsw", "exact", "disjoint"}
    words = rest.split()
    while words and words[0] in flags:
        words.pop(0)
    return " ".join(words)


def _binary_operands(inst: Instruction) -> tuple[str, str, str] | None:
    """Return (type, left, right) for scalar integer add/mul."""
    if inst.opcode not in {"add", "mul"}:
        return None
    rest = _strip_binary_flags(inst.rhs, inst.opcode)
    match = re.fullmatch(r"(i\d+)\s+([^,]+),\s*(.+)", rest)
    if not match:
        return None
    typ, left, right = match.groups()
    return typ, left.strip(), right.strip()


def _equality_operands(inst: Instruction) -> tuple[str, str, str] | None:
    if inst.opcode != "icmp":
        return None
    match = re.fullmatch(r"icmp\s+eq\s+(i\d+)\s+([^,]+),\s*(.+)", inst.rhs)
    if not match:
        return None
    typ, left, right = match.groups()
    return typ, left.strip(), right.strip()


def _identity_site(inst: Instruction) -> LLVMSite | None:
    binary = _binary_operands(inst)
    if binary:
        _, left, right = binary
        if inst.opcode == "add" and (left == "0" or right == "0"):
            return LLVMSite("identity", inst.ordinal, inst.ordinal)
        if inst.opcode == "mul" and (left == "1" or right == "1"):
            return LLVMSite("identity", inst.ordinal, inst.ordinal)
    equality = _equality_operands(inst)
    if equality:
        typ, left, right = equality
        if typ == "i1" and (left in {"true", "1"} or right in {"true", "1"}):
            return LLVMSite("identity", inst.ordinal, inst.ordinal)
    return None


def _operand_site(inst: Instruction) -> LLVMSite | None:
    parts = _binary_operands(inst) or _equality_operands(inst)
    if not parts:
        return None
    _, left, right = parts
    if left == right:
        return None
    return LLVMSite("operand", inst.ordinal, inst.ordinal)


def _adjacent_sites(blocks: Sequence[Sequence[Instruction]]) -> list[LLVMSite]:
    sites: list[LLVMSite] = []
    for block in blocks:
        for left, right in zip(block, block[1:]):
            if left.result is None or right.result is None:
                continue
            if left.opcode not in PURE_OPS or right.opcode not in PURE_OPS:
                continue
            if left.result in right.uses or right.result in left.uses:
                continue
            sites.append(LLVMSite("adjacent", left.ordinal, right.ordinal))
    return sites


def discover(text: str) -> tuple[tuple[Instruction, ...], tuple[LLVMSite, ...]]:
    instructions, blocks = parse_instructions(text)
    sites: list[LLVMSite] = []
    for inst in instructions:
        identity = _identity_site(inst)
        if identity is not None:
            sites.append(identity)
        else:
            operand = _operand_site(inst)
            if operand is not None:
                sites.append(operand)
    sites.extend(_adjacent_sites(blocks))
    return instructions, tuple(sorted(sites, key=lambda site: (site.start, site.end, site.family)))


def select_sites(candidates: Iterable[LLVMSite]) -> tuple[LLVMSite, ...]:
    selected: list[LLVMSite] = []
    last_end = -1
    for site in sorted(candidates, key=lambda value: value.key):
        if site.start > last_end:
            selected.append(site)
            last_end = site.end
    return tuple(sorted(selected, key=lambda value: (value.start, value.end, value.family)))


def header_width(site_count: int) -> int:
    return 0 if site_count == 0 else site_count.bit_length()


def payload_capacity(site_count: int) -> int:
    return site_count - header_width(site_count)


def _family_payload(candidates: Sequence[LLVMSite], family: str) -> int:
    return payload_capacity(len(select_sites(site for site in candidates if site.family == family)))


def project(text: str) -> Projection:
    instructions, candidates = discover(text)
    selected = select_sites(candidates)
    counts = {family: sum(site.family == family for site in candidates) for family in ("operand", "identity", "adjacent")}
    return Projection(
        instructions=len(instructions),
        operand_sites=counts["operand"],
        identity_sites=counts["identity"],
        adjacent_sites=counts["adjacent"],
        selected_sites=len(selected),
        payload_bits=payload_capacity(len(selected)),
        operand_only_payload_bits=_family_payload(candidates, "operand"),
        identity_only_payload_bits=_family_payload(candidates, "identity"),
        adjacent_only_payload_bits=_family_payload(candidates, "adjacent"),
    )
