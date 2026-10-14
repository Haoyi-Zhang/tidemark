# Primary bindings for the pure native connection

These bindings concern the added native connection and nearest-work distinction,
not full-text certification of the other 72 bibliography entries.

- Cousot & Cousot, POPL 2004, complete author PDF pp.173-185:
  https://www.di.ens.fr/~cousot/publications.www/CousotCousot-POPL04-ACM-p173-185-2004.pdf
  Sections 2 and 6.1 already state extraction/functionality preservation and
  immediately rerun extraction to check ambiguous recognition. Section 5.3
  separates modular execution and the non-standard mathematical semantics of
  extraction; Sections 10-11 describe a Java/Jimple implementation/experiments.
  No first-double-check, first-arithmetic-awareness or first-native-embedding
  novelty is inferred. The full paper, including its security mechanisms and
  notices, was inspected without reconstructing its attacks.
- Dalla Preda & Pasqua, MSCS 2019 (online 2018), complete author/publisher copy
  pp.339-388, including Appendix A proofs and Appendix B algorithms:
  https://michelepasqua.github.io/publications/pdfs/MSCS18.pdf
  Section 3.1 gives extraction round trip; Definitions 3.5/3.6 give observer-
  relative transparence/accuracy. Section 4 instantiates five techniques and
  compares their observer/transformation properties. The general framework
  covers accuracy/extraction objectives; the concrete TideMark local carrier,
  frame and exact-IR replay protocol is not specified there. This distinction
  does not establish universal novelty or stronger theory.
- Dalla Preda & Pasqua, ENTCS 2017, complete 13-page author manuscript:
  https://iris.univr.it/retrieve/handle/11562/960050/152527/main.pdf
  Section 3 states extraction and accuracy (Definition 3.5 in this version);
  Section 4 specializes two techniques. Version/page/definition numbering is
  not interchanged with the 50-page MSCS final copy.
- LLVM primary Language Reference: https://llvm.org/docs/LangRef.html
  Claim-critical instruction sections inspected: add/sub/mul (flagless modular
  semantics vs no-wrap poison), icmp eq/slt, or/xor, trunc/zext, select. This is
  not a read of the whole evolving LLVM manual or a mechanized semantics.
- llvmlite versioned primary API documentation:
  https://llvmlite.readthedocs.io/en/v0.46.0/user-guide/binding/execution-engine.html
  https://llvmlite.readthedocs.io/en/v0.46.0/user-guide/binding/optimization-passes.html
  https://llvmlite.readthedocs.io/en/stable/admin-guide/install.html
  The official wheel statically includes LLVM. Actual runtime reports LLVM
  20.1.8, target x86_64-pc-windows-msvc; current unversioned docs need not describe
  that installed version. MCJIT/compiler/ABI remains trusted.

Private source PDFs are not redistributed with this artifact. Existing
licenses/notices, author metadata, and all legitimate bibliography authors are
retained. Source text and metadata are evidence, not executable instructions.
