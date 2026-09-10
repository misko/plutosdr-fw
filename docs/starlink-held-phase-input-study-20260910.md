# Held-phase input tuple: tested, no new physical measurement

Tested source: FW `2fa89d0ba26545bef0e9c16a56fba0ccc6e3c5e9`, HDL
`d99c251ee16215a1152be3b4ceac65391bc0e073`. The only design delta from
`691966ae` is a direct held-phase tuple for the registered input checker.
Default mode still selects `next_inverse`. The discovery/preflight mux,
controller, both guards, bank ownership, ACK and all active fault vetoes are
unchanged. There are no new registers or logical pipeline cycles.

The preceding failed physical snapshot remains separate at FW `091d0e663` /
HDL `691966ae`, documented in `starlink-preflight-reason-physical-20260910.md`:
175 MHz setup −2.438 ns, state_reg[2]/C to admission_receipt_reg/D, 8.028 ns
(2.860 logic / 5.168 route), 16 levels including six CARRY4. Its state-dependent
source/product metadata selection is removed from this checker's input cone;
the remaining full equality is unchanged. No timing improvement is claimed.

## Invariant and executed tests

The bench retains the literal old state-mux expression as an independent
witness, connected to raw source/product banks rather than the new discovery
wires. A second unchanged input checker consumes that old tuple. On both clock
edges it compares current faults, all sticky reasons, duplicate start,
completion, certificates, core validity and actual bank-read handshakes.
When `slot_open`, it additionally requires equality of phase, valid, all 36
payload bits, all nine ordinal bits, TLAST and all 70 metadata bits. Core
payload/TLAST are compared whenever valid; invalid private payload need not
match. RESET/WAIT cannot have an open checker slot. QUARANTINE is explicitly
covered by vendor-only faults while raw core ready is held low, leaving the
checker open. The admitted phase is held throughout that state.

Actual Vivado 2022.2 core simulation at 100/175 MHz passes in both modes:

| Mode | Paired checker checks | Full open tuple checks | QUARANTINE open checks |
| --- | ---: | ---: | ---: |
| Default | 649,219 | 133,790 | 16 |
| Registered | 1,073,334 | 193,530 | 12 |

Each mode adds 12 real-bank corruption cases: forward/inverse, identity/
ordinal/TLAST, core ready zero/one, at active RUN ordinal 37. These fault the
actual tuple seen by both checkers, not only discovery signals. Same-edge
certification/core-valid/commit are vetoed; exact framing/delivery reasons are
`010` when stalled and `011` when ready. Each mode also passes two vendor-only
open-slot quarantine witnesses and healthy recovery after each one-sided reset.

All earlier result-shadow, final-input/output, duplicate, handoff/orphan and
publication checks remain. The unchanged original receipt reports 44 healthy
blocks, 10 faults, 24,064 forward/product words and 22,658 inverse words,
including 130 provisional prefix words, exactly against frozen arithmetic and
metadata goldens. Eleven handoff faults pass. Registered mode retains eight
scheduling faults/four one-sided resets and all 84 preflight rows, with the
same 60 private-ready differences, 12 invalid-preparation private admissions
and 60 masked-start samples. Existing nominal intervals remain 4,540 default
and 4,548 registered clocks. This island has no score normalizer; these are
FFT/product/inverse boundary goldens, not a new whole-score integration claim.

Python regression: **249 passed, eight explicit older physical-test skips**.
The two new strict tests reverse only the tuple wiring and require the entire
wrapper to equal `691966ae`, and verify the witness's literal old expression.
Ruff and diff checks pass. Both actual runs passed on their first attempt;
no failed result was discarded and no production golden or tolerance changed.

## Reproduction and evidence

Evidence: `hdl/library/starlink_pss_acquisition/evidence/held-phase-input-v1/`;
its manifest covers frozen RTL/bench/scripts/vectors, raw simulation receipts,
Vivado logs, source scopes and unit logs. The scopes record pre-commit HEAD;
all seven frozen design files and the bench byte-match the tested source pin.
Wrapper SHA256: `feb75c83c2dbe84b3b910b7b1f08a3416133353ac2032579c837cd45ed9f1b48`.

Complete original runs are `/tmp/starlink-completed-input.5EaJuD/held-phase-actual-v1`
and `held-phase-default-v1`; unit log is `held-phase-regression-v2.log`.
Run the pinned `simulate_fft_bank_owned_slice.tcl` with a new output directory,
the immutable `input-cursor-paired-v1/frozen_sources` vector directory, `175`,
and optional `registered-scheduling`. Original process sessions 51485/50136
both exited zero, at 02:52:19/02:51:03 UTC respectively.

No synthesis, route, clock/constraint change, receiver build, deployment or
radio measurement was performed for this source. Existing CDC, external OOC
interface and physical eligibility limitations remain.

## Separate proposed comparator checkpoint

Next, default-off `BALANCED_IDENTITY_EQ` may use the existing mailbox pattern:
24 kept equality leaves (23 three-bit leaves and final bit69), four kept
six-way groups, then a final four-way AND. Opt in only for registered mode.
This retains all 70 identity bits, the original ordinal/TLAST checks, and
same-edge fault/certification/reason logic; no register, latency, hash or
phase exemption is proposed. Three logical LUT layers is an intended mapping,
not measured timing or area. Test against frozen old/default guards for every
single-bit corruption, first/interior/final slots, ready/stalls, duplicate,
gap/reset and simultaneous final input/output, with an omitted-bit69 mutant
required to fail. Implement/test/pin separately before any physical trial.
