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

## Dependencies

Linux; Python 3.11 or newer (standard library for the core); the included Go
1.23.2 source snapshot; Clang 17 for the textual projection. Paper building also
needs pdfTeX, BibTeX or bibtex8, the bundled acmart class and bibliography style,
TikZ, PGFPlots, Libertine, NewTX, and Inconsolata TeX packages. PDF auditing needs
Poppler and PyMuPDF. The recorded visual review additionally used PDFium.
The reproduction workflow uses offline inputs. The recorded run did not include
a Coq-kernel or SMT recheck.

## Scientific interpretation

The 400 programs are quota constructed: family capacities, carrier totals, and
total bindings are construction inputs. Family counts are regression outcomes,
not independent natural-program prevalence measurements. The raw-tree reference
checker does not import production semantics. The structural-record verifier
reuses reference semantics and is therefore not an independent proof kernel.
Its five fields per step are record values, not independently proven premises.

The current complete raw evidence is under `data/raw/mode4/`. Each program,
execution, selected site, certificate mutation, record mutation, adjacent-pair
classification, frame vector, and interval instance precedes aggregation. The
external runner retains failed compilation diagnostics as well as hashes.
`data/derived/verification-matrix-current.json` records real component exits;
`audit/current/` contains current logs and consistency/build/PDF audits.

The saved runs predate the parser and structural-record round-trip corrections.
They remain observations of that source version, not test results for the
corrected implementation; the current source and added regressions need a
fresh run before making that claim.

The 75-entry bibliography and every current citation are indexed in
`reference/`. Read `reference-review.md` for the distinction between metadata
corroboration, local citation fit, full-text review, and scientific correctness.
