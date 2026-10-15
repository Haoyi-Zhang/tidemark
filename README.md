# TideMark Mode-4 artifact

This artifact implements the finite typed IR and embed-time relation in the
adjacent paper. It does not certify LLVM, persistence after optimization,
robustness, secrecy, ownership, or deployment security.

The optional pure native module below supplies a separate range-admitted
connection for generated scalar LLVM IR. It is not general LLVM certification,
and does not change the retained core/overlap/opportunity measurements.

## Optional owned pure native extension

Install native-requirements.txt in an isolated local environment. The native
test folder is outside default test discovery, so the core's standard-library
dependency contract stays unchanged. Run from this artifact directory:

~~~sh
python3 -B -m unittest discover -s native_tests -v
python3 -B scripts/run_native_study.py --small --out /path/to/fresh-small
python3 -B scripts/run_native_study.py --out /path/to/fresh-controlled
python3 -B scripts/run_native_study.py --verify-saved --out results/native-20261014-small-001
python3 -B scripts/run_native_study.py --verify-saved --out results/native-20261014-full-001
~~~

The native verifier reconstructs the fixed owned cohort and each authorized
module before reexecution. It does not execute arbitrary saved LLVM. New run
directories are mandatory; these commands never overwrite old results.
formal/native-connection.md states the pure subset, all-intermediate range
condition, command-slot transport, exact IR decoding theorem and compiler/ABI
assumptions. No current Coq compilation or general LLVM refinement is claimed.

The separate raw campaigns contain four all-message sources and 96 controlled
sources. Each uses all 98 states of the declared input box and four identical-
information selector policies. The controlled campaign retains 1,152 attempts,
984 targets, 168 capacity failures, 202,272 native calls, 1,968 rejected
rehashed IR changes and 592 distinct-message optimized-IR collision pairs.
Mode 4 ties singleton-first at 1,254 bits and 60/96 fixed-eight-bit successes;
source-first and adjacent-only each have 744 bits and 48/96. Saturation is
each policy's own quota, not a common-message comparison. Raw JSONL.gz retains
sources, complete candidates/schedules, ranges, input states, targets,
certificates, pre-/post-pass IR, outputs, generated COFF objects and mutations.

LLVM 20.1.8 / llvmlite 0.46.0 MCJIT actually ran on native Windows x86-64.
The default speed-level-2 IR pipeline and backend-opt0 are recorded separately;
this is not a Clang O2 campaign. Objects are experiment evidence, not deployment
memory/lifecycle cost. Pre-optimization IR is the extraction channel. The
retained external-source adapter is still opportunity-only. LLVM/ABI is trusted;
stateful native code, foreign IR, post-pass/object recovery and a complete
Python/Coq refinement are unvalidated.

## Reproduce from this directory

```sh
export PYTHONPATH="$PWD/src"
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s tests -v
python3 scripts/run_static_risk_regressions.py
python3 scripts/verify_evidence.py
python3 scripts/verify_all.py
```

The default matrix checks saved raw/derived evidence and runs tests and boundary
regressions. In a complete project checkout with a sibling `paper/` tree it
also builds the figures and paper and checks citations/PDF assets. A standalone
code checkout reports those manuscript components as unavailable, not passed.
The full-project build uses XeLaTeX for `main.tex`; its exporters reuse saved
measurements rather than rerunning timing campaigns. Current PDF pages and
identity are reported only from this invocation's successful PDF audit, bound
to the actual PDF bytes. A stopped build never inherits archived PDF metadata.
Use `python3 scripts/verify_all.py --include-paper` to explicitly require the
full-project manuscript checks.
A new complete CPU run, with new genuine timing measurements, is:

```sh
python3 scripts/verify_all.py --rerun
```

This reruns evaluation, finite algebra, and the fixed external LLVM projection
before rebuilding the paper. Timing and RSS are machine- and run-dependent;
there is no assertion that reruns reproduce their bit patterns. Structural
counts and scientific decisions are deterministic for the fixed inputs.
To prove that generated assets are not hidden dependencies:

```sh
python3 scripts/check_clean_build.py
```

The current owned-IR Linux execution is retained in `results/current/`.
It passes 111 tests, twelve boundary cases, and 7,303 finite algebra cases,
including all four expected countermodels. The full 400-program evaluation
checks 3,200 executions, 46,256 local cases and 2,000 certificate mutations
with no semantic discrepancy or accepted mutation; it takes 39.408 seconds
and 26,288 KiB peak RSS on that host. Large raw JSONL/CSV outputs use `.gz`
and decompress to their original bytes. This run is separate from the earlier
phase-timing table and does not execute LLVM or mechanize the proofs.

## Dependencies

Linux; Python 3.11 or newer (standard library for the core); the included Go
1.23.2 source snapshot; Clang 17 for the textual projection. Paper building also
needs XeLaTeX, BibTeX or bibtex8, the bundled acmart class and bibliography
style, Libertine, NewTX, and Inconsolata TeX packages. Python draws every
figure using Matplotlib and ReportLab; no figure TeX engine is invoked. PDF auditing needs
Poppler and PyMuPDF. The recorded visual review additionally used PDFium.
The reproduction workflow uses offline inputs. The recorded run did not include
a Coq-kernel or SMT recheck.

## Portable overlap regression

`tests/test_analysis_reuse.py` runs under the existing test discovery command,
or alone with
`python3 -B -m unittest discover -s tests -p test_analysis_reuse.py -v`.
It uses 24 owned sources of at most eight commands, including discarded
identity/operand/adjacent overlaps and state/trace conflicts, all legal payloads
for their schedules, and six typed input/store states. Complete descriptors,
orientations, targets, certificates, extraction, records and observations are
checked against the raw-tree reference; a test-local Cartesian-subset oracle
checks the maximum canonical schedule. These tests supplement the quota corpus,
not its counts or retained measurements.

Embedding and extraction reuse only their call-local source analysis. Public
discovery still validates, extraction validates the target before discovery,
and replay and the checker's extractor check remain in place.

## Overlap-bearing same-goal comparison

`python3 -B scripts/run_overlap_comparison.py` writes a separate run under
`results/current/overlap/` and refuses to overwrite an existing run. To recheck
the included raw sources, complete candidate descriptors/orientations,
policy-specific targets, observations and isolated mutations without writes:

```sh
python3 -B scripts/run_overlap_comparison.py --verify-saved
# New measurements go to a new directory; no historical data are replaced.
python3 -B scripts/run_overlap_comparison.py --output-dir /path/to/new-overlap-run
```

The study crosses four grammar families, four body sizes and twelve fixed
variants, producing 192 owned IR sources. All have overlaps; no target capacity
quota or seed search is used. Every non-unit value feeds a dependent output
suffix, and store/trace effects remain observable. Mode 4 uses the actual core
embed/check/extract APIs. Source-first (longer interval at equal start),
singleton-first (singletons before gap-filling adjacent sites), and adjacent-only
are source-only baselines with checked replay, canonical bytes, digests, framing
and extraction. Their separately tagged schema is not a Mode-4 certificate.
The wrappers reuse legal carrier primitives; raw-tree policy implementations and
evaluators are differential evidence, not a complete independent proof kernel.

The empty and fixed-eight-bit requests compare identical goals per source.
Saturation compares each policy's capacity and uses different message lengths.
All attempts and capacity failures are retained. Mode 4 and singleton-first tie
at 4,336 sites/3,376 user bits and 120/192 fixed-message successes; source-first
has 2,930 sites/2,066 bits and adjacent-only 2,880 sites/2,016 bits, both with
96/192 fixed-message successes. The 1,968 feasible embeddings undergo 11,808
complete-observation comparisons, with no difference, and both checkers reject
3,936 isolated payload or rehashed-return mutations. Both orientations of each
family are reached. This remains a constructed terminating-language evaluation,
not LLVM validation, a natural-software sample, a timing comparison, or proof
closure. `summary.json` binds the exact executable sources; verification rejects
a source-version mismatch. The paper exporter derives its separate macros and
table from these raw records, with count/failure gates.

## Scientific interpretation

The 400 programs are quota constructed: family capacities, carrier totals, and
total bindings are construction inputs. Family counts are regression outcomes,
not independent natural-program prevalence measurements. The raw-tree reference
checker does not import production semantics. The structural-record verifier
reuses reference semantics and is therefore not an independent proof kernel.
Its five fields per step are record values, not independently proven premises.

The retained Linux raw evidence is under `data/raw/mode4/`. Each program,
execution, selected site, certificate mutation, record mutation, adjacent-pair
classification, frame vector, and interval instance precedes aggregation. The
external runner retains failed compilation diagnostics as well as hashes.
`data/derived/verification-matrix-current.json` records that archived run's
component exits; `audit/current/` retains its logs and consistency/build/PDF
audits. Their names do not make them validations of later source edits.

In particular, the retained `pdf-audit.json`, `pdf-source-audit.log`,
`clean-build.json`, `release-audit.json` and related logs include an earlier
36-page PDF identity (`929f923cb1c4b71134f2966f62848a2205d235041673a30156a40bc544f8d0fd`).
They are historical build/generation records, not audits of the current
41-page manuscript. The archived matrix and PDF audit may contain 48-page
packaging-goal fields; those fields have no scientific role and are not emitted
by the current scripts. Historical records and measurement bytes are retained
unchanged. A new verification run writes only what it actually executes; it
does not refresh the archived release, clean-build or visual review by implication.

The saved Linux runs predate the parser and structural-record corrections.
Their structural mutation rows include accumulated changes because exporting
step dictionaries previously aliased the producer record. These rejected rows
do not establish isolated per-field rejection. Import/export now copy nested
steps, and canonical comparisons distinguish integer bits/coordinates from
Boolean and floating-point aliases. The saved Linux timings and LLVM results
remain historical; they have not been replaced by corrected-source measurements.

For separate fresh offline outputs without overwriting the saved run, use:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/run_static_risk_regressions.py --output-dir /path/to/new-run/boundaries
python3 -B formal/check_finite_algebra_mode4.py --output-dir /path/to/new-run/finite
# The full evaluation uses Linux resource/RSS semantics.
python3 -B scripts/run_evaluation.py --output-dir /path/to/new-run/evaluation
```

The evaluation entry point fails on measured discrepancy/acceptance counters or
wrong frozen counts, after preserving raw outputs. The prepared
`.github/workflows/scientific-checks.yml` uses the flat artifact-repository root,
Ubuntu 24.04, a whole-run deadline and resource limits, and always attempts to
upload raw outputs and logs. It runs only owned IR/finite cases: no external
compiler campaign, TeX build, API, or third-party application. It has not been
executed on GitHub as part of the local checks.

The 75-entry bibliography and every current citation are indexed in
`reference/`. Read `reference-review.md` for the distinction between metadata
corroboration, local citation fit, full-text review, and scientific correctness.

In a complete project, `scripts/audit_references.py` distinguishes the active
TeX citation keys, any explicit `nocite` entries, the actual BBL/AUX presentation,
and unpresented database reserves. Currently 74 keys are cited and printed;
`r09` is retained only as an unpresented database record, not a missing citation.
The 60-reference floor applies to printed entries. Missing/duplicate keys,
DOIs, wrong AUX numbering and BBL/database identity mismatches still fail.
The checker replays BibTeX with the bundled style in a temporary directory and
compares the BBL, including ordered authors, titles, years and DOI mapping;
renderer-specific name formatting is not treated as a spelling correction.
This is local consistency, not certification of the original publications or
their support for a manuscript claim. Existing `reference/` outputs remain
historical until a new check is actually run on the intended project copy.

`scripts/check_clean_build.py` closes both PDFs after every comparison, also
when opening or reading a PDF fails, before removing its temporary project.
All eight text/render comparisons (main manuscript and seven figures) and macro-byte checks remain required;
build, comparison and temporary-cleanup errors are not suppressed.

### Editable Python schematics

`figures/draw_schematics.py` generates the five structural diagrams as
font-embedded vector PDFs. In the complete package,
`python3 ../paper/figures/build_figures.py --outdir OUTPUT` regenerates all
seven figures, including the native connection and the two retained-data plots.
The manuscript contains inclusion wrappers rather than TeX drawing code.
The clean-build and PDF audits include the native connection. Paper drawing
dependencies are listed in `requirements.txt`; core checking remains
standard-library-only.
