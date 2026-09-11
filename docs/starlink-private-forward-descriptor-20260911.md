# Private forward descriptor capture — DO NOT MERGE

This isolated actual-FFT/buffer experiment separates private descriptor storage
from the unchanged bank controller. Native 60 MS/s fine search and independent
2.5 MS/s inspection remain required; their receiver sources are unchanged.
No radio deployment or full-board qualification is claimed.

## Exact change and safety boundary

The descriptor register now resets in its own block and loads on the existing
`reserve_valid && reserve_ready` condition. The state machine no longer writes
that register. Its current/sticky fault handling, state transitions, counters,
exponent, RAM, capture/seal/replay and registered private status are unchanged.
The derived top only selects the derived bank. All 36 parent runtime modules
remain byte-identical; two derived modules are added, with no logical register
or processing latency added.

A reservation and current fault on the same edge may update the private copy
while the original bank would keep its old descriptor. Both banks must enter
identical quarantine on that edge. Descriptor differences are allowed only with
fault asserted and capture/reservation/replay disabled. They cannot become
publication or reuse authority, and common reset must clear both copies.

## Component and actual-FFT verification

The initial 27-test component run passes: exact inverse transforms, 21 existing
512-word bank scenarios, and a 768-case control grid using known/X/Z descriptors
and all four-state reserve/capture/seal/abort combinations. The grid uses a
four-word bank, and each case performs a fresh reset/replay recovery, totaling
3,072 checked reads. Three unsafe mutations are rejected. Full-width state-space
or formal equivalence is not claimed.

The actual bench adds the unchanged parent bank as an independent simulation
reference, driven by the same signals—including injected faults. Its controls,
valid replay payload and all non-descriptor bank state are compared before and
after fast-clock edges. The reference bank is not synthesized into the DUT.
Six additional boundaries cover reservation with capture/seal faults, X/Z,
unknown private descriptor data and both resets while the rejected copy is held.
The prior 59 fault/reset/delay cases remain enabled unchanged.

The healthy actual generated FFT run matches all 64,512 numerical words and
retains 4,178 service clocks (23.874 us at 175 MHz; budget 5,215 clocks). The new
observer performs 177,096 comparisons, with 18 loads and no descriptor differences
or faulting loads. These are simulation results, not continuous RX or RF proof.

The full regression passes 1,753 distinct tests, including 44 new component/witness
and 63 route-admission tests. Both actual FFT campaigns pass all 65 boundary
cases. The auxiliary reference performs 1,376,591 comparisons, observes 145
loads including six faulting reservations, and permits 910 descriptor-difference
observations only behind matched quarantine. Every non-descriptor bank state
and current/valid-output comparison remains exact; each new boundary recovers
512 correct fresh reads and one real release. Numerical CSV SHA remains
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
Synthesis passes with DCP
`00ea737905f2650371b3415d4f56cf31993aa7de76f2fab41cbff527bd46d867`.

## Routed result and next gate

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no exceptions
or clock relaxation. All 8,562 nets route without errors.

| Metric | Retirement parent | Private descriptor |
|---|---:|---:|
| WNS / TNS (ns) | -1.426 / -446.926 | -1.304 / -663.577 |
| Same-domain 175 MHz WNS | -1.348 ns | -1.304 ns |
| Failing setup endpoints | 839 / 14,510 | 1,647 / 14,493 |
| LUT / FF | 2,748 / 5,913 | 2,741 / 5,907 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Independent endpoint inspection measures all 70 descriptor CE pins: worst
**+0.129 ns**, versus -1.348 ns previously. It also measures all 70 descriptor
D pins at **+2.226 ns**. Product occupancy and identity remain passing at
**+0.892 ns / +0.316 ns**. Descriptor CE is now four LUT levels / 5.130 ns data
delay. These are existing physical endpoints, not missing-path assumptions.
The CE margin is small and does not qualify full-board implementation.

Overall worst now runs from expected product metadata bit 21 through preflight/
current publication checks to output-stage occupancy: eight LUT levels,
6.963 ns data delay, 78.313% routing. The next reported endpoint is the output
bank request toggle (-1.138 ns). Worst slack improves, but aggregate slack and
failure count regress. This is local path closure, not a deployable subsystem.

Hold +0.052 ns and pulse +1.830 ns pass; combinational/latch-loop counts are zero.
114 inputs and 124 outputs remain OOC-unqualified. CDC reports nine CDC-3 and
208 CDC-15, no CDC-10. Scalar fault again directly feeds its synchronizer;
output-bank metadata bit 35 uses a physical replica. Those held-metadata CDC
paths and the complete board clock/reset/I/O structure remain unqualified.

Next test the already-proven product retirement pattern on the output private
stage: keep actual replay acceptance and bank publication current, but retire
the private final slot from registered output request/ACK ownership. Do not
delay the host-publication fault veto. Verify retained-controller receipts,
descriptor/tag identity, slow-reader stalls, no post-publication writes, pending
resets and late faults before another actual campaign and route. The remaining
current publication path and full receiver timing/CDC gates remain separate.

Routed DCP: `6e54cf83bae142e87493efc4cc67a341ecc3d351a276dbfeb252c11a86efed4e`.
Main/auxiliary actual runs: 54.222 / 273.302 s; synthesis: 107.114 s; route:
56.685 s; endpoint observation: 10.562 s. These are experiment runtimes, not
deployment estimates. A generated reporting-helper syntax error was caught and
corrected before endpoint execution; no pinned RTL or actual run was changed.

## Reproduction and release scope

Branch `codex/starlink-rx-only-do-not-merge-private-forward-descriptor`.

- Main inventory: `ec24a2e7946f68f5d906cbc4435f4613b436e2550d998d57955a15ae9b2a3e6e`.
- Auxiliary inventory: `72063709cdfd36cc0de3d61eebfd99a6ae65b4323de0f0959363dbcc6c5e35ca`.

`private_forward_descriptor_experiment.py` prepares and runs actual FFT and
synthesis. `route_private_forward_descriptor.py` requires matching sources and
fresh numerical/reference/boundary evidence. `audit_staged_fft_route.py`
cross-checks routing/checkpoint/timing reports. `inspect_private_forward_descriptor.py`
measures real descriptor CE/D endpoints and the prior product occupancy/identity
endpoints without changing constraints. The recording helper retains evidence.

Primary HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Full receiver
timing/CDC/reset, actual 60 MS/s calibration, continuous RX and real IIO/Ethernet
remain release gates before reversible PPU deployment to `.18`, then Ethernet-only
`.17`. No radios or PPU/main were touched; `.14/.20/.21` remain excluded.
