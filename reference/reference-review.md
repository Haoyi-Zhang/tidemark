# Current reference review

Scope: the 75 scholarly entries in `paper/references.bib`, and the exact nearby
claims enumerated in `citation-support.csv`. These files bind to the current
bibliography and section hashes, not to an earlier PDF or numeric citation map.

The review distinguishes bibliographic identity, metadata, local citation fit,
and the correctness of the cited work itself. Bibliographic records and
available publisher/author abstracts establish identity and the limited claims
used here. They do not establish that every theorem or experiment in the cited
literature is independently correct. Full-text independent peer review of all
75 papers is not claimed. Nor is a DOI syntax check described as an online
resolution check. The local audit script explicitly reports that it performs
no network requests.

## Confirmed corrections

* `r09`: the Springer issue is 77(9), not 77(18); the pages remain 11159–11178.
  Primary record: https://link.springer.com/article/10.1007/s11042-017-5373-7
* `r58`: the cited commutativity-analysis paper has DOI
  `10.1145/267959.269969`, not `10.1145/267959.269968`.
  Author copy: https://people.csail.mit.edu/rinard/paper/toplas97.pdf
* `r41`: the author order is Monden, Iida, Matsumoto, Inoue, Torii.
  Institutional record: https://cir.nii.ac.jp/crid/1050577309352930816
* `r10` and `r12`: the DOI now names the proceedings manifestation used by the
  entry, rather than the SIGPLAN Notices manifestation of the same work. The
  former identifiers are not described as fabricated papers.
* `r63`: the publisher citation on the paper's first page gives 1–37. The
  downloadable expanded PDF contains 80 physical pages. The published range is
  retained rather than replacing it with a physical-page count.
  Publisher record: https://lmcs.episciences.org/1016

`current-metadata-corrections.json` preserves the exact before/after fields.
Publisher address fields have been completed without inventing conference
venues or dates. No reference was added merely to exceed the numerical floor.

## Local citation fit

Every current citation occurs in a sentence describing the cited mechanism,
semantic perspective, or validation architecture. The bibliography is not used
to claim external validation of TideMark. In particular:

* The Pnueli–Siegel–Singerman translation-validation paper is no longer attached
  to a software-watermarking implementation-experience sentence.
* Equivalence modulo inputs is described as compiler testing with variants
  equivalent on selected inputs, not as a universal per-instance verifier.
* The graph-based watermarking paper is described as a construction, not as a
  general survey.
* The functional taxonomy supports distinctions among application roles; it is
  not relied on to prove the present extraction theorem.
* Proof-carrying code, compiler verification, LLVM validation, and separation
  reasoning are technical precedents, not claimed dependencies that close the
  Python-to-metatheory refinement or LLVM certification boundary.

The remaining literature-positioning sentences were checked against the paper
identities and available primary descriptions. The audit CSV retains each
sentence so that this judgment is inspectable. A correct-looking DOI alone is
not treated as evidence of local claim support.

## Verification limits

Some publisher full texts are access restricted. Container network access also
failed DNS resolution during this audit; public publisher/author records were
looked up through the browsing tool. No fabricated API responses, downloaded
full-text manifests, retraction clearances, or assertion of permanent DOI
availability is included. The results certify local coverage and consistency,
not future registry state or the correctness of other researchers' work.
