# Product-buffer identity stage: component proof and integration gate

Branch: `codex/starlink-rx-only-do-not-merge-product-validation-stage`.
FW `7d8550738`; HDL `1a9841dd868e4477f9928554fe07cda065af94dd`.
**15 tests pass. Actual FFT integration, synthesis and routing are still pending.**

The parent remains the timing-failing forward-receipt candidate: -1.567 ns WNS /
-497.191 ns TNS / 681 failing endpoints. All 19 compiled runtime modules are
unchanged in this component checkpoint; no timing improvement is claimed.

## What was implemented

A private one-word stage retains product data, metadata, ordinal/LAST and a
registered identity result. An actual-mailbox variant uses that result instead
of a wide metadata comparison, while keeping its original position, LAST,
explicit-publication, reset, RAM ownership and reader-ACK logic. A full source
inverse confines the mailbox delta. The certificate must remain associated
with the same retained word and reference epoch; it is not independent authority.

The buffer loads its reference metadata when the first word enters RAM. The
stage pauses refill on that one clock so the second word compares against the
registered reference. This removes the need for a 70-bit write-through mux.
The earlier write-through variant also passed; both versions' evidence is kept.
The complete service-time cost must be measured with the actual FFT.

An unpublished LAST remains in the private slot until publication is authorized.
Repeated private RAM writes do not consume that slot or count as reader ACKs.
Fault or reset cancels it without publication. No aggregate fault is simply
delayed past a commit edge.

## Verification

Final suite: **15 tests in 3.07 s**. The actual mailbox is checked against the
original comparator mailbox on the same staged input, with **57454 known-traffic
control/payload comparisons**. Unknown identities require fail-closed behavior,
not general four-state equivalence.

- **6144 exact reads** across 12 correct 512-word blocks, with ownership return.
- Continuous refill, source gaps and deterministic writer stalls.
- A **200-clock unpublished-final hold**, with no early request or read visibility.
- **420 metadata faults:** all 70 bits, both second and final word, known-bit/X/Z.
- Six ordinal/LAST faults at first, middle and final word.
- Eight held-final reset/abort/unknown-control cancellations, each followed by
  fresh correct-block recovery.
- Actual mailbox rejection of 0/X/Z final certificates and unsupported modes.
- Seven unsafe variants rejected, including missing first-reference pause,
  dropped unpublished LAST, unchecked identity and lost reset/abort.

Mixed-test totals are 118802 simultaneous refills, 297 held-word checks and 444
reference pauses. These include negative prefixes and are not RF frame rates.
The stage declares 119 state bits; mapped resource usage is not yet measured.
There is no new DSP/RAM declaration or clock domain.

## Next: actual FFT integration and route

Connect arithmetic READY to actual private-slot acceptance. Use the mailbox's
held metadata and its real metadata-load pulse for the one-clock reference
pause. Keep RAM-write acceptance distinct from final-slot retirement, and add
stage faults consistently to existing current/sticky admission and fault checks.
Update numerical logging to the actual new producer acceptance edge.

Then test first-reference stalls, corrupted metadata, held-LAST faults, both
reset sides and fresh recovery with the real FFT and buffers. Require the
64512 indexed numerical results, both bounded campaigns and the unchanged
5215-clock coarse-service gate before routing under the existing constraints.
Do not extend the main deadline or remove current-fault publication vetoes.

Native 60 MS/s fine search and 2.5 MS/s inspection remain unchanged. No radio,
PPU/main or primary production HDL change. Full receiver timing/CDC/reset/board
clocks, real 60 MS/s calibration and sustained Ethernet/IIO still precede `.18`
canary and `.17` PPU Ethernet-only deployment with rollback. Final acceptance
remains 300-second scanning, 120 ms valid dwells and blind host GLRT.

## Preserved evidence

[Read-back verified component packet](20260911-product-identity-components-evidence.tgz)
and [receipt](20260911-product-identity-components-evidence.json): **155421 bytes,
225 members**, every member verified. SHA256:
`84108474bab4cdffd0f03ea0cf8d6f9b2f12fdcdf2a160a153bf23e9dd29b102`.
Includes all four test versions' generated sources/logs/XML, current source,
the original mailbox and the prepared 19-module parent runtime.

Worktree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-validation-stage-worktree-v1`.
Test scratch: `/dev/shm/starlink-product-stage.vi9yss`; no live build remains.
Primary production HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
