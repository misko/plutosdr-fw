# Raw ownership readiness / certified forward ACK: still fails175MHz

This separately authorized follow-up preserves the tested public controls,
ACK-clear edges, fault reasons and numerical outputs. The single diagnostic
route still fails:175MHz setup−3.144ns, versus−3.855ns for completed-input-only
and−2.557ns for original169f9fb. No promotion, receiver build or radio test.

Tested pins: FW `f57d1fb75177b84cfce1a9dc39c6713b12fe44db`, HDL
`fb0f819d934c5d4590a2421bd75942ab30bec6c4`. The earlier failed study is retained
at FW `ae0a51d92`, HDL `b8c98c23`; neither its source nor evidence was replaced.
Evidence is `hdl/library/starlink_pss_acquisition/evidence/raw-readiness-v1/`.
The complete original runs are `/tmp/starlink-completed-input.5EaJuD/actual-v3`,
`synth-v2`, `route-v2`, and `join-mutation-v2`. All seven synthesis RTL files
byte-match the passing actual-core snapshot and tested HDLfb0f819d.

## Change and executed checks

Only two functional wrapper substitutions were made: when forward_committed,
the result guard receives raw `product_bank_valid` readiness; the controller's
forward ACK_DRAIN explicitly requires `forward_handoff_ack`. The complete
identity/position/TLAST/external-fault predicate, independent512th-read mailbox
ACKs, default guard behavior and sticky reason storage are unchanged.

An original-full-ready shadow compares exact guard/public controls and ACK-clear
edges. Raw-ready and certified-ready may differ only while the forward guard
is inactive and its current or sticky fault blocks ACK retirement. The original
44-block/10-fault numerical suite passed unchanged, including130provisional
inverse words; its nominal maximum forward interval remains4540fast clocks.
An additional11handoff faults,1039raw/certified-ready differences,4late-ACK
boundaries and a one-sided handoff-reset/healthy recovery passed, with573353full
shadow comparisons. Malformed handoff descriptor, first ordinal and TLAST,
orphan frame/status/output, duplicate start and late vendor fault are included.

Important preserved limit: the three new orphan frame/status/output events on
the controller-drain edge AFTER a healthy guard ACK-clear each produced the
baseline's private core reset/phase advance. The full result guard is not reset
by core reset: its exact sticky reasons survived, global quarantine preceded any
inverse admission or result publication, and only an epoch reset recovered.
There is no claim of a same-edge controller veto for these orphan events; no
broader fault wiring was introduced under an equivalence claim.

The initial actual-v2 run passed the original suite, then failed an overstrict
new assertion after an orphan fault: it required current idle_fault_now even
when sticky protocol_fault already prevented ACK. Only that assertion was
corrected to accept current OR sticky fault; full control/reason comparisons
remained unchanged. The failed frozen bench/log are retained in
`failed-assertion/`. Final actual-v3 passed all added cases. The actual-FFT
join-bank-ready mutation again failed its exact held-final witness. Fifteen
focused pytest tests passed; the previous74passed/6explicit old-physical-probe
skips remain the regression evidence for the unchanged checker/guard RTL.

## Measured isolated cost and diagnostic timing

| Measurement | Synthesis | Route |
| --- | ---: | ---: |
| LUTs |1826|1840|
| Registers |4375|4449|
| Slices |not placed|1072|
| DSP48 / BRAM tiles |21 / 7.5|21 / 7.5|
| Unique control sets |not measured|55|
|175MHz setup / hold slack,ns |not routed|−3.144 / +0.059|
|100MHz setup / hold slack,ns |not routed|+2.478 / +0.100|

Worst175MHz setup: `next_inverse_reg/C` → `state_reg[0]/D`,8.806ns
(2.746logic/6.060route),15levels including5CARRY4. The input metadata comparator
now reaches controller state through fault/admission/ACK logic; removing the
kernel-join endpoint from the worst path did not close timing. Worst175MHz hold
is the FFT `processing_address_generator/mux_addr3/...Q_reg[6]/C` →
`memory_control[3]/...srl_sig_reg[22][6]_srl23/D`,0.263ns
(0.141logic/0.122route),slack+0.059ns. Unabridged endpoints and all20paths are
retained in `route/receipt.txt` and the four per-clock timing reports.

Worst100MHz setup is `source_bank/metadata_in_hold_reg[6]/C` →
`source_bank/write_position_reg[1]/CE`,7.062ns(2.521logic/4.541route),slack+2.478ns.
Minimum is `fast_fault_slow_reg[0]/C` → `fast_fault_slow_reg[1]/D`,
0.197ns(0.141logic/0.056route),slack+0.100ns.

All6416routable nets routed with0routing errors. Constraints are byte-equivalent
to the original inherited100/175 resource probe except for the generated output
path comment; no exception or clock relaxation was added. External I/O remains
unqualified, with114missing input delays,124missing output delays and139CDC-15
warnings. These counts and the original generated-IP clock limitation are not
waived. Exact normalization/scoring, both detector stages,2.5MS/s pilot export,
whole-receiver timing and live evidence remain outside this isolated slice.

This follow-up used one synthesis and one diagnostic route. No further physical
iteration was run. Root owns any next controller/admission factoring and its
comparison with the independent score-integration branch.
