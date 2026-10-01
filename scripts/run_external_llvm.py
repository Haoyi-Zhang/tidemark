#!/usr/bin/env python3
"""Compile the frozen Go source snapshot and run the mode-4 LLVM projection.

The output is a read-only opportunity audit.  It is not an LLVM semantic
refinement, transformation certificate, or persistence experiment.  Every
failed compile keeps its portable command, return code, and a readable diagnostic
excerpt in addition to a digest of the complete diagnostic stream.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import shlex
import subprocess
import sys
import tempfile
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tidemark.external_llvm import project

SNAPSHOT = ROOT / "external" / "go-source-snapshot" / "src"
SOURCES = sorted(
    path for path in SNAPSHOT.rglob("*")
    if path.suffix in {".c", ".cc", ".cpp"}
    or path.as_posix().endswith("/cmd/link/testdata/testBuildFortvOS/main.m")
)
STAGES = ("O0", "O1", "O2")


def tree_hash(paths: list[pathlib.Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        rel = path.relative_to(SNAPSHOT).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(4, "big")); digest.update(rel)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()


def portable_command(source_relative: str, stage: str) -> list[str]:
    return [
        "clang", f"-{stage}", "-S", "-emit-llvm", "-Wno-everything",
        "-I", f"<snapshot>/{pathlib.PurePosixPath(source_relative).parent.as_posix()}",
        "-I", "<snapshot>", f"<snapshot>/{source_relative}", "-o", "<temporary>/module.ll",
    ]


def diagnostic_excerpt(stderr: str, maximum_lines: int = 20) -> str:
    lines = stderr.replace(str(SNAPSHOT), "<snapshot>").splitlines()
    return "\n".join(lines[:maximum_lines])


def main() -> int:
    rows: list[dict[str, Any]] = []
    for source in SOURCES:
        relative = source.relative_to(SNAPSHOT).as_posix()
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        for stage in STAGES:
            with tempfile.TemporaryDirectory(prefix="tidemark-llvm-") as temporary:
                output = pathlib.Path(temporary) / "module.ll"
                command = [
                    "clang", f"-{stage}", "-S", "-emit-llvm", "-Wno-everything",
                    "-I", str(source.parent), "-I", str(SNAPSHOT),
                    str(source), "-o", str(output),
                ]
                timed_out = False
                try:
                    completed = subprocess.run(
                        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, timeout=20, check=False,
                    )
                    returncode = completed.returncode
                    stdout = completed.stdout
                    stderr = completed.stderr
                except subprocess.TimeoutExpired as exc:
                    timed_out = True
                    returncode = 124
                    stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                    stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                row: dict[str, Any] = {
                    "source": relative,
                    "source_sha256": source_digest,
                    "stage": stage,
                    "portable_command_json": json.dumps(portable_command(relative, stage), separators=(",", ":")),
                    "portable_command_shell": shlex.join(portable_command(relative, stage)),
                    "returncode": returncode,
                    "timed_out": int(timed_out),
                    "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
                    "diagnostic_excerpt": diagnostic_excerpt(stderr),
                    "instructions": 0,
                    "operand_sites": 0,
                    "identity_sites": 0,
                    "adjacent_sites": 0,
                    "selected_sites": 0,
                    "payload_bits": 0,
                    "operand_only_payload_bits": 0,
                    "identity_only_payload_bits": 0,
                    "adjacent_only_payload_bits": 0,
                }
                if returncode == 0 and output.exists():
                    projection = project(output.read_text(errors="replace"))
                    row.update(projection.__dict__)
                rows.append(row)

    raw = ROOT / "data" / "raw" / "mode4"
    derived = ROOT / "data" / "derived"
    raw.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with (raw / "llvm-projection.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader(); writer.writerows(rows)
    with (raw / "llvm-projection.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")

    clang_version = subprocess.check_output(["clang", "--version"], text=True).splitlines()[0]
    clang_path = pathlib.Path(subprocess.check_output(["which", "clang"], text=True).strip()).resolve()
    summary: dict[str, Any] = {
        "schema": "llvm-opportunity-projection-mode4",
        "mode": "tidemark-mode-4",
        "adapter_policy": {
            "metadata": "trailing LLVM metadata attachments are removed before operand comparison",
            "poison_undef": "explicit poison and undef operands are rejected",
            "flags": "integer add/mul accept only the adapter's enumerated flags; other flags are rejected",
            "unsupported": "memory, calls, terminators, PHI/EH, floating point, vectors, and target-specific semantics are outside the certified language",
        },
        "claim_boundary": "Read-only textual opportunity projection; not an LLVM semantic refinement, transformation certificate, or post-optimization persistence result.",
        "go_version": subprocess.check_output(["go", "version"], text=True).strip(),
        "snapshot_root": "external/go-source-snapshot/src",
        "snapshot_source_files": len(SOURCES),
        "snapshot_source_bytes": sum(path.stat().st_size for path in SOURCES),
        "snapshot_source_tree_sha256": tree_hash(SOURCES),
        "clang_version": clang_version,
        "clang_binary_sha256": hashlib.sha256(clang_path.read_bytes()).hexdigest(),
        "attempts": len(rows),
        "raw_rows": "data/raw/mode4/llvm-projection.csv",
        "readable_failure_diagnostics": True,
        "stages": {},
    }
    metric_fields = [
        "instructions", "operand_sites", "identity_sites", "adjacent_sites",
        "selected_sites", "payload_bits", "operand_only_payload_bits",
        "identity_only_payload_bits", "adjacent_only_payload_bits",
    ]
    for stage in STAGES:
        stage_rows = [row for row in rows if row["stage"] == stage]
        successful = [row for row in stage_rows if row["returncode"] == 0]
        metrics = {field: sum(int(row[field]) for row in successful) for field in metric_fields}
        metrics["successful_modules"] = len(successful)
        metrics["failed_modules"] = len(stage_rows) - len(successful)
        metrics["timeouts"] = sum(int(row["timed_out"]) for row in stage_rows)
        summary["stages"][stage] = metrics
    encoded = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    (derived / "llvm-projection-mode4.json").write_text(encoded)
    (derived / "llvm-projection.json").write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
