# Reproduction guide

From the project root:

```bash
export PYTHONPATH="$PWD/artifact/src"
export PYTHONDONTWRITEBYTECODE=1
export TERM=xterm
python -m unittest discover -s artifact/tests -v
python artifact/scripts/run_evaluation.py
python artifact/scripts/run_external_llvm.py
python artifact/scripts/verify_submission.py
```

The unit suite contains 80 deterministic tests. The internal evaluation checks 400 programs, 3,200 complete source–target executions, 809 local carrier equations, 2,000 certificate mutations, 3,000 proof-object mutations, 65,536 interval instances, and 12,309 legal frames. The external command compiles every retained source at three optimization stages and preserves failures in the denominator.

`verify_submission.py` checks the final PDF, authorship slots, page count, page size, metadata surface, embedded fonts, native figure assets, reference ledgers, evaluation totals, external snapshot integrity, release layout, and public-surface hygiene.

The final environment does not provide `coqc` or a command-line Z3 executable. Their absence is recorded in `local_execution_gaps.json`; no conceptual proof or research-design task is delegated there.
