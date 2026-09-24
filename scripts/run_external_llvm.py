#!/usr/bin/env python3
"""Compile the frozen Go source snapshot and run the read-only LLVM projection."""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

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


def main() -> int:
    rows: list[dict[str, object]] = []
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
                try:
                    completed = subprocess.run(
                        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, timeout=20, check=False,
                    )
                    returncode = completed.returncode
                    stderr = completed.stderr
                except subprocess.TimeoutExpired as exc:
                    returncode = 124
                    stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
                row: dict[str, object] = {
                    "source": relative,
                    "source_sha256": source_digest,
                    "stage": stage,
                    "returncode": returncode,
                    "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest(),
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

    raw = ROOT / "data" / "raw"
    derived = ROOT / "data" / "derived"
    raw.mkdir(parents=True, exist_ok=True)
    derived.mkdir(parents=True, exist_ok=True)
    with (raw / "llvm-projection.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

    clang_version = subprocess.check_output(["clang", "--version"], text=True).splitlines()[0]
    clang_path = pathlib.Path(subprocess.check_output(["which", "clang"], text=True).strip()).resolve()
    summary: dict[str, object] = {
        "schema": "llvm-opportunity-projection",
        "claim_boundary": "Read-only textual opportunity projection; not an LLVM semantic refinement or end-to-end certification result.",
        "go_version": subprocess.check_output(["go", "version"], text=True).strip(),
        "snapshot_root": "external/go-source-snapshot/src",
        "snapshot_source_files": len(SOURCES),
        "snapshot_source_bytes": sum(path.stat().st_size for path in SOURCES),
        "snapshot_source_tree_sha256": tree_hash(SOURCES),
        "clang_version": clang_version,
        "clang_binary_sha256": hashlib.sha256(clang_path.read_bytes()).hexdigest(),
        "attempts": len(rows),
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
        summary["stages"][stage] = metrics
    (derived / "llvm-projection.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
