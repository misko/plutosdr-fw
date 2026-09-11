# Registered input identity: actual FFT integration and routed result

FW `6af13552f961eba23e0caeea4d2782773fd72a7c`, HDL
`73363ec5e2a865d0b3d63cfb5c5d0277d33d47d0`, pushed on
`codex/starlink-rx-only-do-not-merge-input-validation-stage`.
This supersedes the component-only status on that branch. The actual generated
FFT and mailbox buffers now use the registered input stage. **Functional tests
pass, but timing still fails: no promotion or deployment.**

## Implementation and verification

Bank acceptance captures one private word plus its 70-bit identity-check result.
The checker certifies actual FFT consumption; offered-beat summaries use that
same staged stream. A core-reset-scoped LAST-captured flag stops prefetch into
the next bank. The engine retains its input reservation until the buffered final
word is actually consumed. Stage control faults participate in existing current
and sticky quarantine, including the completed-input view. Publication, real
reader release, certificates and coordinated reset are preserved.

A complete source inverse limits top changes to this integration and preserves
all other original runtime modules. Two modules are added to the compiled
inventory (19 total, including the unused original checker). The checker inverse
preserves all non-identity equations. Actual tests check descriptor identity on
capture, occupancy, held word/evidence and final-word reservation.

- **489 regression tests pass in 71.68 s**, plus eight evidence-auditor tests
  and one full V1/V2 boundary-bench inverse: **498 passing cases** across runs.
- V1 actual FFT passes in 171.73 s; extended V2 in 188.26 s. All **64512 numerical
  records** match the independent reference. The CSV changes due to retiming;
  byte-identical execution is not claimed.
- Service is **3661/3661/4928/11728/3661/3661 clocks**, versus parent
  3659/3659/4927/11727/3659/3659. Normal cost is two clocks. The deliberate
  9000-clock reader stall remains excluded from the unchanged 5215-clock gate.
- V2 adds six real-FFT cases: wrong/unknown identity in both phases at early/final
  positions, and fast/slow reset with the final inverse word buffered. No invalid
  FFT delivery or completion, no stale publication, and fresh 512 reads/one real
  release are required and observed in every case.
- V2 scoreboard: 85143 captures, 85137 private retirements, 85307 held-valid
  observations, 164 buffered-final ownership checks. Counts include cancelled
  work, not RF frames. Existing fault/reset/queued-publication tests also pass.

The first regression had 487 passes and two historical source-equality failures.
Both assumed an unchanged top. Their historical comparisons are now parent-pinned;
live predicate/order checks remain, and the new complete inverse checks the actual
top delta. The failed run remains recorded, not relabelled successful.

## Physical measurement

Synthesis completes in 96.83 s; unchanged routing in 50.84 s. Source/checkpoint
audits pass with no routing errors. This does not imply a timing pass.

| Metric | Retained guard facts | Registered input |
| --- | ---: | ---: |
| WNS (ns) | -1.340 | -1.503 |
| TNS (ns) | -463.636 | -521.325 |
| Failing setup endpoints | 821 | 896 |
| LUTs | 2808 | 2724 |
| Flip-flops | 5691 | 5670 |

Both use 21 DSPs and 15 RAMB18s. New design has 8319 fully routed nets; hold
+0.058 ns and pulse +1.830 ns pass. The diagnostic OOC build still reports 114
unconstrained inputs and 124 unconstrained outputs. No board/full receiver signoff.

The worst path moved to **output-bank fault Q -> adapter/ledger fault handling ->
destination availability -> scheduler engine-metadata CE**. Seven levels,
6.928 ns data delay, 5.604 ns routing (80.9%), and a final enable with 72 loads.
The input identity comparator is no longer the worst reported path. However,
overall timing is worse than the retained parent, so retain both references
without claiming that the new one is timing-qualified.

## Next step and deployment gates

Separate private scheduler descriptor capture from the wide capacity/quarantine
enable. Investigate tracking selected metadata while WAIT_BANK, then freezing
it when ownership advances. Retain the original admission, phase/lease and
current-fault decisions. Prove that extra private captures during cancellation
cannot configure/start the FFT or publish; check healthy transfer equality.
Then repeat actual FFT, boundary/service tests and unchanged routing. This
follow-up is not implemented yet.

No radio, PPU/main or primary production HDL changes. Native 60 MS/s fine search
and independent 2.5 MS/s CI16 IIO inspection remain untouched. Full receiver
timing/CDC/reset/board clocks, sustained capture, real 60 MS/s calibration and
Ethernet/IIO tests still precede reversible `.18` canary, then `.17` PPU
Ethernet-only deployment with pinned rollback. Final qualification remains
300-second scanning, 120 ms valid dwells and blind host GLRT comparison.

## Evidence and continuation

[Verified archive](20260911-staged-inputidentity-evidence.tgz) and
[receipt](20260911-staged-inputidentity-evidence.json): 16553957 bytes, 7539
members, all read-back verified. SHA256:
`a2e27bd55f7320ab45fecd6c20927f1247c6aacb6d4832703b7f19703e9c4013`.

- V2 prepared inventory: `b8fa61a47a66e7363d67227a197176f8145e3764bcf97551769328ae68b28e66`.
- V2 CSV: `44fae7467811a9e0f71d63330ee5c868c676c9a4c0ffb29f6f649be23e003279`.
- Synthesis: `8d4ffe35a99a79d2a59cc5a719263834c2b712aae24e292d7e3c11686bb51987`.
- Routed DCP: `35bc4a1bb33ea81220194d7063553eef4b18470ad7fe31555c6eefdd5e0730fd`.

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/input-validation-stage-worktree-v1`.
Artifacts: sibling `staged-inputidentity-*` directories/files. No live build remains.
Both completed regression scratch trees were compressed, byte-compared, then
their unpacked generated copies removed to recover disk space. Full local
archives (including generated convenience links; do not blindly extract them):

- V1 `staged-inputidentity-regression-v1-complete.tgz`, 138619522 bytes, SHA
  `578352bbaa058874a3406ae7452d9537defb1d2e47bd5ad4e3cb78ecf2cfbab7`.
- V2 `staged-inputidentity-regression-v2-complete.tar.xz`, 50804564 bytes, SHA
  `710e1207abcf412dbf36aeecca790441fdabe1e69568a2512b6df911221375e9`.

Sources/logs and curated evidence are preserved remotely; full scratch archives
remain local and recoverable. Primary production HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
