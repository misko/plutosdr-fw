# Private kernel ordinal: tests pass, reference still routes better

Tested independent private kernel-index advancement on the **private-capture
reference**, FW `fcc3dc202`, HDL `c25126a2e`, which routed at -1.969 ns. This is
not combined with the later staged-final regression; that work remains preserved
on its existing branch. No firmware was deployed.

The new separate FW/HDL branch is
`codex/starlink-rx-only-do-not-merge-kernel-ordinal`, in worktree
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/kernel-ordinal-reference-worktree-v1`.

## Implemented and verified

The guard supplies a private forward offer from an owned, structurally qualified
return. A held final word still waits for status/exponent/final-fence checks.
Only the ROM's hidden expected-bin counter advances from that offer, using real
capacity and registered epoch-quarantine gates. Public acceptance, per-bin
sequence/metadata checks, coefficient validity, error flags and block completion
retain their original qualified paths. A private advance rejected by a current
fault cannot be reused before common reset/flush.

- **64,512 actual FFT numerical records match** the pinned reference. The CSV
  is byte-identical to private capture, including all six contexts. Service
  remains 3659/3659/4927/11727/3659/3659; the unchanged 5215 limit passes for
  qualifying contexts. The deliberate 9000-clock reader stall has no service claim.
- The entire previous reset/fault/admission/completion/replay/writer/capture
  campaign passes. New actual cases cover vendor fault, product-bank framing
  fault and duplicate status on a private offer, late legal forward status and
  16-clock held-final backpressure. Fault cases observe private advancement
  without public acceptance or later publication/reuse/reads/release. Healthy
  cases each return 512 correct reads and one real release.
- Every healthy handshake agrees with public acceptance; every live cycle
  checks exact index advance/freeze. Coverage: **9216 advances / 98,246 holds**.
  Original descriptor capture/hold, full-width timestamp and stopped-reader reset
  checks remain. Total receipts including aborted jobs: 105 admissions / 77 closes.
- **397 combined tests pass in 51.74 seconds**: 382 private-capture baseline
  tests plus five ROM and ten evidence-parser tests. The ROM comparison checks
  4096 lookups, malformed data, stalls and flush against the original pinned ROM.
  A private-only unpublished offer and fresh recovery pass; four broken ordinal
  variants fail. This suite is distinct from the staged-final branch's suite.
- Actual/synthesis/route complete in **116.52 / 100.07 / 52.15 seconds**. Before/
  after sources and checkpoints are unchanged. The independent physical audit
  confirms the measured reports below, not a timing pass.

## Routed comparison: not promoted

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Private-capture reference | **-1.969 ns** | **-813.676 ns** | **914** |
| Private ordinal on that reference | -2.347 ns | -967.661 ns | 1093 |

1093 / 13765 setup endpoints fail. Hold +0.071 ns and pulse +1.830 ns pass;
8347 nets fully route with zero errors. Resources: 2748 LUT / 5653 FF / 21 DSP /
15 RAMB18. Device, actual FFT, diagnostic 100/175 MHz clocks and recipe are
unchanged. Five critical CDC findings, 208 warnings and 114/124 unconstrained
I/O remain. No timing waiver or full receiver/board signoff is claimed.

The worst endpoint moved to the inverse guard's `fault_reasons_reg[0]/D`, reached
through held phase → input metadata selection/comparison → certified input →
cutover fault → guard fault accumulation. It is a 10-level, 8.009 ns path, with
6.313 ns routing. The forward guard's equivalent bit follows at -2.315 ns.
This candidate therefore remains experimental; the private-capture reference
is still the better measured design.

## Next step and full deployment gates

Investigate source-local fault aggregation rather than another isolated private
counter change. Existing offered-input summaries shorten some common control
paths, but detailed guard faults retain the chained external predicate. Any
replacement must prove equivalence, preserve exact fault reasons/unknown-input
handling, and retain immediate publication/ACK vetoes. Do not simply delay the
whole fault signal. Test against the better reference, then reroute.

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required. Full receiver route/CDC/reset/board constraints, sustained
capture and actual 60 MS/s RX calibration precede `.18` reversible canary, then
`.17` via PPU Ethernet with pinned rollback. Final verification remains the
300-second scan, 120 ms valid dwells and blind host GLRT comparison. No radios,
PPU, main branches or primary production HDL gitlink changed in this increment.

## Preserved evidence and commits

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Folders: `staged-ordinal-prepared-v1`, `staged-ordinal-actual-v1`,
`staged-ordinal-synth-v1`, `staged-ordinal-route-v1`; all runs terminal.
Inventory: `727eaacff7b4781dbf04672bdd90681033906c9591d7cd669378e5c50c4ac1ed`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Synthesis DCP: `0929abdda3a30213837631513905a02c4b364075004dfe25ab766a700b19a23f`.
Routed DCP: `8ecbf98aa360e8d0849259bc8b8243a36ea85a1c1578fe33f453bddebfdfe9d6`.

[Verified source/results archive](20260911-staged-ordinal-evidence.tgz):
15,518,488 bytes, 7224 regular members, all read-back checked by SHA256 and size.
SHA256: `21b3b31f7b3d9173e5ee8d32c338c0a0ff25940f91d25e12ab2b49820b71a9c5`.
Includes frozen runtime/bench/vectors, actual logs/CSV, synthesis/routed reports
and checkpoints, tests, original ROM and private-capture route audit.

Implementation pushed to `codex/starlink-rx-only-do-not-merge-kernel-ordinal`:
FW `98c56066c809e84ab446e5b001ab5f0815cd9105`,
HDL `379026ea55f91d9f79116a4c493aeb4bbd65595f`. No merge into main.
