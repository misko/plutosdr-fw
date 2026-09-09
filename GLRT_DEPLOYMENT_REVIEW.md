**FPGA GLRT: review and deployment plan — 9 September 2026**

The implementation is ready for a focused completion effort. The architecture,
integer arithmetic, five routed images, IQ/event interface and RAM packaging
exist. Useful detection, reliable finite-capture completion, real transport and
the outdoor deployment path still need work. The next milestone should be one
repeatable, independently validated 2.5 MS/s receiver on the USB canary, followed
by the rate ladder and the outdoor receiver.

This review changes documentation only. It does not authorize radio access,
collection, flashing or production promotion.

**Reviewed baseline and evidence**

- Firmware `6e49144af3b7bc6044d640582f5d49845779cb37`, branch
  `codex/starlink-glrt-only-do-not-merge`, in
  `/home/mouse9911/gits/plutosdr-fw-starlink-glrt-only`.
- Current HDL checkout `0d67920c`; lower-rate images use `a9a4ca9a` and the
  60 MS/s image uses `0d67920c`. Their documented differences are physical
  optimization/fanout settings. Linux `2ca294936430`, Buildroot `35d87ae5`.
- Device deployment extension `fa2f6e1`, in the firmware workspace's
  `artifacts/device-tool-glrt-v1`; it provides the experimental RAM-only
  `rx-glrt-stream-v1` policy.
- Independently checked all 114 path/hash entries in the
  [current package report](../plutosdr-fw-starlink-glrt-only/reports/starlink-glrt-current-board-packages-20260909.json).
  Every referenced file exists and matches. This verifies retained evidence,
  not a fresh place-and-route or an observation of hardware.
- Re-ran existing offline suites: 91 package/ABI/IIO/capture/comparison tests;
  170 device-tool RAM contract/backend/lifecycle/CLI tests; 22 host/comparison/
  terminal tests; and 24 scorer/selector tests. All passed. These suite counts
  overlap and must not be summed as unique coverage. No radio or Vivado build
  was started during review.

The design actually performs blind pilot acquisition and native-rate GLRT in
fabric. The independent 2.5 MS/s IQ export does not depend on detections. Host
analysis receives no FPGA timing/CFO seed, and provenance/counter validation is
substantial. These are foundations to retain.

| Source MS/s | Current RAM label | Setup / hold slack, ns | Strong frames recovered in latest synthetic trial | Hardware / live |
|---|---|---|---|---|
| 2.5 | `glrt-ram-r2500000-v4` | +0.112 / +0.019 | 4 / 9 | Unqualified |
| 5 | `glrt-ram-r5000000-v3` | +0.200 / +0.021 | 4 / 9 | Unqualified |
| 10 | `glrt-ram-r10000000-v3` | +0.075 / +0.014 | 8 / 9 | Unqualified |
| 25 | `glrt-ram-r25000000-v3` | +0.041 / +0.024 | 8 / 9 | Unqualified |
| 60 | `glrt-ram-r60000000-v2` | +0.002 / +0.013 | 8 / 9 | Unqualified |

All five are build/package candidates. Their deployment-readiness flags remain
false. Rates are compiled into separate images; the board/driver profile is
upper-pilot, single-RX only.

**Findings, in priority order**

1. **P1 — Admission discards useful frames while the scorer is occupied.**
   [Receiver admission](../plutosdr-fw-starlink-glrt-only/hdl/library/starlink_glrt/starlink_glrt_receiver.v:81)
   requires both native reader and scorer ready. The latest trial detects
   32/45 strong frames; all 13 misses had a truth-near candidate selected and
   rejected while busy. The existing bench measures 37,457 processing cycles
   after the 64th correlation before a score result: 374.57 microseconds at
   100 MHz. At 60 MS/s the 16,384-sample native ring retains only about
   273 microseconds, and selection already waits 140.8 microseconds. An epoch
   queue cannot safely wait through a full score without considering history
   expiry. This is a scheduling problem before it is a threshold problem.

2. **P1 — The default capture profile differs from the tested profile.**
   [Capture defaults](../plutosdr-fw-starlink-glrt-only/tools/starlink_glrt_capture.py:340)
   use acquisition Q16 `15729` (about .24); the improved numerical evidence
   uses `13107` (about .20). Saved development record 31 produces zero
   proposals at .24, with maximum acquisition score .22913945, and a matched
   detection at .20. The evidence preserves this honestly, but an operator
   following default capture commands does not reproduce the tested detector.
   These are engineering settings, not calibrated RF thresholds.

3. **P1 — Finite observation completion needs an explicit detector boundary.**
   [Kernel stop/drain](../plutosdr-fw-starlink-glrt-only/linux/drivers/iio/adc/adi_starlink_glrt.c:434)
   allows buffered jobs to finish but can leave a scorer awaiting samples past
   the captured end. The
   [host event check](../plutosdr-fw-starlink-glrt-only/tools/starlink_glrt_abi.py:120)
   conservatively rejects pending scorer state. Offline replay can prove an
   incomplete tail using internal indexes; the hardware ABI cannot. Thus valid
   IQ can survive while the strict captured-observation comparator is unusable.
   Do not remove the rejection without supplying the missing evidence.

4. **P1 before operational rollout — Physical and transport qualification is absent.**
   The [CDC review](../plutosdr-fw-starlink-glrt-only/reports/GLRT_CDC_REVIEW.md:95)
   leaves 13 external RX data/frame inputs and two ENSM outputs without external
   timing closure. The RX PN/tuning path remains available despite removal of
   native ADC DMA, but no per-rate calibration/eye evidence has been collected.
   At 60 MS/s only 45 of 4,400 slices remain free, with +0.002 ns setup slack.
   This is a constrained internal STA pass, not proof of a robust physical
   receive interface. Sustained IQ transport has never been measured.

5. **P2 — Qualification process success does not mean detector success.**
   [The synthetic runner](../plutosdr-fw-starlink-glrt-only/tools/starlink_glrt_synthetic_qualification.py:149)
   exits successfully when execution completes even if its separate detector
   criteria flag is false. Its strong-case criterion needs only one matched
   frame, so an all-cases pass coexists with 29% missing strong frames. The
   latest full 24-record saved-RF study also predates the 352-sample selector;
   only a selected saved positive was rechecked after that change. Controls
   cover just 59.4984 ms of supported IQ in the latest synthetic trial.
   Neither sensitivity nor a false-alarm rate is qualified.

6. **P1 before outdoor rollout — RAM deployment is not the LAN deployment path.**
   [The device-tool policy](../plutosdr-fw-starlink-glrt-only/artifacts/device-tool-glrt-v1/docs/adr/0009-experimental-glrt-stream-layout.md)
   explicitly scopes GLRT to the v2 RAM lifecycle. Persistent/LAN layout
   validation has no GLRT profile. The existing deployment design requires
   local persistent boot/workload/recovery evidence before promotion of the
   same bytes to an Ethernet-only device. The prepared RAM plans do not
   complete this step.

**Execution plan**

Keep one firmware owner, one numerical/host owner and one deployment owner.
Independent work can proceed in separate component branches, with the firmware
owner assembling one candidate. There should be one qualification table and
one set of immutable candidate receipts, rather than competing status reports.

Steps 2–4 are rate-scoped: repair, refresh evidence and pass full-design checks
for 2.5 MS/s, then qualify that candidate. Other rates may progress independently.
All five remain required for final completion; higher-rate tuning does not
block the repaired 2.5 MS/s canary.

**1. Make the acceptance rules executable.**

Freeze a small explicit candidate profile: source rate, upper edge, pilot-center
frequency convention, acquisition/exact/margin gates, template/filter hashes,
host search/gates, timing/CFO comparison tolerances and source identities.
Use the existing metadata/CLI paths. For initial regression, preserve the tested
Q16 tuple `[13107, 19661, 9831]` explicitly; .20 is a baseline to evaluate,
not a claim of final sensitivity. Read back and attest the profile at capture.

Make detector-qualification failure return nonzero, separately retaining
execution status. Add tests for a completed miss, a false positive and a
partially recovered strong case. Count complete truth frames one-to-one;
extra detections and unexplained unmatched positives must remain visible.
Update stale 176-sample descriptions to the instantiated 352-sample grouping.

Exit: the documented capture configuration reproduces the numerical profile,
and a deliberately failing detector cannot pass the release check.

**2. Repair scheduling and finite completion as one bounded pipeline change.**

Trace proposal time, selected epoch, ring age, native-read duration and scorer
service time on existing failed cases. First prototype separating acquisition
of a complete 64-symbol correlation vector from its DFT scoring, using one
bounded staging slot if measurement supports it. Size storage from actual
occupancy and deadlines. Queueing only epochs is acceptable only if their
entire required native support is proven to survive until consumption.
Preserve explicit overload/expiry counters and unconditional IQ export.

Define finite close: stop accepting new work at a declared boundary, finish
work with complete retained support, classify incomplete end-of-observation
work, drain all completed events, then expose stable final accounting. A stuck
fully supported job must still fail. Test stop during acquisition, native
collection, DFT, event delivery and a stopped ADC clock; then start a new visit.
Expose necessary endpoint/state evidence through a versioned extension or new
ABI with matching driver/host decoders. Preserve existing GLR1 v1 meanings and
old recorded files.

Use the measured 60 MS/s critical path to guide timing work: pipeline the
native reader's 64-bit availability comparison or use proven bounded-distance
credit logic, retaining full absolute-coordinate and wrap validation. Avoid
spending iterations on placement seeds before addressing this path.

Exit for each candidate rate: recover all complete isolated strong frames in its regression,
with no unexplained admission loss; overload remains explicit. Every finite
test has conserved candidate/result/tail accounting and stable final events.
Exported IQ and completed raw statistics remain bit exact.
The changed full design passes setup/hold, CDC/skew and no-PSS/no-native-DMA
checks without relaxed constraints. Record remaining physical margin honestly.

**3. Refresh scientific evidence on the candidate that will be loaded.**

Use the existing 24 upper-edge, 20 ms saved records first. Diagnose losses by
acquisition, selection, admission, scoring and comparison support. Deduplicate
overlapping host frame supports; the old 175 unmatched supports are not 175
independent known misses. These saved files are 2.5 MS/s development IQ and
cannot qualify native 5/10/25/60 MS/s RF behavior.

After the profile and scheduler are frozen, run a predeclared fresh synthetic
seed/timing matrix for the candidate rate, ultimately covering all five. Include full/partial frames,
CFO offsets, weak signals, tones, scrambled pilots and rolled-code ambiguity.
Use untouched saved positives/controls where available, preserving actual
native rates and provenance. Start with small batches and report measured
runtime before expanding; do not turn replay into a long campaign.

Keep FPGA and blind host estimators independent. Compare complete common time
support, timing and CFO within a declared observable band; do not require raw
score equality. Existing five-output-sample/2 kHz matching tolerances are
engineering limits to validate. Preserve out-of-band, incomplete, ambiguous
and unmatched results separately. Define sensitivity/false-alarm acceptance
before evaluating holdouts; otherwise label the release experimental with
measured limits, not detector-qualified.

Exit: current-code saved-data regression, fresh frozen synthetic results, exact
arithmetic evidence and an explicit sensitivity/ambiguity envelope accompany
the exact candidate. All strong/control release criteria pass.

**4. Prove one USB receiver, then climb the rate ladder.**

The designated first canary is .18, serial
`1040007c4a94000211000b009186843ef2`. The original FPGA task
`01a05dc1-7a4b-71c1-9ae6-189b51bd83a1` was active when inspected for this review;
there is no allocated window recorded here. Reconcile ownership and obtain
explicit authorization for any new RF collection before operation. Keep each
collection window at most 30 minutes and individual planned captures at most
30 seconds. Existing collection tools already enforce the latter limit.

Start with a statically reviewed 2.5 MS/s RAM candidate. Preserve exact device,
setup, source firmware, QSPI and recovery receipts; keep TX muted. Run RX
PN/data-eye calibration, retain delays and actual clock/rate results, and
explain each remaining external timing path/exception. Calibration is a
controlled canary measurement: requiring already completed live qualification
before the first RAM load would create a circular gate.

The current RAM policy requires a verified TX-capable 1R1T original image,
with TX quiesced, for its preboot/recovery checks. Confirm that prerequisite
against the actual owner-supplied baseline. If it differs, prepare and test a
specific compatible lifecycle policy or obtain an approved baseline before
execution. The existing candidate plan alone does not establish compatibility.
Bind each capture to the successful deployment receipt and manifest hash;
GLR1 registers do not expose a bitstream hash, so a firmware label alone is
insufficient source evidence.

Run 120 ms, 1 s, 10 s and 30 s captures, plus a finite 4 MB prefill/drain test.
Require exact requested IQ bytes, contiguous mapped endpoints, zero transport
loss/overflow, reconciled event counters and finite-close classification.
Measure sustained 10 MB/s IQ service including event traffic and durable-file
completion. Characterize prefetch/cache effects before using the finite drain
rate to claim headroom; source-paced throughput alone is not spare capacity.
Inspect the actual link capacity and buffering before setting achievable
service-margin and consumer-stall limits, then freeze those limits before the
qualification run. Require measured spare service above the 10 MB/s payload,
adequate buffering for the tested stalls, and zero loss in normal operation.

Exercise cancellation, a bounded slow consumer, timeout, event-consumer failure
and stop/restart. Deliberate overload must produce explicit failure and retain
available evidence; restoration must return the exact expected original image
and allow a fresh clean observation. Repeat the same short ladder at
5, 10, 25 and finally 60 MS/s, with a rate-matched image and fresh calibration.
Do not make first 2.5 MS/s success wait for all higher-rate tuning.

Exit per rate: repeatable RAM boot, calibrated receive path, loss-free normal
IQ/events, measured transport, tested failure recovery and a verified return
to the original firmware. This proves device operation; ambient bench noise
does not prove live Starlink detection.

Static review and a controlled interface-only canary can proceed alongside
steps 2–3 using a separately identified existing image. Detector qualification
must use the final repaired candidate and refreshed evidence.

**5. Complete the persistent route, then validate outdoor RF.**

Extend the existing device-tool persistent canary/return-layout policy narrowly
for GLRT and produce the canonical persistent artifact with exact hashes.
Keep board identity, source/target layout, bootloader/QSPI protection, TX mute
and recovery checks. Test the policy's accept/reject cases offline.

After RAM qualification, and with explicit authorization for persistent
flashing, prove local persistent boot, workload, reboot/cold-return and rollback
on .18 for the immutable bytes intended for deployment. A cold-return test
must use an available controlled power path or wait for an allocated hardware
action; do not assume the user can rewire equipment. Then define the distinct
reviewed LAN-promotion profile. Repeat qualification for any subsequently
promoted rate-specific image; one image's boot test is not a five-image pass.

The outdoor .17 receiver is serial `104000bac4950008230026001b440a003a`,
Ethernet-only, with its existing powered LNB/bias-tee arrangement. Inspect its
current topology and known recovery route through the owner. Record LNB/LO,
pilot-center convention, rate, bandwidth, gain and settling. Deploy only the
locally qualified identical bytes through the supported LAN lifecycle, and
verify serial/image identity and TX mute after return.

Repeat RX PN/eye calibration, delay recording and sustained IQ/event transport
qualification on .17 at every promoted rate. These are specific to this board
and its Ethernet/IIOD path; .18 USB results cannot supply them. Check negotiated
link capacity before choosing the service-margin target. If this path cannot
sustain the required 10 MB/s plus events and protocol overhead, report the
deployment blocker without changing the promised IQ rate or hiding gaps.

Use short fixed-frequency observations within an explicitly authorized window.
Finalize and hash IQ first; run unseeded host GLRT offline; compare only then.
Require nonvacuous, reproducible FPGA/host agreement on observable complete
supports, with every comparable mismatch accounted for. Repeat on the required
rates and record recall, busy/expiry losses, controls and ambiguities. Reuse
these recordings for diagnosis instead of immediately collecting more RF.

Exit: supported deployment and recovery on .17, rate-specific live evidence,
and truthful detector limits. A single matching event is a milestone, not the
entire detector acceptance gate.

**6. Finish the operator handoff and decide production promotion.**

Publish a single concise operator procedure: select immutable rate/profile,
check exact device and owner window, deploy, configure, capture, compare,
inspect outcome and restore. Reuse the existing PPU and capture tools. Pin
firmware/component/tool identities, numerical profile, calibration, transport,
live results and recovery receipts in one release record. Archive superseded
candidates as evidence without presenting them as current choices.

The first deliverable is an explicitly experimental, repeatable deployment.
Production promotion requires the agreed sensitivity/control envelope and
successful operational/recovery gates, followed by explicit deployment approval.
Keep no-PSS, one receiver, fixed-frequency operation and 2.5 MS/s export in
scope. Hopping, a second receiver, new radio hardware, detector redesign and a
new dashboard are not prerequisites for this milestone.

**Completion evidence**

For each required source rate, the release record must answer: which bytes and
settings ran; whether physical reception and 10 MB/s export were measured;
whether every event and finite tail is accounted for; which same-IQ blind-host
matches and mismatches occurred; what detection limits remain; and how recovery
was demonstrated. Until those answers exist, distinguish implemented, routed,
RAM-qualified, persistent-qualified and live-validated status explicitly.

The next concrete work package is steps 1–2: fix the reproducible profile and
qualification gate, then stage complete detector work and close finite
observations. Prepare the owner window and persistent policy in parallel.
