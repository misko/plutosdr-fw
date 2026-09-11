# Clocked admission facts — DO NOT MERGE

Baseline: staged handover FW `9e24e0328`, HDL `ac06d966a`; actual numerics and
fault/reset tests passed, but routed WNS was -3.970 ns. The worst path traversed
input identity/certification and cutover logic into the admission receipt.
This experiment is not a receiver release or a replacement for native fine search.

## Contract and implementation

The scheduler holds the captured bank descriptor, phase and lease while waiting
in ARM_JOB. Once the result slot, cutover reset capacity and (for inverse jobs)
descriptor allocation are available, a new certificate captures 22 independent
good/bad facts. Nineteen are a partition of the existing offered/contextual
current-fault predicate; three record the private capacity conditions.

On the next edge a clean, held certificate may issue one private result-owner
admission. It cannot refresh itself, survive request withdrawal, survive reset
or quarantine, or be consumed twice. Every bit must be known one in simulation.
The current guard capacity is still checked at consumption. Banks are not read
or released while the certificate is being prepared.

The local result-guard copy has an explicit certified-private-admission option.
Its capacity output omits active-stream current fault logic. Default admission
is unchanged. In the opted-in integration, a new fault may coincide with private
occupancy acceptance; the unchanged fault bank quarantines that occupancy on
the same edge. The scheduler consumes its admission receipt on the following
edge, when registered quarantine prevents emitted input start/configuration.
Cutover's new capacity observation does not replace its full actual admission
validation. All output publication, ACK, numerical and detailed current fault
checks remain. No globally delayed fault bit is used to authorize output.

Only the existing registered/offered/contextual combination opts into the new
contract. Local guard/cutover sources are derived from the previous frozen
runtime; default receiver sources and the primary production HDL gitlink are
not modified. The real FFT, source/product/inverse buffers and independent
reader ownership remain in the integrated subsystem.

## Test design and early evidence

The real-FFT bench retains six numerical/readiness contexts, both stopped-reader
reset epochs and seven existing fault cases. It additionally checks, on every
active fast edge, that the partitioned reject facts equal the original current
fault predicate. New cancellation cases inject raw output before fact capture,
before certificate consumption, or before receipt application; change the
captured lease at consumption; and reset either clock domain with a pending
certificate. No emitted start, configuration, input or publication may follow
cancellation. These are bounded tests, not an exhaustive CDC/formal/RF proof.

Five isolated certificate tests pass, including 66 zero/X/Z bit rejection
trials, held evidence, single use and fresh-epoch recovery. Four executed unsafe
mutants are rejected. The first test wrapper expected no Icarus finish notice;
its receipt assertion was corrected without changing RTL, and that failed test
run is preserved.

V1 actual integration failed before the first inverse job: it froze unavailable
allocation capacity and never retried, eventually tripping the unchanged
preflight watchdog. Its source-matched synthesis completed, but V1 is not routed
or accepted. V2 begins capture only when the small capacity conditions are
available. The failed V1 source and actual logs are retained.

V2 actual generated-FFT simulation passes in **72.50 seconds**. All **64,512
numerical records** independently match the pinned prior actual reference.
Both stopped-reader resets, seven original fault cases and six new admission
cancellation cases pass. The partition equality assertion is checked throughout
the active fast-clock campaign. It observes 59 admission and 52 close receipts.
Service intervals are 3657/3657/4927/11728/3657/3657 fast clocks; only the
deliberately 9000-clock-stalled reader is excluded from the 5215-cycle cap.
Normal service increases by two clocks from V4, with no numerical change.

**307 regression tests pass in 42.12 seconds**. Seven additional audit controls
require all admission cancellation markers and reject missing cases/terminal,
missing partition proof, emitted starts, publications or releases after cancel.
These parser tests do not count as additional actual hardware executions.

V2 frozen source inventory SHA256:
`a6c03ad7c81a46fee02e30f20e52cd5e66f805dd99f0e07f556b13da09ed40b3`.
Numerical CSV SHA256:
`b3543f3daa7a99d9fc6e945b5af7e9febaabab00cc6eed4761db41f1d4ce2c59`.
All before/after source checks pass. Real FFT generator/wrapper, device and
diagnostic clocks are unchanged. V2 synthesis completes in 111.74 seconds;
V2 routing completes in **56.05 seconds**, but fails at **-3.451 ns**, TNS
**-1926.674 ns**, **1602** failing setup endpoints. This improves from the
handover baseline's -3.970 ns / -2566.980 ns / 2261 endpoints but does not close
timing, and still trails the older staged-output -2.726 ns WNS baseline.
Hold +0.062 ns and pulse +1.830 ns pass; 8303 nets fully routed with zero errors.
Resources: 2772 LUT / 5565 FF / 21 DSP / 15 RAMB18. CDC remains unqualified:
5 critical, 210 warning and 4 informational findings; 114/124 unconstrained I/O.

The worst V2 path now runs from product-bank metadata through current completion
validation into the live descriptor lookup and then the 70-bit writer comparison:
16 logic levels, 9.110 ns data delay (6.449 ns routing). V3 makes that private
lookup available under the already-held inverse descriptor ownership, rather
than gating it with the fault-dependent completion-valid signal. Full lookup
found/uncommitted/descriptor checks still occur at accepted completion, and no
lookup result itself authorizes output. The bench additionally asserts that
every accepted completion has held inverse descriptor ownership.

V3 actual generated-FFT verification passes in **73.66 seconds**, with the
complete numerical CSV and every parsed service/reset/fault/admission result
identical to V2. The combined regression now passes **321 tests in 43.87 seconds**,
including the seven admission-audit controls against both actual campaigns.
V3 inventory SHA256:
`a2d6340562dbbbdea164f991e2e50d283805c2d43b1fbbe0121c57dc193c617b`.
Source-matched V3 synthesis/route complete in **105.80/55.04 seconds**. Routing
still **fails** at **-3.080 ns**, TNS **-1541.860 ns**, **1511 / 13468** failing
setup endpoints. Hold +0.060 ns and pulse +1.830 ns pass; 8281 nets fully route
with zero errors. Resources: 2765 LUT / 5552 FF / 21 DSP / 15 RAMB18.
This improves WNS, TNS and endpoint count over both V2 and the handover baseline,
but WNS remains worse than the older staged-output -2.726 ns baseline. It is
progress within the current architecture, not overall timing closure or a release.

The new worst path is held phase → input identity/fault checking → completion
receipt: 11 logic levels, 8.697 ns data delay, including 6.877 ns routing.
The next step is clocked producer-completion facts with a held ownership/identity
certificate, full cancellation on reset/fault, and explicit quiet/raw-event checks
before core reset or reuse. Do not simply delay global fault publication fences.
Repeat the real-FFT fault/reset/overlap campaign and source-matched route before
integrating any further features. Other top paths still include descriptor
validation; fixing this single path will not itself prove timing closure.

V3 CDC remains unqualified: 5 critical, 208 warning and 4 informational findings;
114/124 I/O ports lack board delays. No timing exception was added. All vendor
handles are terminal; checkpoints, source receipts, four clock-pair reports,
summary, utilization and routing inventory pass the independent report audit.
V3 synthesis DCP SHA256:
`b718847bb26446357b0a6644b662a857e79afbfde8c8e3721c59010c73837fd0`.
V3 routed DCP SHA256:
`53a8540ee842e9da4aad0e8218478c8f28787c2f34fab3a29fdd73a1646fad76`.

V2 synthesis DCP SHA256:
`274a11736e5735531616de3e1ee1ade772b18142fd31be9d52d9d69e1d8d0d5d`.
V2 routed DCP SHA256:
`10844de3ba28a40fc3491f0a4a8bed932e864ad5f2a5591803f5f415c22faf54`.

## Unchanged release gates

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO remain required.
Passing this subsystem would still leave full receiver route/CDC/reset/board
constraints, sustained capture and actual RX calibration, `.18` reversible
canary and `.17` PPU Ethernet-only deployment with pinned rollback. The final
300-second / 120 ms valid-dwell campaign must compare FPGA evidence with blind
host GLRT. No radio, PPU or main branch is changed in this experiment.
