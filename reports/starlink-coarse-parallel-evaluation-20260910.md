# Parallel coarse-engine evaluation — experimental only

## Latest checkpoint: complete scorer and control-path counterevidence

The map-lifecycle task below is complete at FW `b709f683` / HDL `1800c665`:
eight actual175 cases, 7,560 exact scores and 3,129 exact map words. Root checked
all 101 source/artifact hash receipts and integrated only additive tests/reports
into the primary experimental branch. Both rejected v1 and successful v2 logs
are archived in `experiments/20260910-bank-map-lifecycle.tgz`; see the original
report in `../docs/starlink-bank-map-lifecycle-20260910.md`.

The registered-scheduling study is frozen separately at FW `9b324979` / HDL
`ba000e48`. Actual-core tests pass, but its single175 route fails setup -2.461 ns
(hold +0.071 ns), with 1,935 LUTs, 4,540 FFs, 21 DSPs and 7.5 BRAM tiles.
The worst path still runs from scheduling state through wide preparation
validation into guard admission: 8.122 ns, including 5.492 ns routing. Root
reviewed the report and preserved it on the completed-input-fence remote branch;
no control-path variant has been merged into primary or deployed. The repaired
exact-source tests pass 244 with eight explicit physical-test skips; the original
239/8/3 stale-anchor result and failed route remain retained.

The next separately opt-in experiment splits preflight from active fault
handling. Raw preflight must still record its reason on the original edge and
quarantine the epoch, but must not create a wide admission combinational path.
An emitted start token must be suppressed even on the latest receipt-consume
mismatch. All active fault/publication vetoes and bank retirement checks remain
unchanged. The split is now frozen at FW `4eeda57e3f7f646ee14cdeab57b7074ca479d585`
and HDL `fb820d3908ac75e29e604a9895d482c2edf4146a` (tested RTL `cee639e43`).
Default and registered actual-core replay pass. All84 new preflight boundary
rows, exact same/next-edge status reasons, six detailed causes, suppressed start/
read/configuration/publication and two one-sided fault-reset recoveries pass.
Registered service stays4,548 nominal/4,828 bounded-stall clocks. The full
regression is247passed/eight explicit physical skips; root independently reran
the reason-only, final-authorization and phase-input suites:20passed/two explicit
physical skips. Root checked the source/log hashes and complete evidence
checksums, then authorized one unchanged100/175 OOC synthesis/diagnostic route.
That one measurement is now complete and still fails175 setup at -2.438ns
(hold +0.071ns), with1,991 LUTs,4,543 FFs,21 DSPs and7.5 BRAM tiles. All6,590
routable nets routed, but688 fast-clock endpoints fail setup; this is not just
one isolated outlier. Physical evidence is separately frozen at FW `091d0e663`
/ HDL `691966ae`, with no design-RTL change. Root verified its report and full
checksums. The worst path moved to state-dependent input selection through the
active input guard's full metadata equality into admission. An explicit held-
phase delivery tuple now passes both actual175 modes, frozen at FW `1530939f`
/ HDL `3c5c3aba` (tested RTL `d99c251e`). Root reviewed the exact tuple-only
delta, old-mux checker witness and full evidence checksums; its two strict
source tests independently pass. Both modes cover12 actual-bank corruption
cases, two open-slot QUARANTINE cases and two one-sided-reset recoveries.
The registered84-row preflight suite remains intact. These pins are backed up
on the completed-input-fence remote branch, not promoted to primary. The next
separate default-off comparator experiment retains all70 identity bits and
same-edge certification/reasons with balanced equality leaves. No held-phase
or comparator physical result is claimed yet.

The balanced comparator is now separately frozen at FW `eb9e008e7` / HDL
`9f598dd1` (tested design `447183b8`). Both actual modes exit0 and their complete
24-column control traces byte-match held-only. The258-test regression passes
with eight unchanged explicit physical skips. Root reviewed the exact all70-bit
delta, immutable reference,420 corruption rows per mode, retained final-edge
vetoes and all evidence checksums; its independent nine-test run passes including
bit69 and duplicate-veto omission mutants. One fresh100/175 synthesis/diagnostic
route was authorized with unchanged source/constraints/strategy. That single
trial is complete: synthesis exited0 at03:08:07 UTC and route at03:09:57 UTC.
The175MHz setup miss improves from−2.438ns to−1.596ns; hold+0.070ns. Source100MHz
setup+2.426ns, hold+0.100ns. All6,664 routable nets complete with zero route
errors, using2,023 LUTs,4,556 FFs,1,055 slices,21 DSPs and7.5 BRAM tiles. There
are still497 same-clock175MHz failing endpoints, TNS−522.209ns. Worst path is
now scheduling state through the preflight metadata carry chain into descriptor
certification:7.255ns (2.443logic/4.812route),12levels including5CARRY4. The114/124
OOC input/output delay gaps and139 metadata CDC warnings remain. This is
improvement, not timing closure or primary runtime promotion. Exact original
reports are `/tmp/starlink-completed-input.5EaJuD/balanced-route-v1/`; input
synthesis DCP SHA256
`fbeb7245dec062e80ebf9c25cc10fdbf1c1a7fcd22b1fe3640168e552bff01c2`.
Root read the actual route receipts and full worst path, then independently
verified the complete physical archive checksums. The negative result is pinned
and backed up on the completed-input-fence remote at FW `5e6424a4b` / HDL
`6fb16e4b`, with design `447183b8` unchanged. See that branch's
`docs/starlink-balanced-identity-physical-20260910.md`.

The next bounded implementation/test step is approved, not another physical
run: use a phase-direct held preflight tuple while VERIFY/ARM is active and
balance both full70-bit preflight comparisons. Keep all header/phase/lease and
current-edge fault/certificate vetoes. The independent witness must compute the
old preflight predicates itself and feed the result shadow, not share the new
predicate. All-bit fast predicate tests and existing actual-core boundary/fault/
numeric tests have distinct scopes. Only unused idle preparation values may
differ; forward-phase expected-product-cache mismatches remain ignored exactly
as before. No further synthesis/route or primary runtime promotion is authorized
until those source-specific tests are reviewed.

A separate active-clock verification worktree now exists at
`/tmp/starlink-coarse-alternatives.Y3JzOI/clock-traffic`, branch
`codex/starlink-rx-only-do-not-merge-clock-traffic` in FW/HDL, starting FW
`135769292` / HDL `dbe744c0`. It completed at FW `704f58b2` / HDL `7d4d6d8c`:
five exact full replays and four active reset cases with actual generated175
MMCM and complete coarse traffic. Root verified all124 hash receipts, merged
only additive tests/evidence, and independently replayed the merged source at
02:55:46 UTC: 7,853 accepted exact scores, 10,752 forward/product and9,985 inverse
words. No receiver clock wiring changed. See
`experiments/20260910-bank-clock-traffic-primary-replay.md`.
The root independently completed a read-only exact-bank CDC inventory of the
earlier complete-coarse DCP; see `experiments/20260910-bank-cdc-inventory.md`.
No CDC exceptions were added and no physical pass is claimed.

The original 4,096-block175 burst/stall soak remains active; its latest agent
observation at02:52:37 UTC reached2,417 blocks/1,080,399 ordered scores with FIFO maximum358 and
no observed error. That partial count is not a terminal capacity PASS.

A new independent FW/HDL worktree at
`/tmp/starlink-coarse-alternatives.Y3JzOI/production-map`, branch
`codex/starlink-rx-only-do-not-merge-production-map`, starts at FW `ad6dfbb79`
/ HDL `6ae9c302`. Its bounded task is a compact independent18-bit C-model
oracle and actual-bank production20000x64 map verification, with unchanged
runtime/geometry and full numerical/tail/stop/retention checks. A447-sample
periodic synthetic source makes the oracle compact; it is arithmetic and map
geometry stress, not RF or750 Hz acquisition evidence. The full1,280,000 selected
scores must be distinguished from the supporting2,864 FFT blocks and208 potential
tail scores. Root must review frozen expectations and a reduced wiring smoke
before the long production simulation is launched. No runtime/profile/radio or
physical-build work is delegated to that task.

An additional independent verification worktree was allocated after the
read-only map integration review: `/tmp/starlink-coarse-alternatives.Y3JzOI/bank-map-lifecycle`,
firmware and HDL branch `codex/starlink-rx-only-do-not-merge-bank-map-lifecycle`,
starting FW `249edd4b535bea7e6537e8c102f49ad1b5f8b07f` and HDL
`69f84febf0a2788f23e04f2f6b3cfec5b33b9c9a`. The previous narrow-agent study is
preserved unchanged. The bounded new task is actual-core map retention,
publication-edge fault visibility and reset/re-enable lifecycle verification;
no radio, PPU, full receiver, synthesis/route or remote changes are delegated.

The complete bank-owned coarse composition is now additive code on the primary
experimental branch, not selected by receiver defaults. Six alternative-branch
actual-core runs cover numerical/fault replay and nominal/burst-stall 64-block
capacity at 175/200 MHz. Independent primary-branch 175 MHz numeric and stalled
capacity runs also pass; see `experiments/20260910-bank-composition-primary-replay.md`.
Whole-coarse synthesis measures 3,868 LUTs, 6,499 FFs, 27 DSPs and 14 BRAM tiles,
with no black boxes. These are not routed receiver resource savings or a timing
pass. The separately frozen 4,096-block soak described above is running.

The completed-input refactor is intentionally NOT merged into the primary HDL.
Its first isolated route regresses from the original bank's -2.557 ns to
-3.855 ns. The subsequent raw-readiness/certified-ACK experiment passes the
actual-core numerical/fault suite, including post-ACK orphan quarantine, but
still fails setup at -3.144 ns (175 MHz hold +0.059 ns). Its worst path is
`next_inverse_reg` through input metadata validation to controller state,
8.806 ns data delay, including 6.060 ns routing. This is evidence for examining
registered validation/admission boundaries, not permission to relax constraints.
The second experiment remains in its independent worktree pending report review.

Root pushed and verified these exact experimental remote pins after the
independent replay, without touching main or radios:

| Remote branch suffix after `codex/starlink-rx-only-do-not-merge` | Firmware | HDL |
| --- | --- | --- |
| primary (no suffix) | `1fc195de2b4a38fbe89efbb9f208b4508ab96404` | `39bbf8a131e1b83e70e3875c697c12f11f23b03c` |
| `-fft-island` | `e880640b7763d2646fbba5f1aa118246ef6a9aa6` | `95cedf076a845d1c52ec3134fd55d4666d225bcd` |
| `-completed-input-fence` (first failed physical study) | `ae0a51d92e92db039f24551e11befd8c5d53c669` | `b8c98c23d9cf7ee273aab83e94867b0efd9b85d2` |

The history below retains earlier results and their original promotion limits.

The user explicitly requested an independent subagent and worktree for every
alternate approach. Three agents were launched on 2026-09-10 UTC. The primary
agent continues the existing idle-admission timing experiment separately.

All alternatives start from the same committed firmware `ec36b96965df76f83b80e70c1aba867e7cbbbc30`
and HDL `eb96c64738697c10b9c0abb379ab64f6a4a5c59c`, not the primary worktree's
uncommitted files or newly promoted candidate. Each has independent firmware
and nested HDL Git worktrees; only Git object storage is shared.

| Agent | Firmware worktree (HDL is its `hdl/`) | Branch in both repositories |
| --- | --- | --- |
| `coarse_fft_island` | `/tmp/starlink-coarse-alternatives.Y3JzOI/fft-island` | `codex/starlink-rx-only-do-not-merge-fft-island` |
| `coarse_direct_correlator` | `/tmp/starlink-coarse-alternatives.Y3JzOI/direct-coarse` | `codex/starlink-rx-only-do-not-merge-direct-coarse` |
| `coarse_narrow_acquisition` | `/tmp/starlink-coarse-alternatives.Y3JzOI/narrow-coarse` | `codex/starlink-rx-only-do-not-merge-narrow-coarse` |

## Bounded deliverables

- Consolidated island: actual-core first slice or executable cycle/dataflow
  model keeping FFT, template multiply and inverse processing local. Charge
  outer clock-crossing/bank costs and retained ACK/reset/config overhead.
- Direct correlator: coefficient provenance and independently evaluated
  numerical/cycle prototype, with resource measurement where practical. The
  original Q15 taps and quantized frequency-domain/BFP chain are distinct
  numerical contracts; unchanged goldens remain the reference.
- Narrow acquisition: offline sensitivity/CFO/filter-support and causal
  assistance study. No assumed host real-time capacity, post-hoc seed leakage,
  or hidden filtered-out negatives. Original-rate fine search remains required.

Each agent must report executed tests, source/artifact identities, measured
limits and open integration work. A negative result is useful. No architecture
is selected from an unexecuted proposal or isolated area estimate.

## Ownership and promotion boundaries

No agent may access radios, edit PPU or another worktree, merge into main, push
remotes, launch a full receiver build, waive timing constraints, or remove a
detector. Qualified local branch commits are permitted for review. There are
no delegated radio ownership locks. The primary full build retains coarse and
fine PSS, pilot DMA and the original clocks/constraints. Alternative full-build
selection follows review so source identities remain unambiguous.

The full objective is unchanged: original-rate fine search at 15/30/60 MS/s,
independent 2.5 MS/s pilot IIO capture, .18 then Ethernet/PPU .17 verification,
eight lower/upper targets with 120 ms valid dwells over 300 s, and independent
live GLRT/PSS agreement. Neither simulation nor 16.7 ns sample spacing is a
deployment or accuracy claim.

## Completed first studies and independent review

All three agents finished on 2026-09-10 UTC. The root read each complete report,
checked clean firmware/HDL worktrees and exact commit identities, and reran the
20 newly added unit tests: island8, direct3, narrow9, all passing. These are
independent unit-test reruns, not repeated physical builds or the complete
offline data experiments. Agent-run evidence and its limits remain separate.

| Alternative | Firmware commit | HDL commit |
| --- | --- | --- |
| FFT island | `d88ad998d4207972855b92ee92fdf9e3a099f3dc` | `456f6d76aa82751f4db50323c648a885ee49c47a` |
| Direct coarse | `84c48b347cc0c7f13f15403eaa174f9076d4fda3` | `a29d4fc27e2b92311131d07c53fb559bff37c697` |
| Narrow assistance | `3f192ada5ae79b7e7f4afe96f129f2b20cc84d0b` | `eb96c64738697c10b9c0abb379ab64f6a4a5c59c` (unchanged) |

These alternative branches are local; no remote push or merge was performed
by the agents. Their committed reports are respectively:
`docs/starlink-fft-island-slice-20260910.md`,
`docs/starlink-direct-coarse-evaluation-20260910.md`, and
`reports/starlink-narrow-coarse-feasibility-20260910.md`, in the worktrees above.

| Approach | Executed evidence | Current limiting result |
| --- | --- | --- |
| Consolidated FFT island | Actual generated core:23 healthy blocks,11776 exact inverse words, reset/flush and fault cases | 5182-clock nominal interval at200MHz leaves3.89us/block; a measured6130-clock stalled profile exceeds29.8us. Outer CDC banks remain modeled, not implemented; no physical result. |
| Direct66-tap coarse |119 RTL arithmetic/protocol jobs;102 numerical controls; actual isolated route |2/102 controls fail unchanged FFT comparison, up to9 score LSBs.2087LUT/2442FF/18DSP slice passes setup(+.453ns), fails hold(-.713ns); history/normalization/CDC are extra. |
| Narrow pilot/GLRT assistance |12 synthetic and9 real20ms probes;69 focused tests | Supported fixtures pass, but real CFO aliases remain. Measured x86 search28.13–62.16ms is not target CPU capacity; future-frame handoff49.48–83.51ms excludes transport/control/fine cost. |

The direct result defines a different arithmetic contract; matching an independent
float oracle on its failing dynamic-range controls does not establish better
detection or authorize changing production acceptance tolerances. Narrow
assistance is a candidate aid, not a replacement for native fine evidence.

The root's unchanged-clock full idle-admission receiver build also completed
with exit1 at00:20:46UTC. WNS -1.269ns and355 failing endpoints regress from
the retained best18c reference. No build artifact is deployment eligible.
The worst path has6.100ns data delay, including4.900ns routing, between input
cursor and result input-count control. This and full slice occupancy support
investigating locality and complete resource budgets; they do not prove which
alternative will close timing.

## Next bounded comparison, not a selected replacement

1. Prioritize a second FFT-island experiment that removes redundant local bank
   copies through validated ownership handoff. Preserve exact arithmetic,
   current faults, late-fault quarantine, reset/ACK and complete publication.
   At150MHz the measured first slice needs at least713 clocks removed merely
   to get positive nominal margin; removing one512-clock copy is insufficient.
2. Measure the complete island including outer banks, both edges, original
   energy/normalization and sustained stalls, then its actual resource/physical
   cost before commissioning another full receiver build.
3. Keep direct as a separately scored fallback until numerical acceptance,
   complete history/normalization cost and real hold closure are demonstrated.
   Do not spend a full receiver route on the current incomplete arithmetic slice.
4. Keep narrow pilot evidence independent and study alias-preserving future-frame
   commands. Charge real host/transport/control/compute deadlines and expire
   stale visit-tagged predictions; do not assume a retrospective native60 ring.

The measured reference-resource inventory and reproducible read-only reports are
in `reports/experiments/20260910-coarse-reference-resources.md` and its archive.
Normalization and20BRAM tiles of coarse maps remain material costs regardless
of the FFT choice. No source-rate fine search or pilot output is removed.

## Completed second studies and remote preservation

The root reviewed all three second-study reports, reran the direct feeder RTL
(72543 inputs/71047 exact results), reran the eleven prior-alias unit tests,
and reran nineteen bank-evidence/island-budget tests. All passed. Root checked
the six remote refs against the exact frozen hashes below after pushing.
The FFT branch now proceeds to an additive unchanged-score composition; its
frozen bank-slice revision remains separately identifiable below.

| Alternative | Frozen firmware commit | Frozen HDL commit |
| --- | --- | --- |
| Three-bank FFT island | `1035b93d53b8519f18d280e50f7e3ab11e56edce` | `169f9fb659bd98b4cb1e76163f4fdb8b853a7d1b` |
| Direct feeder/history | `73c98844d801aae3fdb510503d2f1d4e9c04615e` | `f36613fa13626a86db3b9f30ce557e41c61b1913` |
| Prior-alias assistance | `d0acda14b7f44b054671df6098793c8c36db532f` | `eb96c64738697c10b9c0abb379ab64f6a4a5c59c` (unchanged) |

The root pushed these exact six revisions to their corresponding do-not-merge
branches in the firmware and HDL remotes. No main merge or PR was created.
The agents themselves performed no remote writes. Further working-tree changes
are not implied to be included in those frozen pushes.

The FFT slice passes actual-core tests at150/175/200MHz with44 healthy complete
blocks per run and a130-word exact provisional prefix before injected late-fault
quarantine. The175MHz nominal/stalled maxima are25.943/27.543us, below29.8us
arrival;150MHz's31us stalled interval exceeds it. These are independent-block
slice results, not continuous-source score qualification. The complete slice
synthesizes to1834LUT/4375FF/21DSP/7.5BRAM, with no black boxes.

Root's subsequent isolated route finds a same-domain175MHz failure of-2.557ns
from product-bank metadata through input/result validity to kernel-memory enable.
The archive and exact diagnostic limitations are in
`experiments/20260910-bank-owned-route-diagnostic.md`. A physical receiver clock
is not established. The next control refactor must preserve identity checks,
current-fault commit vetoes, private-bank ownership and terminal health.

The complete direct feeder+MAC route fails setup(-3.161ns) and hold(-.742ns),
with2354LUT/2814FF/18DSP/4BRAM; normalization remains omitted. It is not selected.
The prior-alias study completes eleven exact PSS branches and25 blind GLRT
probes, but both causal CFO aliases remain candidates. Two sequential maps
need at least170.667ms at current throughput and the production three-map rule
needs256ms for one branch. Short-dwell causal policy remains an explicit gate,
not something timing closure alone resolves.

Detailed next gates: `starlink-bank-owned-integration-gates-20260910.md`.

### Independent completed-input control experiment

The direct-study agent's subsequent read-only review found that a visible held
return implies registered complete input in the current result guard: any raw
output without the required input evidence faults on capture, and the sticky
fault masks the speculative return afterward. This is a candidate premise for
shortening the control cone, not permission to remove active-input identity
checks or current duplicate-start/final-publication vetoes.

A separate FW/HDL worktree is allocated at
`/tmp/starlink-coarse-alternatives.Y3JzOI/completed-input-fence`, branch
`codex/starlink-rx-only-do-not-merge-completed-input-fence`, from the frozen
bank-slice commits1035b93d5/169f9fb. The agent may implement an explicit opt-in
phase predicate there, with unchanged default guards and complete fault reasons,
then actual-core175MHz tests and an isolated diagnostic route. No full receiver
build, radio, PPU edit or agent remote write is allowed. This branch is initially
local and unqualified. It does not modify the FFT agent's concurrent scorer
integration or the retained failed bank-slice route.
