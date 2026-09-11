# Balanced forward identity — 2026-09-11

Branch `codex/starlink-rx-only-do-not-merge-balanced-forward-identity`.
DO NOT MERGE firmware/HDL into main. **Timing fails; do not deploy.**

## Implemented experiment

The previous critical path contained a six-stage carry chain implementing the
70-bit forward-bank descriptor equality. This candidate changes only its
combinational structure: 23 three-bit comparisons plus the remaining high bit,
four six-input reductions and a final reduction. Kept intermediate nets make
the first two levels explicit to synthesis. No logical registers or fault
latency are added. Equality and the final known-true check retain four-state
semantics, including mismatch dominating unrelated unknown bits.

A new derived bank and top leave all 29 parent runtime modules unchanged.
The top changes only its module name and bank instance type. The product
current-fault veto, 33-bit private fault pipeline, scalar fault CDC source,
bank RAM, capture/seal/replay state machine, reset and real ACKs are retained.
Native 60 MS/s fine and 2.5 MS/s inspection receiver sources are unchanged.

## Functional verification

**1,412 distinct tests pass:** 1,381 regression (1,347 inherited + 34 new)
and 31 route-evidence unit tests. A separate 34-test component run is a subset,
not another 34. Twenty-one bank scenarios compare current controls and valid
replay payload against the immediate parent on both sides of each clock edge;
private write-count/exponent differences are forbidden even during quarantine.
The comparator matches the old expression on 20,351 directed/random vectors
including every descriptor bit, X/Z and known-mismatch cases. Mutants omitting
the high bit or a middle reduction are rejected. These are simulation checks,
not a formal exhaustive state-space proof.

Both actual generated FFT campaigns match all **64,512 numerical words**
against the frozen original reference. All six healthy contexts retain
**4,178 service clocks**, 23.874 us at 175 MHz, below the 5,215-clock budget.
CSV and all original numerical/service/identity/fault observer results match
the parent. The 43 actual fault/reset/delay cases still pass; the recently fixed
late product-publication boundary is retained.

The added actual observer compares the bank's new and old descriptor predicates
every fast cycle: 88,545 main cycles / 9,216 captures and 501,624 auxiliary
cycles / 50,167 captures. Capture counts include cancelled/private work, not
only completed blocks. No simulation or regression failed in this campaign.

## Physical realization and routed result

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no new timing
exceptions or relaxed clock. Main/auxiliary source identity and full evidence
are checked before and after routing the exact synthesized checkpoint.

The independent pinned routed-netlist inspection finds all **24 group nets and
four reduction nets**. All 28 upstream comparison cones contain **zero carry
cells**. The unkept final AND may fold into its consumer LUT; the targeted
routed critical path is now all LUTs rather than the old carry chain. This
confirms the requested topology was implemented, not that its placement is
fast enough. Netlist observation does not modify constraints or the checkpoint.

| Metric | Product-fence parent | Balanced comparison |
|---|---:|---:|
| All-path WNS | -1.224 ns | -1.420 ns |
| All-path TNS | -519.788 ns | -420.378 ns |
| Setup failing endpoints | 1,217 / 14,494 | 939 / 14,505 |
| Same-domain 175 MHz WNS | -1.174 ns | -1.420 ns |
| LUT / FF | 2,780 / 5,907 | 2,805 / 5,912 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Aggregate negative slack and failure count improve, but worst-case timing
regresses. **Do not promote this as a timing improvement or remove the product
publication fix to recover slack.** Physical FF count includes synthesis/
placement effects; the comparator adds no RTL state.

All 8,675 nets route without errors. Hold +0.013 ns and pulse +1.830 ns have
no failures; combinational/latch-loop counts are zero. 114 inputs / 124 outputs
remain OOC-unqualified. CDC reports nine CDC-3 and 209 CDC-15 warnings, no
CDC-10. The additional warning is source metadata receiver bit 20's replica;
the reset-release CDC source also becomes a physical replica. Both require
full physical/ownership qualification. The scalar fault register remains the
direct source of its two-stage synchronizer.

Worst path is forward-bank descriptor bit 36 into the forward guard's latched
fault reason: eight LUT levels, 6.989 ns data delay, **77.306% routing**. The
comparison's carry chain is gone, but the same-edge path still travels through
the bank's current fault/readiness and shared external-fault/control logic.

## Next engineering gate

Preserve both candidates; the parent remains better for worst-case slack.
The next experiment should separate the forward bank's registered private
fault/ownership status from its same-edge public fault veto. Local RAM and
seal/replay rejection must retain immediate checks. Any private status latency
must be bounded and proved unable to publish, ACK/reuse or survive reset.
Explicitly retain the current product-publication fence and test bad first,
middle/final descriptors, seal-edge faults, unexpected returns and reset.
Then rerun the actual campaigns and route; do not assume a pipeline will close
timing. Held metadata CDC qualification with real board clocks remains a
separate requirement, not a reason for blanket timing exceptions.

Full receiver integration must preserve native 60 MS/s fine and independent
2.5 MS/s inspection. Timing/CDC/reset, 60 MS/s calibration, continuous RX and
sustained IIO/Ethernet remain open before reversible PPU deployment: `.18`
canary, then `.17` outdoors over Ethernet. No radios or PPU/main were touched;
`.14/.20/.21` remain excluded. Primary HDL is not promoted.

## Artifact identities

Evidence root: `/dev/shm/starlink-balanced-forward.TAQ78ZtF`.

- Main inventory `3fdb6238d577ede67da2c3d4778d3ddb1a9e07f19a311f72482051d95d2a15a1`.
- Auxiliary inventory `775bd7a3da5be744d7fa4bc93728003332923b7e80e320ae44a3f8a69c92fc03`.
- Actual CSV `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
- Synthesized DCP `6ccf01da2811b5f851dc00b26eed73daf20087ec273e5f6af877540b89376bc8`.
- Routed DCP `cb0bf25b79c63c903377649130efba86e3bc676a93efe46a721f73aec75d1b60`.

Use `balanced_forward_identity_experiment.py`, `route_balanced_forward_identity.py`,
`audit_staged_fft_route.py`, `inspect_balanced_forward_identity.py` and
`record_balanced_forward_identity_evidence.py`. Archive includes full current
actual streams, prepared source, both checkpoints, raw route/netlist reports
and tests; historical regression payload duplicates remain local with hashes.
