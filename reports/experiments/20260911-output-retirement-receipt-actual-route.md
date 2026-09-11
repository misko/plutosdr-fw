# Output private-slot timing closes; publication and receiver gates remain open

The output-stage occupancy endpoint improves from **-1.304 ns to +1.432 ns**.
Total negative slack and failing-endpoint count nearly halve, but whole timing
still fails. **No receiver promotion or radio deployment.**

## Implemented and verified

Actual bank publication, current fault/framing checks, retained-controller
acceptance and reader release remain unchanged. Only private final-slot
retirement uses the bank's registered request/ACK ownership, holding the final
word one extra healthy edge after publication. No logical register is added;
nonfinal refill is unchanged. All 38 parent runtime modules remain byte-identical,
with one derived top added. This is not a second payload bank or a changed FFT.

The final regression passes **1,869 tests**. Coverage includes exact inverse RTL
transforms, 1,024 four-state readiness combinations, real mailbox data/metadata/
framing/reset checks, unsafe mutations and source-matched route admission.

The actual generated FFT matches all **64,512 numerical words** and retains
**4,178 service clocks / 23.874 us at 175 MHz**, below the 5,215-clock budget.
All **71 actual fault/reset/delay cases** pass: 65 inherited plus six new output
boundaries. Healthy observer: 88,545 checks / 18 publications / 18 retirements.
Full auxiliary observer: 750,164 checks / 97 publications / 93 retirements /
97 extra holds. Private cancellation during fault/reset is not normal retirement.
Each new boundary recovers 512 fresh correct reads and one actual reader release.

The six boundaries cover a consistent 128-edge pause, both raw resets during
the extra private hold, late unexpected FFT status, final metadata corrupted
before actual certificate generation, and missing publication after private
replay consumption. A shorter actual-FFT run passes all six before the full run.

Failed evidence is retained, not counted as passing: recursive harness entry,
a declaration-counting test bug, a forced register that remained low after
release, and certificate-only corruption that contradicted the independent
word checker. Parent/candidate actual probes show identical rejection when
private replay is consumed but bank publication is deliberately withheld.
The final tests preserve these safety checks; no current fault veto was removed.

## Physical result

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no exceptions
or relaxed clocks. All 8,561 nets route without errors.

| Metric | Descriptor parent | Output retirement |
|---|---:|---:|
| WNS / TNS (ns) | -1.304 / -663.577 | -1.152 / -343.090 |
| Same-domain 175 MHz WNS | -1.304 ns | -1.095 ns |
| Failing setup endpoints | 1,647 / 14,493 | 867 / 14,505 |
| LUT / FF | 2,741 / 5,907 | 2,689 / 5,912 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Output occupancy passes +1.432 ns; product occupancy/identity pass +0.866 /
+1.035 ns. All 70 descriptor CE pins pass (worst +1.440 ns) and all 70 data
pins pass (worst +3.155 ns).

Worst internal path is product-bank metadata bit 29 through handoff/current
cutover checks to its publication request: **-1.095 ns**, eight LUT levels,
6.756 ns data delay, 75.711% routing. Output publication remains **-0.831 ns**
including its physical replica. The first probe measured only the original
output toggle (-0.220 ns); the second includes both pins and supersedes that
limited observation. Neither result changes constraints or the routed checkpoint.

Overall worst is held output descriptor bit 60 crossing into slow metadata,
-1.152 ns under the unchanged OOC clocks. Hold +0.070 ns and pulse +1.830 ns
pass; zero combinational/latch loops. 114 inputs / 124 outputs remain unqualified.
CDC: nine CDC-3 / 209 CDC-15, no CDC-10. Scalar fault directly feeds its
synchronizer. Reset-release/output-request replicas and a source-bank metadata
destination replica remain part of unqualified full-board CDC review.

## Next gate and retained checkpoint

Investigate the actual product-bank publication cone, including held-bank
metadata validation feeding current cutover control. Preserve current publication
vetoes, metadata ownership, actual request/ACK receipts, quarantine and recovery.
Run focused protocol tests before the full campaign, then route and measure
all physical publication replicas. No blanket waiver or omitted fault check.

Branch `codex/starlink-rx-only-do-not-merge-output-retirement-receipt`:

- FW `32a69f329c707dfd48be3da4f9370e707de5f72f`.
- HDL `e56d6028465712f639efe704702f355c17fe8b1e`.
- Main inventory `10f92347fddc5e2a150f1fa852418211b58a3f168bc07b782fdf2bb2c10ac767`.
- Accepted auxiliary inventory `3abec4b232d23c3c6cbe40f886fa13167c3053d110e7fae50becf047581ac29b`.
- Routed DCP `2466665a6e1c63f8ffb9edf9dbc65041c5128652c647c48647ad6806d3205374`.

- [Verified archive](20260911-output-retirement-receipt-evidence.tgz):
  **64,329,139 bytes / 196,711 members**.
- Archive SHA256 `2bdf5eaeb73fbda810b7f80f42ae4a8b4cc6cbc2433b9216792bb07691f173a3`.
- [Independent sequential read-back receipt](20260911-output-retirement-receipt-evidence-stream.json).
- Latest branch FW `70c41153305c96113ddb3f09d1ed273e58ad2783` adds the read-back
  verifier and seven passing [verifier tests](20260911-output-retirement-stream-verifier-tests.xml).
- Verifier SHA256 `c03e82ec7454df7fccba72a20fc958dc839d566094aaa6dfd6233e19b9456b88`.

Every payload is checked against its manifest size/SHA256, with exact member
inventory, regular-file checks, gzip CRC and stable whole-archive SHA256. The
original archive writer completed its output but its random-access read-back
was slow at this inventory size. After the independent complete verification,
that redundant verifier was stopped (exit 143). The archive was not rewritten
or truncated; the primary copy compares byte-identical. The independent receipt,
not a nonexistent successful original-writer receipt, is the verification proof.

Primary HDL stays `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Native 60 MS/s
fine search and independent 2.5 MS/s inspection remain required and unchanged.
Full receiver integration/timing/CDC/reset, actual calibration, continuous RX
and real IIO/Ethernet remain mandatory before reversible PPU deployment to .18,
then Ethernet-only .17. No radios or PPU/main were touched; .14/.20/.21 excluded.
