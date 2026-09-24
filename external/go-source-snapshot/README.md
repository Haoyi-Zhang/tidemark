# Imported Go source snapshot

This directory contains the C, C++, Objective-C, and required header files used by the external LLVM opportunity projection. The snapshot was copied from the installed Go 1.23.2 source distribution without modifying upstream files.

`FILES.csv` records every imported path, byte count, and SHA-256 digest. `LICENSE` is the upstream license. The external adapter compiles the files at O0, O1, and O2 and reports both successes and failures. It is a read-only opportunity projection, not a semantic refinement of LLVM or an end-to-end watermark embedder.
