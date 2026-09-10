# Retained-output physical review: timing FAIL, no deployment

This report supersedes the earlier "synthesis/routing next" status. The exact
retained-output runtime that passed actual vendor FFT run 13931 was synthesized
and routed without changing arithmetic, clocks, exceptions or safety limits.
Tool completion is not timing closure. No radio, PPU or production HDL gitlink
was changed for these runs.

## Measured results

Root independently passed 25 synthesis-preparation tests and eight
route-preparation tests before owning the two vendor invocations. Both original
process handles were consumed to terminal exit 0, without timeout or retry.

| Measurement | Synthesis 8892 | Route 5802 |
|---|---:|---:|
| Elapsed seconds | 207.887 | 74.278 |
| LUT / FF | 2239 / 4758 | 2334 / 4768 |
| DSP / RAMB18 | 21 / 15 | 21 / 15 |
| Setup WNS | not physical qualification | **-4.068 ns** |
| Setup TNS / failing endpoints | not physical qualification | -1952.796 ns / 1266 |
| Hold worst slack / failing endpoints | not physical qualification | +0.052 ns / 0 |
| Fully routed nets / routing errors | not applicable | 7224 / 0 |

The mapped design retains one FFT, three payload banks and two result guards.
Synthesis adds 294 LUT and 211 FF relative to L1, without extra DSP or RAM.
These are isolated-module resource counts, not spare capacity in a complete
receiver. Root checked raw utilization reports, all eight 20-path clock-pair
reports, inherited constraints, exceptions and the critical routed path.

The worst path is product-bank metadata bit 24, through input identity/fault
checks and cutover/common-fault logic, to forward result-guard descriptor bit
64's clock enable. It takes **9.493 ns** (1.758 ns logic, 7.735 ns routing), ten
LUT levels, against a 5.714 ns cycle. Both endpoints are in the 175 MHz domain:
independent-clock modelling warnings cannot explain away this failure.
The result is worse than earlier P1 (-1.492 ns) and L1 (-1.549 ns).

| Clock pair | Setup slack | Hold slack |
|---|---:|---:|
| 100 -> 100 MHz | +2.572 ns | +0.100 ns |
| 100 -> 175 MHz | -1.255 ns | +0.143 ns |
| 175 -> 100 MHz | -1.494 ns | +0.128 ns |
| 175 -> 175 MHz | -4.068 ns | +0.052 ns |

## Next implementation: preserve admission, shorten private control

Source review found that the guard already treats inactive descriptor capture
as private, but its top-level `job_valid` input contains the entire `job_ready`
qualification. This reintroduces the global fault tree into the capture enable.
The bounded next candidate separates a private descriptor offer from qualified
admission. Only invalid private descriptor bits may change on a rejected offer;
accepted metadata, activity, reservations, publication and real ACK must remain
unchanged. Active/retained descriptors must hold, including the ACK-clear edge.

Descriptor factoring alone is insufficient. Other top-20 paths reach kernel-ROM
enables via the input comparator, certified completion and cutover checks
(reported ROM paths include -3.933 ns and -3.913 ns). A separately tested
candidate will expose the literal cutover fault predicate restricted to zero
input strobes, and use it only in the already-registered input-complete return
phase. The full predicate, sticky reasons and unrestricted admission/config
checks stay live. This is phase-specific equivalence, not a delayed fault veto.
Known-complete input must imply zero certified strobes, and the selected
predicate must equal the original under that premise. Review identified an
important four-state exception: an X completion certificate and X strobe can
make the restricted predicate expose X where the full predicate returned zero.
The separately authorized candidate will therefore test a documented fail-closed
visibility rule: in enabled mode, the three public return paths require a
known-one completion certificate. This preserves known 0/1 behavior and makes
X/Z certificates unable to publish; it is not a claim of four-state equivalence.
The full diagnostics and all ACK paths remain literal. In particular, a retained
inverse ACK must remain possible during the next forward's incomplete input
epoch. The full predicate remains necessary at the final input's pre-NBA edge;
the closed-input premise holds after the registered completion update settles.

Only additive implementation and offline tests have been authorized so far.
Each candidate needs a default/inverse check and independent original shadows.
Another actual FFT run and physical build require review of the resulting
frozen sources. No timing success is predicted from a source-level cut alone.

The parallel checked-product design instead places checked metadata in an
owned, registered token before consumption. Its 3306 offline tests are useful
control evidence; its actual-FFT harness is still being prepared. It has not
been composed with retained scheduling or physically qualified.

Root has now independently passed its next **93 offline preparation/observer
tests in 5.48 seconds**, original process 16830 terminal exit 0. All 27 source
pins remained unchanged; four compiled-source manifests / 147 entries were
independently rehashed. These tests include literal disabled/enabled harness
elaboration, exact whole-source inverses, four healthy controller-actor pairs,
current/raw/reset cases, a continuous retained-owner watcher, the six pre-GOOD
metadata/ordinal/TLAST corruptions crossed with READY 0/1, and six deliberately
corrupted independent-observer evidence cases that each hit their named fatal.
An earlier independent 14-test binding-only replay passed in 0.92 seconds with
23 source pins unchanged; it overlaps the 93 and must not be added to its count.

The changed enabled contract distinguishes live VALID from retained ownership,
and actual ACK capacity from the scheduler's persistent receipt. Continuous
ownership checks run before the sampled edge update and after both settled fast
edges, not just at the end of a waiting interval. Active inverse corruption is
explicitly tested at the raw offered token before GOOD, not misrepresented as
the old post-GOOD wire fault. This authorizes preparing a source-specific actual
runner/result gate, **not** launching vendor simulation or claiming FFT evidence.
The absolute 5215-clock service cap and numerical/reference vectors are retained.

Raw independent receipts are in `checked-bindings-parent.oXANs8Wf` and
`checked-observer-parent.3BJkm3qG` under the recovery root below. The observer
source SHA256 is
`e0fc22ae7975db53790b0fc46115dbfe9ab3bbcf18c8c37784011d7248dd5647`;
the source-specific preparation helper is
`9d06f33d810eb69e9a9112c06756cadf3906c91935b80f53c98477c0904601e3`.

## CDC and board clock remain independent gates

Five critical CDC findings remain unqualified. Four arise from reset-idle
observations reading first-stage synchronizer bits as well as terminal stages;
another comes from decoded purge completion before synchronization. Legal
startup sequencing is not metastability or placement signoff. No CDC waiver
or timing exception was added.

The comparator retains independent rounded 100/175 MHz clocks, 114 inputs
without input delays and 124 outputs without output delays. These isolated
constraints are not board I/O qualification. The Pluto block design currently
requests 100/200 MHz and connects 200 MHz directly to `fft_clk`; the existing
100-to-175 MHz MMCM factory is not integrated there. The AD9361 delay reference
also uses 200 MHz and must not be casually retuned to implement the FFT clock.

Deployment remains gated by full receiver timing/CDC/reset/I/O closure, actual
60 MS/s RX calibration, continuous causal acquisition/native-fine scheduling,
independent 2.5 MS/s IIO recording and blind comparison, and the eight-target
120 ms-valid-dwell/300 s scanner. Only then: reversible `.18` canary followed
by `.17` using PPU over Ethernet. Isolated simulation is not RF timing accuracy.

## Frozen evidence and publication

Authoritative raw roots under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`:

- `retained-synthesis-parent.JqxbVb4y`: gate, owner execution, audit, synthesis.
- `retained-route-parent.I7WoLBxe`: gate, owner execution, audit, routed reports.

Synthesis DCP SHA256:
`d0a5e0c70d960ab6cf5c9b616610df88c2599ed73932f4fc9c8415c10f4ff840`.
Routed DCP SHA256:
`f93d0280e5ace9756fe99e1b118b8e12b57dd1b4b45bd14820aa70a1ad209cc8`.
Qualified v5 manifest:
`c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8`.
Prepared synthesis inventory:
`4a0bbd1b07ea94c51e5b001dbbd7c48b601d1abd8659253a318e3d3f6d357ecb`.

Portable physical evidence is published on
`codex/starlink-rx-only-do-not-merge-high-rate60-paired`, FW commit
`ef351ae1718350dfb5f595f546d94df578d411f9`, HDL commit
`667badf95a1739424e36c6a934bfbc8f9a69179a`. Both remote tips were verified;
root separately rechecked the FW remote tip. The package is
`artifacts/retained-physical-observations-v1.tar.gz`, 6,448,360 bytes,
SHA256 `39388ceeba0829e16b8a58fa83f7fc60f48b7baef9b6298115ee07a3a99cde83`.
Its collector verified 280 regular members / 279 receipts, both DCPs, raw
reports/warnings and source inventories. Root independently read the archive
from the exact published Git object, checked its size/SHA256, all 280 unique
safe regular members and every one of the 279 length/hash receipts, and
confirmed the recorded timing/deployment verdicts remain false. Full raw
products remain in recovery.
The archive does not silently reclassify the failed route or replace the
earlier passing simulation evidence.
