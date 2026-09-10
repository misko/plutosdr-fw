# C1 plus K1/M1: source-specific physical preparation, offline only

**43 offline tests pass** in62.28s, original42873 exit0; Ruff passes. The
prepared recipe binds exactly the accepted relocated10102 source. No synthesis,
placement, route, RTL change or new actual FFT evaluation was performed.
Tested FW `ed7cb390207e48010d096f8bf953cbe5935edc86`, HDL
`49a133554c8cb738d2a93136355571225df7076c`.

## Minimal recipe adaptation and preserved gates

The new generator restores its entire generated helper to the reviewed C1
helper, then the unchanged C1 inverse restores the complete original R/D/S
helper. The C1 generator is copied byte-for-byte, SHA4ecdc126…; the original
base remains0fee7f69… and the external one-shot owner remainsd0f36ce2….
The complete generated Tcl has an independent inverse to the C1 adapter.

Only the bank/joiner/ROM physical file/module names and top select the additive
variants. Explicit K/M=1 settings, set/readback and uniqueness checks are added;
R/D/S/C remain1. The seven physical RTL files equal their actual frozen sources.
Every canonical runtime file remains unchanged. No additional arithmetic,
descriptor-enable, pipeline or local-control flag is selected.

The actual-admission layout changes from old `actual-*.txt` paths to the
relocated run's sibling owner receipts. It does not copy or fabricate old-layout
receipts. All original C1 source/numerical/current-fault/CSV/qualified-status
gates remain; the new admission additionally replays frozen ROM full-source
and result checks, exact persisted zero statuses, reviewed owner hash, stored
pre/post hashes and all19 after-only generated-IP identities. Old observers,
references, helpers, vectors, settings and all56 actual-source files remain
bound by the immutable6f5 inventory. Both full main and extra CSV pairs retain
the historical hashes. The accepted status scope remains953943 raw-equal plus
292315 invalid-only, not raw217 equality; the ROM view is unconditional.

The original synthesis directives, IP factory,100/175 resource XDC, threads
hook, part, two-thread settings, no-black-box gate and route script are exact.
The owner still distinguishes raw tool exit from complete required products
and records both source-audit attempts even on failure; it does not retry or
route. No timing exception or interface/CDC qualification is added.

Tests cover whole helper/Tcl/source/owner inverses; both flags' missing, zero,
duplicate, conflicting, lowercase, unknown and lost-readback cases; hostile
Python parent environment reaching only a mocked project-creation trap;
no-overwrite/symlink paths; rehashed physical-source corruption; complete
copied-source closure; failed23845 and non-ROM C1 rejection; empty/nonzero
persisted receipts, missing post hashes, changed owner, missing/wrong ROM
terminal and old-observer corruption. These are offline admission tests, not
vendor synthesis or substitutes for the actual10102 numerical proof.

Initial lint-only output flagged an unused import and test-side `exec`. The
retained draft was changed only to assert the frozen C1 hash and load that
exact helper via runpy; no test acceptance or production code changed. Initial
pure preparation25923 and final preparation4662 both exited0. Raw attempts,
generated traps/mutations, source snapshots and final freeze are retained
under non-/tmp `rom-physical-offline-v1.pUUMEuvr` in the recovery parent.

Portable package `reports/experiments/20260910-rom-physical-preparation-v1.tgz`
contains699 file members plus its embedded receipt,4,190,608 bytes, SHA
`e67a4bcafdb717e4218d1100b040d905dbe4ab9c7b542d8ced7a51f02f1bd739`.
It includes all retained test/preparation artifacts, the initial lint draft,
final source dependencies and the exact18-file final freeze. Twelve large
copied log artifacts are individually gzip-compressed with their original byte
identities; all698 original regular-file identities were verified. Eleven
pytest-current/deliberate alias links are excluded from file payloads, with
each path/target recorded. Original trees/links remain intact; no failed test
or mutation artifact was discarded. The companion JSON hashes every archive
member; committed Git-object/inner-member verification accompanies publication.

## Exact prepared source and proposed command

Prepared directory:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-k1m1-physical-prepared-v1`.
It contains18 inventoried files plus SHA256SUMS. Inventory SHA:
`d4d364427c31531358ce747b5931d4fa441e8e46002bf986626c69e923be2a39`.

- Generator `2f00d50a175fa087596b6164831ca2c8a55a168f103469ceb2a7dd924f5b78d0`.
- Derived helper `73553095e0ea15305e542b8dc76a5a58164ea976363a8719207ccb27461bd664`.
- Synthesis adapter `902a1fd050137dcfa471ae79ee8c86e6c3bb29c4862f3339c8f957b7e47a07f3`.
- Unchanged owner `d0f36ce2817ab20baaff8668b6743e367d296f7a60e714099fe69aa5b6912111`.
- Unchanged route `0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.

The following is a **proposal requiring separate source-specific approval**.
Its new-run directory is absent. All execution/temp paths stay on the recovered
non-/tmp disk; the frozen owner supplies the explicit SuSE Vivado environment.

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH \
  TMPDIR=/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-k1m1-physical-tmp-v1 \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
  /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-k1m1-physical-prepared-v1/run_exact_control_synthesis.py \
  --execute-synthesis \
  --prepared /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-k1m1-physical-prepared-v1 \
  --expected d4d364427c31531358ce747b5931d4fa441e8e46002bf986626c69e923be2a39 \
  --new-run /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-k1m1-synth-v1
```

Logical cost at D18 remains +107 register bits and105 mux bits before
optimization, not measured LUT/FF/BRAM/DSP use. The data/metadata capture
dependency is changed in RTL, but current-fault selector paths, mux feedback,
held-phase/input-guard paths and routing can still dominate. Synthesis and a
separately reviewed diagnostic route would be needed to measure actual mapping
and timing. The existing interface/CDC and full-receiver caveats remain open;
this preparation supplies no closure or promotion claim.
