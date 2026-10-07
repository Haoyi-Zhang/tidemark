# TideMark Mode-4 artifact

This artifact implements the finite typed IR and embed-time relation in the
adjacent paper. It does not certify LLVM, persistence after optimization,
robustness, secrecy, ownership, or deployment security.

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
needs pdfTeX, BibTeX or bibtex8, the bundled acmart class and bibliography style,
TikZ, PGFPlots, Libertine, NewTX, and Inconsolata TeX packages. PDF auditing needs
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
