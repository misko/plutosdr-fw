# Synthetic520 concurrent-source fixture: offline gate only

The new explicit `520-pss` profile has independently regenerated numerical
goldens and passed offline arithmetic, integrity and Tcl admission tests.
**No actual175/200 MHz RTL simulation of this fixture has run.** No synthesis,
route, receiver integration, radio, PPU or remote action occurred in this stage.
This is a static synthetic PSS, not causal acquisition, RF lock,750 Hz accuracy,
or production timing/resource qualification.

## Isolated source and behavior

Worktree: `/tmp/starlink-coarse-alternatives.Y3JzOI/bank-native-paired`, with its
independent HDL worktree on `codex/starlink-rx-only-do-not-merge-bank-native-paired`.
Starting pins were FW`f1ace9c6809ff13bc1fe07573d71232b1999f4c2` and
HDL`8e2d11a8fabcfea58e28d1b469c93cdc43f5fd24`. New HDL test-only commit:
`5ad9ba4a2ae7f196cbd44066eec725090cd76cea`.

The new module `tests/starlink_oracle/bank_native_true_pss.py` does not modify
the old native oracle, original pipeline generator, paired-pilot generator,
legacy paired bench or any product RTL. The only HDL edits add a default-off
bench profile and its explicit runner admission/terminal checks. Default447
still has the strict positive overlap gate, and its previously failed overlap
receipt remains failed. Original520 remains the distinct arithmetic profile
whose winner is−17; it is never implicitly upgraded to this new fixture.
All old manifests, sources, archived runs and goldens remain byte-unchanged.

The original1406 numeric source is reconstructed and checked against its
immutable SHA. Only numeric`[520:586]`, paired4096`[1288:1354]`, is replaced
with the independently generated upper-edge zero-CFO66-tap Q15 PSS. Exactly66
source words differ. All768 prehistory words, tail words, and original PSS
controls at100,447,1000 are preserved. The4096-word source still feeds both
native and coarse/pilot branches at the original15 MHz sample boundary.

| Identity | Original520 arithmetic | New synthetic520 |
| --- | --- | --- |
| Explicit runner profile | `520` | `520-pss` |
| Request ID | `15005200` | `15005201` |
| Coefficient generation | `15000001` | `15000002` |
| Coefficient bytes/energy | unchanged Q15 /1073742825 | same bytes/energy |
| Independent winner | −17 | 0 |
| Fixture ID | original paired smoke | `bank-native-original-overlay-520-pss-v1` |

Native coefficient files retain `iiiiqqqq`; the public AXI write swaps to
lowI/highQ. Source files remain `qqqqiiii`. Tests compare the complete packing
and reject a swapped coefficient bank even with a rehashed receipt.

## Independent numerical gate

The explicit `Model18` generic override mirrors the reviewed production-map
model configuration (`9,1,0,0,18,16,1,BFP,1`); it does not mutate the base
model's24/23-bit globals. The separate production-map worktree was read-only
reference material, not a runtime import or modified fixture. Every one of
the three nonperiodic512-word blocks is transformed separately.

The installed Vivado2022.2 XFFT9.1 C-model archive hash is
`0f264e0e15f93fcf5df9c60e715fe51c9bcd9639b578a5ae67be4df5cf2d5f87`.
The extracted model/GMP library hashes are in `score/pipeline_vectors.json`;
proprietary libraries are not archived. The fixed-template FFT is independently
derived with schedule(2,0,0,0,0) and byte-compared to the original18-bit kernel.

The offline bootstrap byte-matches all seven original numerical files plus
the original kernel. New vectors contain1536 forward,1536 product,1536 inverse
words and1341 scores. Exact signed ties-even product division by2^18,66-tap
energy, BFP scale and69-bit saturating numerator preparation are explicit.
Tests independently check every product, energy, inverse-to-score scale and
score with Python integers/Fraction, not RTL results. Blocks0 and2 remain
byte-identical to their original forward/product/inverse vectors; block1 is
new, not a periodic replication.

New forward exponents are[5,5,4], inverse[3,3,4], power shifts[30,30,30].
There are no FFT/product overflows or69-bit numerator saturations. All four
PSS starts100,447,520,1000 score255. The separately serialized447-word map
is exactly `scores[k] + scores[k+447]`, selecting894 ordered scores; the full
1341-score offline vector must not be misreported as the paired bench's
boundary-stop score count.

The integer15→2.5 MS/s pilot oracle independently regenerates512 words,
exactly2048 bytes, from the same modified4096 source, with no saturation.
Pilot output/index metadata retain the original support lattice, but the
expected pilot sample bytes change. The native oracle checks all61 qualified
tuples against the DSP reducer's signed39 correlation, unsigned38 Ex,
unsigned31 Eh, positive energies and zero saturation bounds before exact
strict P/Ex ranking. A separate Python-int/Fraction test checks all61 tuples,
all intermediate signed48 per-tap bounds and all26 packet words. The exact
winner is0, Re=Ex=Eh=1073742825, Im=0, normalized ratio1.

## Support, command lead and resource boundary

`FIRST = 8589934576`. Native center is8589935096, capture is
`[8589935064,8589935194)` = source offsets`[488,618)`:130 words,66 taps,
raw lags−32..32 and qualified lags−30..30. The inserted PSS occupies
offsets`[520,586)`, entirely inside that capture. Selected coarse maps cover
`[FIRST,FIRST+894)` candidates and full actual FFT input envelope
`[FIRST,FIRST+959)`, enclosing the native capture. The independent pilot's
center bounds are`[8589934081,8589937148)`; its raw support is
`[8589933812,8589937417)`, also enclosing the selected coarse input envelope.

The source clock remains a true15 MHz clock with continuous valid on healthy
enabled edges, separate100 MHz AXI/coarse and175/200 MHz FFT clocks. Public
AXI command issue is afterFIRST+16. The unchanged observed-admission deadline
isFIRST+128, giving minimum capture lead `488−128−1 = 359` source samples,
well above the strict64-sample gate. Source indexing, timestamp=index,
inactive configuration epoch and monotonic restart are unchanged; no source
counter compensation or valid-gap counter suppression is introduced.

The prior arithmetic520 fixture actually admitted atFIRST+26 (461-sample
lead). Its first actual forward FFT input was at sourceFIRST+590 after the
outer512-word bank's100 MHz fill, not immediately after source512 was seen.
Its native capture488..617 overlapped actual FFT RUN_JOB for319 fast cycles
at175 MHz and366 at200 MHz. These are **prior-profile observations**, not new
fixture measurements or guaranteed bounds. The new profile retains strict
positive capture/FFT and native-compute/coarse-active/pilot-accept gates;
new actual175/200 runs must demonstrate them again before any concurrency
claim. Initial447 remains a negative example of why the outer bank lifecycle
cannot be omitted from this calculation.

No runtime bank, FIFO, tap count, FFT, DSP reducer or scoring hardware changes.
The existing source/product/egress banks and native130-word capture remain
unchanged. New files are offline/testbench expectations, not synthesized
memory additions. This supports only unchanged structural resource scope;
there is no new combined-resource total, placement, routed clock or throughput
qualification. Existing physical timing failures are not waived by this test.

## Frozen evidence and executed tests

Live cohort:
`hdl/library/starlink_pss_acquisition/build/bank-native-true-pss520-cohort-v1`.
Portable archive:
`reports/experiments/20260910-bank-native-true-pss-offline-frozen.tgz`, SHA256
`81309199248250904267a9cc7f15bd28156b2fbd5159a4cb778245479be5d8e7`.
It has46 safe unique members,42 files:24 cohort files,12 runtime Python files,
three policy files and three HDL runner/helper/check files. The cohort's23
payload hashes plus12 runtime hashes were checked against the archive.

| Frozen artifact | SHA256 |
| --- | --- |
| `fixture.json` | `aa4330480879e5f44abdfeb34b5ddeca098f1b22352715743f0db32e6672de81` |
| Numeric1406 source | `0bef7049693657b1f058a42495fe3ed9823001d4542b0e41432984649707f4b4` |
| Paired4096 source | `dd331abb7a7347a361ab81c39228ef2b3758e308fac41da34806ad2bcf098099` |
| Forward1536 | `7c16b3de1a707d6925ece52f1f25de89436dc03de745866b3280911e3cd313a8` |
| Product1536 | `26045f0a0b72fd598eae4d24e89b69af5420085536dd1fa381fc6354e827334b` |
| Inverse1536 | `3a64a10a9bd0f4b78eb65e8f4b2b6f6a38bcaee11cac74ec275a281991649de6` |
| Scores1341 | `cdc83107ab52f5756f3bb79c4663b7a10dae3234b529996c25c2b4a142b2a057` |
| Map447 | `0a6a5ab38faf6d4b4cc7636eea859fc16f80c925c1c5d3b5554b94f74769fe16` |
| Pilot2048 bytes | `3c754ff064c7fbfd4bcbe4560353f14fba0d2fd7cde68b5c4bba3a49681f8108` |
| Native26 words | `f8488f2393a08d17e57d8d1ec0e59b1369f0357de37934c6ed0dec66778a9699` |

All other vector/exponent/kernel/source hashes are in the frozen manifests.
The new preflight recomputes every cohort byte, including full C-model traces;
hashing a stale original golden cannot qualify it. It requires one explicit
score/pilot/native cohort, rejects missing/extra files or directories and
symlinks, and refuses overwrite. Its deterministic12-module runtime import
closure includes both package initializers, transitive imports, the new module
and pilot oracle. No policy module is imported by that runtime oracle. Every
cohort file, dependency and policy/helper source is copied and hashed before
project creation; original447/520 retain the existing10-module closure.

Executed final command used the repository Python interpreter:

```text
python -m pytest -q tests/test_starlink_bank_native_true_pss.py \
  tests/test_starlink_bank_native_paired.py \
  tests/test_starlink_paired_realtime_psma_stop_policy.py \
  --junitxml=reports/experiments/20260910-bank-native-true-pss-offline-policy-v2.xml
```

Result:244 PASS in9.80s; Ruff PASS. The earlier242-test XML is preserved
separately; two later tests cover empty-directory inventory and whole-bank
coefficient swap rejection. The initial119-test run passed its tests but the
combined shell returned1 for two lint issues, corrected before the final runs.
Actual Tcl runner tests stop intentionally at a stubbed `create_project`
admission fence—**they do not invoke Vivado, elaborate RTL or count as an
actual-core simulation**. They exercise both intended175/200 profiles, all
relative input/output paths, full pre-project freeze, old/new cohort mismatch,
old goldens on new source, packing, exact profile receipts and post-PASS late
FAIL/FAULT/Fatal/ERROR rejection. The inherited stop/retention and strict
overlap acceptance checks remain in the generated bench.

Standalone offline generation and independent verification each printed the
exact `BANK_NATIVE_TRUE_PSS_ORACLE_VERIFIED ... profile=520-pss winner_lag=0`
receipt. Full three-block C-model source is nonperiodic. No RTL output was
used as an expected value.

## Next gates, not performed

Parent review must authorize the fresh175/200 actual-core runs for this exact
frozen cohort. Then combined expired-native, source-gap and FFT-only-reset/
vendor-fault epochs remain separate negative-case work, not implemented here.
The new synthetic static anchor also does not replace a causal coarse-to-fine
future command test. Public high-rate30/60 conditioner/kernel/profile guards,
native sparse search on original-rate samples, independent2.5 MS/s pilot IIO,
full receiver timing/CDC/IO constraints, RF accuracy, network `.18` before`.17`,
eight targets/120 ms dwells/300s remain open deployment requirements.
