# Concurrent true-PSS evidence and remaining physical timing failures

## Accepted bounded true-PSS concurrency evidence

Parent read the complete independent oracle, tests, runner delta and offline/
actual reports before accepting the new explicit `520-pss` profile. Parent's
offline244-test replay passed in9.65s. Independent full-cohort regeneration
passed; all24 frozen cohort files and12 runtime Python dependencies matched
the offline archive. The old447 and520 profiles/goldens remain unchanged.

Both approved first-attempt actual-core runs exited0: original53217 at175MHz
and88546 at200MHz, true15MHz original sample source and100MHz AXI/coarse clock.
Parent independently checked every108-file frozen inventory at both clocks,
all52 public packet-word reads/run, all512 ordered pilot words/newest indices,
every required terminal marker and all238 safe unique archive members against
their hashes. Full report: [actual results](../../docs/starlink-bank-native-true-pss-actual-20260910.md).
Archive SHA256:
`30f26c1925c96b8f912b1d13ab62787fed99214ec67c4204c42b8706417bf8db`.

Each run checks the exact synthetic zero-lag native packet,130 raw capture
samples,894 coarse scores,447 map words and2048 pilot bytes. Capture overlaps
actual FFT processing for319/366 fast clocks;842 canonical-input observations
witness native computation concurrent with coarse activity and pilot acceptance.
These are not pilot-output counts, causal acquisition, live timing accuracy,
every-frame throughput or60MS/s receiver qualification.

The additive tests/oracle/evidence are integrated at primary FW
`72fa003a3ef35691ee653b5698b97694adfa6bde` / HDL
`b49553c16319f59ad8d7b44fd24c494f96eba142`. No runtime RTL changed. All415 combined
primary tests passed in8.03s across native true-PSS, native paired, production
map, paired PSMA stop and realtime-result verification. Primary's oracle also
independently recomputed and accepted the frozen actual-run cohort unchanged.

Next authorized work is additive implementation/offline tests for a late native
command while coarse and pilot continue. It must prove actual public-command
handshake, late rejection, zero admitted/captured/published native work and no
IRQ, while coarse/map/pilot still match the independent healthy goldens. Public
result availability/counters must prove emptiness; do not attempt to read an
unavailable packet whose read response is gated. Actual negative simulations
require review of the frozen test/event contract first. Gap, FFT-reset/vendor
fault and causal future-command epochs remain separate required work.

## Forward-retirement physical counterevidence

The separate `codex/starlink-rx-only-do-not-merge-completed-input-fence` branch
preserves functional FW2d8e24fe5/HDLb978ebc86 and the final physical archive at
FW `bda25bb5e0a5e98b7a3c1f4921618d040f709bfa` / HDL
`dec20d6371f2d77b6e09c4bcdda2f3d7f8715776`. The runtime variant is NOT integrated
into primary. Parent read the complete physical report, exact critical paths
and additive read-only inventory helper, checked all78 archive SHA entries and
all five original DCP path hashes. Both checkpoints remain unchanged.

Source/synthesis DCP SHA256:
`9a141a44350da32e3ca2609b7e9911b2c41e5e9f4377c5edf3021ac459841941`.
Routed DCP SHA256:
`b8e20f1bebd96dcf375f81c14e96adee2f6ad9d7dc8802ff035525e9676b872c`.

The one unchanged100/175MHz trial fails175MHz setup at−1.907ns, hold+0.071ns,
TNS−663.483ns/664 failing endpoints.100MHz setup is+2.400ns. Routed area is
2013LUT/4547FF/1094slices/57control sets/21DSP/7.5BRAM. No placement retry,
clock relaxation, false-path exception or receiver/radio operation occurred.

The intended output-bank current-framing/held-metadata fan-in is absent from
all64 kernel expected-next enables in BOTH checkpoints. This removes only the
specific dependency, not all ownership/sticky-fault/descriptor dependencies.
The actual remaining limits include:

- Held phase through input validation/fault aggregation to fast_fault:−1.907ns.
- Kernel BRAM output to multiplier B input with BREG0:−1.868ns.
- Product rounding/saturation to output overflow:−1.852ns.
- Other fault/control predicates to kernel expected-next CE:−1.719ns.

The earlier DSP enable cut remains realized with positive CEA2 margins, but
that does not qualify the operand or output arithmetic paths. Physical scripts,
constraints and all seven tested RTL source files were unchanged for this trial.
CDC, external delays and complete receiver gates remain open.

### Next exact-control candidates: fast tests authorized, not physical trials

Following source/proposal review, two separately default-off candidates are
authorized in the isolated completed-input-fence worktree:

1. Distribute the scalar sticky-fault recurrence into local sticky causes with
   the identical common-epoch reset. Their OR must equal the frozen scalar
   recurrence on every edge, including simultaneous causes and resets. Keep
   all detailed reasons and raw publication fences. Registering existing sticky
   reasons one cycle later is not equivalent and is not this proposal.
2. Permit only the private64-bit expected-next kernel scratch value to update
   on a ready final-bin slot, including invalid bubbles. All other state/accepts/
   faults stay literal. Prove that the scratch value equals the old value whenever
   a nonfaulted new-block identity actually consumes it. Include every identity
   bit, wrap, invalid/X bubbles, malformed finals, stalls and overwrite mutants.

Implement and test each separately plus combined; default-off inverse restoration
and independent frozen references are required. No actual FFT simulation,
synthesis or route is authorized until those fast evidence/source changes are
reviewed. Duplicating source/product70-bit comparisons is deferred pending area
and path evidence. A real multiplier operand stage is a separate future change:
it must capture both complex operands and metadata together, preserve token
ownership and backpressure, and explicitly account for shifted overflow latency.
It would not by itself solve the separate rounding/saturation path.

## High-rate integration: offline fixture work authorized

An independently reviewed source audit confirms that existing native30/60 and
rate-conditioned coarse/pilot components are not yet a public high-rate bank+
boundary-stop composition. The acquisition and PSMA guards explicitly restrict
the current shared/STOP profiles to15MS/s; the Linux driver also checks that
rate/version/DDC identity. Preserve those checks until a new explicit opt-in
contract is implemented and tested.

Two easily missed requirements were confirmed directly in current code:

- STOP's current fatal mask0x57ff excludes conditioner saturation bit13.
  A future conditioned/shared profile needs the combined0x77ff health policy,
  including matching driver acceptance; silently permitting higher rates would
  be unsafe. Current15MS/s behavior must remain unchanged.
- Linux exposes wide DDC observations only for ABI1.4. Internal64-bit counting
  at30MS/s does not mean high words are part of that older public contract.

The old paired startup waits for canonical outputs while conditioning is
disabled; at30/60 it needs real raw-CDC cleanup/drain before public enable,
without masking a gap in an active capture. Lower-edge operation requires
actual shared edge/kernel/native-coefficient/pilot configuration, not relabeling
the current upper-only integrated profile.

Next independent worktree: `codex/starlink-rx-only-do-not-merge-high-rate-paired`,
starting FWe2f957b0a/HDLb49553c1. Only implementation/offline testing of a new
30-upper common native-source oracle is authorized. Use real integerx2
conditioning, the frozen30 conditioned kernel/energy, explicit18-bit C-model,
original-rate132tap native correlation and the independent2.5MS/s pilot oracle.
No public guard/profile, runtime, driver, receiver or physical changes yet.

With ratioD=2/4 and conditioner half-supportH=7/21, a canonical interval ofN
samples startingP needs raw inclusive support
`[D*P-H, D*(P+N-1)+H]`, or `D*(N-1)+2H+1` raw words. The proposed4096-canonical
envelope therefore needs8205/16423 raw words at30/60, not a plain8192/16384
rescale. Freeze phase/startup/halo support independently before actual RTL use.
Pilot newest canonical indexn has raw support
`[D*(n-538)-H, D*n+H]` and raw center `D*(n-269)`; do not subtract conditioner
delay twice. Every available transform prefix, native tuple and pilot output
must come from this same raw fixture. A dedicated-core high-rate numerical
composition, if used later, is only an intermediate test and cannot replace
bank/STOP deployment qualification.

## Preserved operational scope

No radios were allocated, contacted or flashed during these studies. No PPU
files changed; its existing four-file binary diff still hashes to
`eb87e8049367ba2a2f8fccf89123b6c2bb58518175e79dba3f41cddabd07848d`.
No firmware/HDL main branch was changed. The original15/30/60 native fine,
canonical15 coarse, independent2.5MS/s IIO pilot, causal handoff, eight-target
120ms-valid visits over300s and `.18` before Ethernet/PPU `.17` remain the
deployment objective. Current timing failures do not authorize flashing.
