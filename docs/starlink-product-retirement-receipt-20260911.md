# Private product retirement receipt — DO NOT MERGE

This experiment changes only the private product slot's retirement interface
inside the actual FFT/buffer subsystem. Native 60 MS/s fine search and the
independent 2.5 MS/s inspection stream remain required and their receiver
sources are unchanged. There is no radio deployment or full-board signoff.

## Contract

The bank's existing request toggle and synchronized acknowledgement expose
registered ownership. Their XOR must be known one to authorize retirement of
a private held-final slot. Nonfinal retirement still follows physical bank
capacity. Actual bank publication retains the original current authorization,
framing, identity and fault checks. No bank/stage RTL or logical register is
added; all 35 parent runtime modules remain byte-identical.

The old `staged_product_ready` expression remains unchanged as the current
public eligibility/injection boundary. It is no longer connected to the private
stage's output-ready port, which consumes `product_retire_ready`. Existing
fault campaigns therefore still target actual prospective publication, not the
later private retirement. Unknown owner/ACK values never count as a receipt.

At a successful publication edge the bank changes ownership and the private
final word stays full. On the next healthy edge it retires from that registered
receipt, with no same-edge refill. The bank cannot accept another write while
consumer-owned. Unpublished final RAM rewrites remain permitted while current
publication authority is withheld; these are not duplicate publications.
Current faults can still quarantine the private slot before retirement.

## Checks

The initial component suite passes all 26 tests. It checks exact top deltas,
unchanged public eligibility and authorization, 1,024 four-state combinations
of final/nonfinal, readiness, fault and ownership inputs, plus unsafe mutants.
The real mailbox comparison covers 12 good blocks / 6,144 reads, 420 malformed
metadata cases, six framing cases and eight resets, with receipt-edge checks.
Early-retirement, missing checks and lost write-through/abort variants fail.

The complete regression passes 1,646 distinct tests, including the new 26
component/witness and 55 route-admission tests. The separate component run
is a subset. Synthesis passes with DCP
`b4c0d2cd4c5b6911cfdf53ff0e0fb7c5ab2687c571317b873d51629645d3c2e6`.

The healthy actual FFT run matches 64,512 numerical words and retains 4,178
service clocks (23.874 us at 175 MHz, below 5,215 clocks). The new observer
checks 88,545 fast cycles, 18 actual bank publications, 18 receipt retirements
and 18 extra private final holds. It compares ownership changes against actual
checked bank publication and forbids post-publication writes and final refill.

Five additional actual boundaries test a 128-clock publication delay, either
reset during the extra hold, a fault after publication and a bad certificate
at prospective publication. The previous 54 cases remain enabled unchanged.
All 59 cases pass. The auxiliary observer checks 646,240 fast cycles, 100
actual publications, 100 extra private holds and 98 receipt retirements. The
other two held slots are deliberately cleared by the two pending-reset cases.
Both runs retain the same 64,512-word CSV hash as the parent:
`df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
Simulation is not exhaustive formal proof, RF accuracy or continuous RX proof.

## Routed result: targeted path closed, whole subsystem still fails

The unchanged Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe routes
all 8,597 nets without errors. No exceptions or clock relaxation were added.

| Metric | Parallel-reference parent | Retirement receipt |
|---|---:|---:|
| WNS / TNS (ns) | -1.435 / -635.472 | -1.426 / -446.926 |
| Same-domain 175 MHz WNS | -1.255 ns | -1.348 ns |
| Failing setup endpoints | 1,175 / 14,505 | 839 / 14,510 |
| LUT / FF | 2,748 / 5,913 | 2,748 / 5,913 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Targeted endpoint inspection verifies product occupancy at **+1.551 ns**
(previously -1.255 ns): four LUT levels, 4.110 ns data delay. The product
identity certificate remains passing at **+1.222 ns** (previously +0.729 ns).
These are actual worst paths to the named D pins, not missing-path assumptions.
The independently pinned inspection does not change the checkpoint/constraints.

Whole-subsystem setup still fails: overall worst is output-bank metadata bit 6
crossing to slow metadata (-1.426 ns). The worst 175 MHz path is now engine
metadata bit 45 through forward descriptor equality/current fault into descriptor
bit 42's clock enable: six LUT levels, 6.809 ns, 79.528% routing. Aggregate
slack/failure count improve, but same-domain worst slack regresses; do not claim
whole-subsystem timing closure or promote this candidate.

Hold +0.062 ns and pulse +1.830 ns pass. Combinational/latch-loop counts are zero.
114 inputs and 124 outputs remain unqualified. CDC reports nine CDC-3 and 208
CDC-15, no CDC-10. The fault synchronizer is driven directly by a physical
replica of the scalar fault register, not an OR of distributed registers. That
replica and all held-metadata CDC paths still need full-board qualification.

Next investigate a private descriptor-load enable independent of current
capture/comparison fault logic. A descriptor may potentially be captured on a
reservation edge that also quarantines the bank, provided it can never authorize
capture, seal, replay, publication or reuse. Preserve state/fault timing and
prove current controls/valid payload against the parent, explicitly cover
simultaneous reserve/fault and X/Z, then repeat actual faults/reset and route.
The separate full receiver CDC/I/O/calibration/continuous-RX gates remain open.

Routed DCP: `74f86e9edbaaf1ec864c27f5454493712ce75633bd4898489f07717860e873b8`.
Actual main/auxiliary durations: 54.457 / 255.096 s. Synthesis: 105.126 s;
routing: 57.676 s; endpoint observation: 10.575 s. These are experiment
runtimes, not deployment estimates.

## Reproduction and release scope

Branch `codex/starlink-rx-only-do-not-merge-product-retirement-receipt`.

- Main inventory: `40dbfcc7a30e1d66f0c4e1319a4d5ac5dd1dd9b29f0b3e14e2c64bc570d74e48`.
- Auxiliary inventory: `654205f6ad1a1b321e451fb5339c743de5b00f7e2737f775764b0f715f7b1622`.

Use `product_retirement_receipt_experiment.py` for source preparation, actual
FFT and synthesis. `route_product_retirement_receipt.py` requires all numerical,
fault/recovery and retirement witnesses from matching sources before routing.
`audit_staged_fft_route.py` verifies routed checkpoint/report identity; the
recording helper retains sources, numerical streams, tests and raw reports.
`inspect_product_retirement_receipt.py` separately measures the actual occupancy
and identity register endpoints and checks report values against timing objects.

Primary HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Full receiver
timing/CDC/reset, actual 60 MS/s calibration, continuous reception and real
IIO/Ethernet remain release gates before reversible PPU deployment to `.18`,
then Ethernet-only `.17`. No radios or PPU/main were touched; `.14/.20/.21`
remain excluded.
