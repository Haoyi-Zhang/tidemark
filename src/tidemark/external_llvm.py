"""Conservative read-only LLVM opportunity projection for TideMark mode 4.

The adapter is not an LLVM semantic refinement.  It recognizes a deliberately
small textual subset after removing metadata attachments.  Both paths exclude
explicit ``poison`` and ``undef``. Identity/operand sites require scalar integers;
adjacency uses the broader opcode whitelist below without a general type/flag
analysis. Memory, calls, terminators, PHIs and exceptional control flow are not
adjacency opportunities. None of these filters certifies LLVM semantics.
"""
from __future__ import annotations

import math
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
        rank = {"identity": 0, "operand": 1, "adjacent": 2}
        return self.end, self.start, rank[self.family]


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


# Result-producing instructions treated as textual, side-effect-free adjacency
# opportunities.  This policy is intentionally narrower than LLVM purity.
ADJACENT_PURE_OPS = {
    "add", "sub", "mul", "and", "or", "xor", "shl", "lshr", "ashr",
    "icmp", "select", "freeze", "trunc", "zext", "sext", "bitcast",
    "ptrtoint", "inttoptr", "getelementptr", "extractvalue", "insertvalue",
    "extractelement", "insertelement", "shufflevector",
}
COMMUTATIVE_OPERAND_OPS = {"add", "mul"}
ALLOWED_INTEGER_FLAGS = {"nuw", "nsw"}
_PREFIXES = {"tail", "musttail", "notail"}
_SSA = re.compile(r"(%[-A-Za-z$._0-9]+)\s*=\s*(.*)$")
_LABEL = re.compile(r"(?:[-A-Za-z$._0-9]+|\d+):(?:\s*;.*)?$")
_SSA_USE = re.compile(r"%[-A-Za-z$._0-9]+")
_METADATA_START = re.compile(r",\s*![A-Za-z$._][A-Za-z$._0-9-]*\s+!")
_POISON_OR_UNDEF = re.compile(r"(?<![-A-Za-z$._0-9])(poison|undef)(?![-A-Za-z$._0-9])")


def _strip_metadata_attachments(rhs: str) -> str:
    """Drop trailing LLVM metadata attachments before operand comparison."""
    match = _METADATA_START.search(rhs)
    return rhs[: match.start()].rstrip() if match else rhs.rstrip()


def _opcode(rhs: str) -> str:
    words = rhs.split()
    while words and words[0] in _PREFIXES:
        words.pop(0)
    return words[0] if words else ""


def parse_instructions(text: str) -> tuple[tuple[Instruction, ...], tuple[tuple[Instruction, ...], ...]]:
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
        raw_rhs = match.group(2) if match else line
        rhs = _strip_metadata_attachments(raw_rhs)
        instruction = Instruction(
            ordinal=len(instructions),
            block=block_no,
            text=line,
            result=result,
            opcode=_opcode(rhs),
            rhs=rhs,
            uses=frozenset(_SSA_USE.findall(rhs)),
        )
        instructions.append(instruction)
        current.append(instruction)
    finish_block()
    return tuple(instructions), tuple(tuple(block) for block in blocks)


def _contains_poison_or_undef(text: str) -> bool:
    return bool(_POISON_OR_UNDEF.search(text))


def _integer_binary_operands(instruction: Instruction) -> tuple[str, str, str] | None:
    """Return (type, left, right) for supported scalar integer add/mul."""
    if instruction.opcode not in COMMUTATIVE_OPERAND_OPS:
        return None
    rest = instruction.rhs[len(instruction.opcode) :].strip()
    words = rest.split()
    flags: list[str] = []
    while words and not re.fullmatch(r"i\d+", words[0]):
        flags.append(words.pop(0))
    if any(flag not in ALLOWED_INTEGER_FLAGS for flag in flags):
        return None
    rest = " ".join(words)
    match = re.fullmatch(r"(i\d+)\s+([^,]+),\s*(.+)", rest)
    if not match:
        return None
    typ, left, right = (part.strip() for part in match.groups())
    if _contains_poison_or_undef(left) or _contains_poison_or_undef(right):
        return None
    return typ, left, right


def _equality_operands(instruction: Instruction) -> tuple[str, str, str] | None:
    if instruction.opcode != "icmp":
        return None
    match = re.fullmatch(r"icmp\s+eq\s+(i\d+)\s+([^,]+),\s*(.+)", instruction.rhs)
    if not match:
        return None
    typ, left, right = (part.strip() for part in match.groups())
    if _contains_poison_or_undef(left) or _contains_poison_or_undef(right):
        return None
    return typ, left, right


def _identity_site(instruction: Instruction) -> LLVMSite | None:
    binary = _integer_binary_operands(instruction)
    if binary:
        _, left, right = binary
        if instruction.opcode == "add" and (left == "0" or right == "0"):
            return LLVMSite("identity", instruction.ordinal, instruction.ordinal)
        if instruction.opcode == "mul" and (left == "1" or right == "1"):
            return LLVMSite("identity", instruction.ordinal, instruction.ordinal)
    equality = _equality_operands(instruction)
    if equality:
        typ, left, right = equality
        if typ == "i1" and (left in {"true", "1"} or right in {"true", "1"}):
            return LLVMSite("identity", instruction.ordinal, instruction.ordinal)
    return None


def _operand_site(instruction: Instruction) -> LLVMSite | None:
    operands = _integer_binary_operands(instruction) or _equality_operands(instruction)
    if operands is None:
        return None
    _, left, right = operands
    if left == right:
        return None
    return LLVMSite("operand", instruction.ordinal, instruction.ordinal)


def _eligible_adjacent_instruction(instruction: Instruction) -> bool:
    if instruction.result is None or instruction.opcode not in ADJACENT_PURE_OPS:
        return False
    if _contains_poison_or_undef(instruction.rhs):
        return False
    # For add/mul, reject unsupported flags using the same parser as operand
    # discovery.  Noncommutative integer operators are admitted only when their
    # textual form has no explicit poison/undef; this remains a projection.
    if instruction.opcode in COMMUTATIVE_OPERAND_OPS:
        return _integer_binary_operands(instruction) is not None
    return True


def _adjacent_sites(blocks: Sequence[Sequence[Instruction]]) -> list[LLVMSite]:
    sites: list[LLVMSite] = []
    for block in blocks:
        for left, right in zip(block, block[1:]):
            if not _eligible_adjacent_instruction(left) or not _eligible_adjacent_instruction(right):
                continue
            if left.result in right.uses or right.result in left.uses:
                continue
            sites.append(LLVMSite("adjacent", left.ordinal, right.ordinal))
    return sites


def discover(text: str) -> tuple[tuple[Instruction, ...], tuple[LLVMSite, ...]]:
    instructions, blocks = parse_instructions(text)
    sites: list[LLVMSite] = []
    for instruction in instructions:
        identity = _identity_site(instruction)
        if identity is not None:
            sites.append(identity)
        else:
            operand = _operand_site(instruction)
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
    if type(site_count) is not int or site_count < 0:
        raise ValueError("site count")
    return site_count.bit_length()


def payload_capacity(site_count: int) -> int:
    return site_count - header_width(site_count)


def _family_payload(candidates: Sequence[LLVMSite], family: str) -> int:
    return payload_capacity(len(select_sites(site for site in candidates if site.family == family)))


def project(text: str) -> Projection:
    instructions, candidates = discover(text)
    selected = select_sites(candidates)
    counts = {
        family: sum(site.family == family for site in candidates)
        for family in ("operand", "identity", "adjacent")
    }
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
