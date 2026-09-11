# Private kernel sequence: aggregate improvement, timing still fails

Implemented on private-final-capture FW `565dd5c45` / HDL `e200100db`.
FW `74c1e2b67` and HDL `f4e14c326` are preserved separately on
`codex/starlink-rx-only-do-not-merge-private-kernel-sequence`.
No radio was touched. No PPU/main changes; primary production HDL remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

## Change and proof

The kernel's hidden bin counter, expected-next-block start and previous-block
flag advance from a caller-owned private offer and actual capacity. Public
per-bin, TLAST, exponent, block identity and stride checks still consume pre-edge
state and original input-valid. Output-valid/completion remain public-qualified.
Held final offers still require original final status/count/exponent/fence checks.
Private/public divergence requires caller quarantine until common reset/flush.
The feature is default off, enabled in the experimental registered FFT top.

Eight local tests pass, including a pinned-original ROM comparison and seven
rejected unsafe variants. Coverage retains 4096 healthy lookups and malformed/
stall/flush cases, adding wrong next-block stride and unpublished first/final
offers. Hidden state advances on those offers, but neither public acceptance
nor completion asserts; all sequence state clears on flush.

**Actual FFT passes: all 64,512 records match**, with byte-identical CSV and
unchanged service intervals. **435 combined tests pass in 55.58 seconds**.
Healthy private/public handshakes agree across 9216 advances, 98,246 holds and
18 final updates. The entire prior fault/reset/ownership campaign passes.
Six new actual cases cover vendor fault, product framing fault and duplicate
status at mid-word, delayed legal final status, 16-clock final backpressure,
and vendor fault precisely on a qualified final offer. Fault cases advance
privately but do not publicly accept/complete; subsequent 100-clock quarantine
has no new input/job/publication/read/release. Legal cases each yield 512 correct
reads and one real release. Total receipts: 106 admissions / 77 completions.

Actual / synthesis / route: 118.22 / 98.33 / 55.82 seconds, first-attempt successes.
Two preflight checks pass. Before/after source identities and route audit pass.

## Physical comparison

| Candidate | Worst slack | Total negative slack | Failing setup endpoints |
|---|---:|---:|---:|
| Private descriptor capture | -1.969 ns | -813.676 ns | 914 |
| Plus private final-data capture | -2.005 ns | -634.847 ns | 856 |
| Plus private kernel sequence | -2.047 ns | -550.201 ns | 825 |

Aggregate timing deficit improves another 84.646 ns (about 13%), with 31 fewer
failing endpoints. Worst slack is 0.042 ns worse than the parent: retain the
references, and do not treat this as physical signoff or deployment promotion.
825/13800 endpoints fail. Hold +0.058 ns, pulse +1.830 ns, 8363 nets routed with
zero errors. Resources: 2770 LUT / 5668 FF / 21 DSP / 15 RAMB18. Diagnostic
100/175 MHz clocks unchanged; five critical CDC findings, 208 warnings and
114/124 unqualified board I/O remain.

The worst path now traverses publication phase -> output-bank metadata
mux/comparison -> guard/shared current-fault aggregation -> descriptor
certification. Eleven logic levels, 7.706 ns data delay, 5.886 ns routing.
The shared control dependency, rather than arithmetic throughput, still fails.

## Next gate and deployment

Review descriptor certification together with admission and quarantine.
`descriptor_certified` captures `preparation_valid && !any_fast_fault`, although
admission separately consumes current validation and registered quarantine.
Test whether the private descriptor snapshot can be separated from permission
to start a job. Prove faults at snapshot and consumption prevent every start,
cancel stale receipts and require fresh recovery. Keep immediate publication
vetoes and detailed fault recording; do not merely delay the global fault.

No receiver features before subsystem physical qualification. Native 60 MS/s
fine search and independent 2.5 MS/s CI16 inspection remain required. Full
receiver route/CDC/reset/board I/O, sustained capture, actual 60 MS/s RX
calibration and Ethernet/IIO verification precede `.18` reversible canary and
`.17` PPU Ethernet-only deployment with rollback. Final verification: 300-second
scan, 120 ms valid dwells and blind host GLRT comparison. No deployed result or
deployment ETA is proven by these subsystem tests.

## Evidence

[Verified archive](20260911-staged-sequence-evidence.tgz),
[receipt](20260911-staged-sequence-evidence.json): 15,709,176 bytes,
7,374 regular members, all read-back verified. SHA256
`5b1edd6a3bfa6c38d4a0a7776ae00d1f8974008fd1a2cebed24a7eae360b801c`.
Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/private-kernel-sequence-worktree-v1`.
Sibling artifacts: `staged-sequence-{prepared,actual,synth,route}-v1`.
Inventory `abdac9894243bc6d7c3c573095fa332068a14e641f044205e40925abeb432606`;
synthesis DCP `bb99304bab866708ee00e50369f7778eac121cfae9a74fb947d3f9b8e456181a`;
routed DCP `4c58e354dbe421a671f9f1a292d6e6a685ae89be50230a3a86d2b83a2e3cca94`.
