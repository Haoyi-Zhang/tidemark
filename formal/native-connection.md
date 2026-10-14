# Range-admitted pure LLVM connection

This extension leaves the original Mode-4 relation, historical quota corpus,
overlap campaign and opportunity projection unchanged. It lowers generated
TideMark trees, not arbitrary external LLVM. The wrapper version is
`tidemark-pure-i64-lowering-1`; baseline selection is explicitly policy tagged.

## Domain and observation

Programs have Int/Bool parameters, no regions, and only variables, Int/Bool
literals, add/sub/mul/eq/lt/not and pure conditional expressions. All bindings
are globally unique. Unit parameters/results and get/put/emit are rejected.
The observation is `(result, {}, ())`; the empty state and trace are not an
omission of effects from a stateful native test.

A box B gives an inclusive integer interval for exactly every Int parameter.
Boolean parameters range over both values. All endpoints and literal values
are exact integers. Let I64 = [-2^63, 2^63-1]. Admission checks every interval
against I64, including all intermediate expressions and both arms of a
conditional. It propagates sum/difference endpoints, the min/max of all four
multiplication endpoints, and the hull of conditional arms. Boolean results
need no integer interval, but their operands are still traversed. This is a
sufficient, nonrelational condition, not necessary admission: `a-a` over the
entire signed interval is safe but can be rejected by interval subtraction.

Input calls obey B and exact parameter types; Boolean ABI values are 0/1.
The optional test harness executes only these generated modules. It is not an
input-validation boundary for arbitrary LLVM or arbitrary ctypes signatures.

## Lemma 1: interval confinement

For every admitted program and parameter assignment in B, every mathematical
integer subexpression lies in its inferred interval, hence in I64.

Proof. Induct on expression structure in the current binding environment.
Variables use its induction invariant; literals are singleton intervals.
Addition/subtraction endpoint formulas contain every possible operand pair.
Multiplication's extrema over the rectangular operand ranges occur at its
corners. Comparison/not produce Booleans after recursively checked operands.
A selected conditional result is in the hull of the arms; both arms have
separately established intervals. Extend the environment after each command.
This proves confinement for all commands, including ones not contributing to
the returned value. Correlations lost by interval arithmetic only enlarge the
range and can cause conservative rejection, not acceptance of overflow.

## Lemma 2: lowering simulation

Assume the specified scalar LLVM instruction semantics and the stated ABI.
For an admitted program P and input i in B, signed decoding of L(P)(i) equals
the mathematical result of P(i), with empty store/trace on each side.

Proof. Associate each parameter/binder with its injectively named SSA value.
Int uses i64; Bool uses i1 (truncation of an ABI 0/1 input). A direct command
copies its value with bitwise `or` with zero/false. Expression induction shows
that constants and SSA uses agree; flagless add/sub/mul compute modulo 2^64,
whose signed interpretation agrees with the mathematical result by Lemma 1.
`icmp eq` preserves equality and `icmp slt` signed order. Boolean not is xor
with true. Both lowered arms of select are computed, but are pure, defined,
nontrapping and range admitted, so eager evaluation adds no observable effect
and the selected value agrees with the language conditional. Command induction
extends the SSA environment. Int returns i64; Bool returns its zero extension.
There are no memory accesses, calls, shifts, divisions, poison constants, undef,
no-wrap flags, exceptional edges or external symbols in the generated subset.

This is a paper-level proof against instruction semantics, not a mechanized
LLVM model or a proof of LLVM code generation/MCJIT/ctypes. Native testing is
finite evidence for those executable connections. The original Coq file is
unaltered and has no theorem about this lowering.

## Lemma 3: range and footprint transport

Every pure Mode-4 orientation preserves admission in B and the inferred
interval of each binding. Its lowered command fragment is independent of the
ordinal, payload and disjoint fragments.

Proof. Commutative orientations give the same interval for add/mul and the
same Boolean type for equality. Both identity forms give the atomic base's
interval/type: adding zero preserves endpoints; equality with true returns
Bool. An independent adjacent exchange reads neither newly bound value, and
the two assignments extend the map with the same names/intervals. At a later
disjoint command the complete type/range map is therefore unchanged. Inside a
fragment, SSA identifiers and temporary identifiers use the binder's UTF-8
hex encoding and a separate namespace; the local instruction counter starts
at zero for each binder. No earlier instruction count shifts these names.
Command-slot markers remain in source coordinate order. Fragment length may
grow, so source command slots, not LLVM instruction ordinals, are coordinates.

## Lemma 4: lowered exact decoding

For source-derived disjoint sites and framed bits, extraction from the actual
generated pre-optimization IR returns those bits, hence the original payload.

Proof. Direct identity copies have fewer instructions than their expanded
forms, including literal bases; no builder performs constant folding. Operand
orientation exchanges two distinct typed expression encodings. In this grammar
the recursively emitted expression instructions/values distinguish constants,
variable names, operators, types and child order; temporaries preserve tree
order and perform no common-subexpression elimination or simplification.
The two operand fragments are therefore different. Adjacent orientations
exchange command fragments with distinct destination identifiers. Exact local
fragment comparison chooses exactly one orientation. Lemma 3 frames disjoint
sites. Source-only selection reconstructs the same ordered slots, and the
unchanged frame/unframe law recovers the payload.

## Theorem: native wrapper contract

If `native.check(Pbytes,Qbytes,IRbytes,wrapper)` accepts, then for every typed
input i in the declared box B:

1. L(P)(i) = L(Q)(i) = Obs(P,i).result under the assumptions of Lemma 2;
2. extraction from the supplied pre-optimization IR returns the certified
   message, with no external message length;
3. the entire supplied IR equals the deterministic lowering of the authorized
   canonical target Q, including the interface, unselected commands and return.

Proof. The wrapper checks the underlying policy-specific complete replay
certificate, source and target admission, and whole-IR equality with L(Q).
Original pure carrier/replay laws give Obs(P,i)=Obs(Q,i). Apply Lemma 2 twice
and Lemma 4. Digest binding is additional byte binding, not authorship
authentication; recomputing a changed module's digest cannot satisfy L(Q)=IR.

All four compared selectors have the same local rules, frame, range condition,
lowering, observations and available information. Source-first and singleton-
first use the full family set; adjacent-only restricts the library. Earliest
finish and singleton-first attain the same optimum on this singleton/adjacent
interval family. The algorithms and interval analysis are standard mechanisms.

## Explicit boundaries and countermodels

The unchecked, flagless module `z = mul i64 a,a; return z` at a=2^32 returns 0,
where mathematical evaluation returns 2^64. It has defined modular behavior;
it is not an OS exploit, UB test or historical TideMark defect. The native
range gate rejects this bridge, including when the multiplication occurs in a
nonselected conditional arm. Without a no-overflow premise one could instead
prove a different modular-language theorem; it would not be the retained
unbounded-integer contract.

The extraction theorem concerns the supplied textual IR before LLVM parsing,
pretty-printing, optimization and code generation. Markers are coordinates,
not covert payload: checker equality fixes them completely. LLVM parsing drops
comments, so a lost-marker decoder failure alone is not evidence that message
information has vanished. The campaign instead compares complete optimized IR
for distinct actual messages at the same source/policy. Equal optimized IR is
a concrete instance of the original orientation-collapse boundary. Native
object bytes are retained but not decoded. No binary persistence is claimed.

No theorem or test covers stateful native code, foreign LLVM, loops, memory,
aliasing, exception paths, concurrency, floats, poison/undef or post-pass exact
recovery. Range checks can conservatively reject safe programs. Correct compiler
and ABI behavior remain assumptions. Tests do not imply novelty or acceptance.
