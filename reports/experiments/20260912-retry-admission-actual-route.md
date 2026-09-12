# Retrying held-job admission — DO NOT MERGE

This experiment separates the job request from current cross-block capacity.
It preserves the actual FFT, buffers, current guard readiness, fault checks,
publication vetoes, cutover validation and all numerical results. It does not
deploy or qualify a complete receiver. Native 60 MS/s fine search and the
independent 2.5 MS/s inspection stream remain required.

FW/HDL branch: `codex/starlink-rx-only-do-not-merge-admission-grant`.
Runtime parent is the lean private-replay candidate, not shared preflight,
the replay queue, or the slower registered-product-capacity candidate.

## Implementation and contract

Only the admission request and its certificate change in the top:

- Request identifies the held job; current guard/cutover/descriptor capacity
  remains in the sampled evidence vector, not in the request signal.
- Rejected private snapshots retry while allocation/reset capacity settles.
- A good snapshot holds until consumption or cancellation; a held request can
  be consumed only once.
- Unknown evidence cannot grant. Current guard readiness remains an independent
  gate on actual job acceptance; original cutover/configuration checks and
  current public-output fault vetoes are unchanged.
- The original live-capacity certificate runs alongside the actual FFT bench.
  Actual job acceptance must match it exactly before and after every fast edge.
  Accepted jobs must have current owned capacity. A held descriptor/phase/lease
  cannot change without a detected current fault or quarantine.

Component proof covers all 4,096 six-cause four-state vectors, retry, immutable
accepted evidence, one-shot consumption, cancellation and reset/unknown control
fences. Five deliberately broken implementations must be rejected. The first
test missed a repeat-consume mutant because the next offered evidence was bad;
restoring good offered evidence after consumption makes duplicate-grant
coverage meaningful. The rejected run and its original bench are retained.

Healthy actual FFT results: 64,512 numerical words exact, 4,178 clocks,
36 admissions matching the original, 177,096 comparison checks,
144 rejected-snapshot observations and 72 real capacity-wait edges.
No additional healthy latency. The unchanged short-service ceiling is 5,215
clocks; this benchmark is not continuous-RX qualification.

CSV SHA256:
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.

## Physical result: still not closed

Same frozen 100/175 MHz OOC route recipe, actual FFT, no added exceptions:

| Metric | Lean parent | Retrying request |
| --- | ---: | ---: |
| Worst setup | -1.182 ns | -1.269 ns |
| Total negative slack | -349.709 ns | -295.708 ns |
| Failing endpoints | 930 | 811 |
| Same-175 MHz worst | -0.970 ns | -1.001 ns |
| LUT / FF | 2,756 / 5,908 | 2,739 / 5,920 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |
| Short service | 4,178 clocks | 4,178 clocks |

8,549 nets fully routed, zero routing errors; hold +0.029 ns, pulse +1.830 ns.
114 inputs and 124 outputs remain unqualified. This is not physical signoff.

The same endpoint-probe revision was run against both pinned routed
checkpoints. It requires real pins and matches each report to timing properties:

| Endpoint | Lean parent | Retrying request |
| --- | ---: | ---: |
| Admission snapshot-valid D | -0.711 ns | +0.009 ns |
| Admission consumed D | -0.716 ns | -0.040 ns |
| Admission snapshot-good D | -0.844 ns | -0.697 ns |
| Admission snapshot-good CE | +2.588 ns | +0.240 ns |
| Guard active D | -0.661 ns | -0.908 ns |
| Guard reasons D | -0.646 ns | -0.669 ns |
| Global registered fault D | +2.015 ns | +0.320 ns |

The original probe did not match the parent's generated-block name for
snapshot-good registers and correctly rejected that partial observation.
Revision 2 matches both flat and generated-block names; both have 35 real
snapshot-good D/CE pins. No missing endpoint is counted as passing.

The request path improves, but the remaining worst same-clock path is now
latched global fault through output-stage/ledger fault handling, inverse guard
completion, and output-descriptor lock: eight levels, 6.663 ns data delay,
about 78% routing. Guard-active's worst path is also through completion/retirement,
not simply the job-admission request.

The overall worst is a zero-logic held-metadata crossing from 175 to 100 MHz.
That crossing is not automatically waived. Actual board clocks and the complete
CDC ownership/constraints require separate qualification. Same-domain setup
also fails, independently of that crossing.

**Not promoted:** lower TNS does not establish timing closure or an aggregate
winner. Keep comparison with the lean parent and do not stack every experiment.

## Extended actual-FFT tests and rejected harness attempts

Ten new cases run before the inherited 82-case campaign:

1. Forward destination readiness stall and bounded recovery.
2. Forward cutover-capacity stall and bounded recovery.
3. Inverse destination readiness stall and bounded recovery.
4. Inverse cutover-capacity stall and bounded recovery.
5–8. Each raw reset input, in each phase, while admission is pending.
9. Held request expires through the existing preparation timeout.
10. Descriptor substitution while a request is pending.

Every cancellation requires no stale output/core input and fresh 512-word
recovery; the capacity-recovery deadline remains six fast clocks.

Retained failed attempts explain the test changes:

- First insertion ran before the auxiliary checker mode was selected, leaving
  the six-context timestamp checker active for the auxiliary block-start tag of 1000.
  The checker mode now switches before the first auxiliary send.
- Forcing the packed two-guard capacity output left its inverse bit at zero
  after release. A diagnostic run showed all underlying guard conditions ready
  (reset=1, no protocol fault/active/ACK/return, both reservations=1,
  mailbox ready=1) while the internal capacity output stayed zero. Both the
  original and retrying certificates correctly refused admission.
- The first replacement targeted a legacy forward readiness wire that the
  active guard no longer consumes. Final injection is directly at each guard's
  scalar mailbox-input-ready port. The guard computes capacity normally.
  Tests prove these revisions change only injection targets, not assertions,
  deadlines or the runtime RTL.

Final proof: **2,299 scoped tests pass** (155.262 s), and **all 92 actual FFT
fault/reset/stall cases pass** (367.738 s). There are 1,841,886 admission-oracle
checks, 316 accepted jobs, 1,326 rejected-snapshot observations and 671
capacity-wait edges. All current grants match the original certificate exactly;
the inherited 28 delayed guard-fault observations remain present. Fresh numerical
audit and source matching were rerun before archiving.

FW source commit `2a5c0a99c`, HDL `05756d03d`, pushed on the branch above.
Verified archive: `reports/evidence/20260912-retry-admission-evidence.tgz`,
13,501,735 bytes / 1,095 regular members. SHA256:
`b3683a55ecd9e029451a840a4f98c568c3135d40859641d0e9339b9943fd99df`.
It includes frozen preparations, healthy and rejected runs, final full campaign,
synthesis/routed checkpoints, both endpoint observations, scoped-test receipts,
and source helpers. Generated bulk regression fixtures remain locally available;
they are not duplicated into this archive. The adjacent archive receipt records
sequential per-member SHA256/inventory/CRC verification and unchanged sources.

## Next meaningful timing experiment

The measured admission bottleneck is reduced, but another request-only tweak
will not remove the completion path now dominating same-domain timing.

Inspect the propagation of an already-latched global abort back through local
output-stage/ledger error summaries and then into guard retirement/descriptor
locking. Separate these two contracts explicitly:

- first-fault detection, immediate publication prevention, stable cause evidence;
- post-quarantine private bookkeeping, which must never authorize publication,
  reuse or a new core job and must recover cleanly after the common reset.

Before changing that behavior, identify which diagnostic/private fields are
externally consumed. Preserve the observable interface and required fault
evidence; do not silently weaken an ABI or a first-fault safety condition.
Prototype a bounded local retirement/descriptor-freeze boundary with concrete
ownership and cancellation rules, then prove numerical/published-result
equivalence, no stale tag/grant, current-fault cancellation, both resets and
fresh recovery. Measure both throughput and all critical endpoint groups.

After isolated timing closes, full receiver routing at actual board clocks,
continuous 60 MS/s + 2.5 MS/s inspection/DMA/Ethernet, real calibration, and
serial-verified .18 canary → reversible Ethernet PPU deployment to .17 remain
open gates. The 200 MHz IDELAY reference is not casually changed.

## Reproducibility and radio scope

Artifact root:
`/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/admission-grant-artifacts.5W9rCyb5`.

Main/synthesis prepared pin:
`af22ae7a5bc32bb7a53f7d33043ada08ab9dd4ed02f9a16e76c3c1f69f2c82ec`.
Final auxiliary prepared pin:
`92c3127aacd81501ddf2c26999c707350c181f07ddad55948c16dcdf8edfdcfd`.
Synthesis DCP:
`779632aeb70f627455a2c528f7914d9c3cdadcd09ed8c6a43c85e49e46381ca0`.
Routed DCP:
`85ed592b0b6e22601f7fa59b28902602f5f098458eda72cd4c221272952ce740`.

All 43 runtime files must match between healthy, synthesis and final auxiliary
profiles. All work stays on explicitly do-not-merge FW/HDL branches.
No radios, PPU or main branches were touched. PRIMARY HDL stays
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.

.18 canary: `1040007c4a94000211000b009186843ef2`.
.17 outdoor Ethernet-only receiver: `104000bac4950008230026001b440a003a`,
powered LNB on RX1 only. .14/.20/.21 are excluded.
