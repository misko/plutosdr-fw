# Qualified-observer baseline: original goldens match, extra epoch fails

Original actual handle **8757 exited 1**; this is **not a qualification pass**.
The complete original numerical/fault sequence printed its original receipts,
and both full main CSVs match the historical baseline golden exactly. The
run then failed an unchanged join-input assertion in the second added extra
epoch. No retry, source change, combined mode or physical run was performed.

Measured source FW `6395b6573a6ef97398537bd573533241c1b97312` /
HDL `b4179711063b492c4c62e2f6ebd0a9643899dea1`, tested helper/source
FW3bb9fcc2 / HDL80e652c0, runtime ae50 unchanged. Prepared directory:
`/tmp/starlink-completed-input.5EaJuD/status-qualified-prepared-v1`.
R0/D0/S0/extras1/FAST175/QUICK0; Vivado 2022.2, two threads, unchanged runner.
Freeze SHA256SUMS remains
`36e44321ea694ee324f12613a54d0758219a62c7f9edd73b0106a45f6e70dd09`.
Before/after source inventories pass. Wall 418.64 s, CPU user/system
374.50/1.90 s, peak RSS 835568 KB; start receipt 07:38:48 UTC, Vivado exit
07:45:36 UTC. All 27 original warnings are retained without waiver.

## Observed status differences and original results

Exactly 29 invalid-status-only rows were logged, all in epoch 11, from
1198594347644 through 1198674347648 fs. Every row directly reports both
valid bits 0, candidate `e5` / `11100101`, reference `05` / `00000101`,
raw equality 0 and qualified equality 1. These raw values differ from the
prior strict diagnostic's `xx100101`; neither result is overwritten or
explained away. Driver origin remains unknown. The narrow observer scope
does not make either strict raw217 comparison a pass.

Both complete main CSVs have 325750 lines and SHA256
`b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d`.
Both partial extra CSVs have 11041 lines and SHA256
`e5c9187f73a51668f239671715f386b308d77e4e5d226e3194ff7d27e3893e78`.
Each pair compares byte-for-byte. The old runner stopped on the fatal
before its post-log hash/receipt gates; the hashes above were independently
checked afterward, not reported as a successful runner exit.

Both independently driven benches printed original receipts, including
44 healthy blocks, held-phase 12 active fault cases, and forward-retirement
651497 checks. Actual inverse-current and sticky-forward fault counters
remain 0. Registered-only preparing/bank boundary rows are 0 in this R0
run; no registered-mode coverage is inferred. No final extra-epoch,
EXACT_CONTROL_ACTUAL_PASS or qualified-observer receipt exists. Calling the
new frozen receipt validator independently rejects the log with
`ValueError: missing or malformed qualified-scope receipt` (exit 1).
No synthetic receipt was created from partial counters.

## Exact failure and read-only scheduling diagnosis

```text
Fatal: FORWARD_ACTUAL_JOIN_INPUT_MISMATCH
Time: 1924511525797 fs
Scope: exact_reference
File: frozen_sources/tb_starlink_pss_exact_control_reference.sv Line: 112
```

This unchanged checker samples at each FFT posedge plus 1 ps. The added
kind-1 extra stimulus calls `repeat(3) tick()`; `tick` also returns at that
posedge plus 1 ps, after which the task forces `event_last_missing` and
releases `product_bank_ready` in the same time slot. Thus added drives and
the old checker structurally share a sample time. It is a demonstrated
scheduling hazard, not proof of the precise simulator process/driver order
or a license to delay the checker.

Read-only WDB handle **52970 exited 0**, without replay. Saved candidate
top-level values confirm epoch 54, extra-kind 1, one completed extra fault,
zero completed extra stalls/resets, and fft_clk=1. The partial extra CSV has
three no-output held rows 336787/336788/336789. Candidate stalls still being
0 is consistent with the fatal occurring before its same-time increment;
reference counters and raw joiner/ready/event operands are unlogged, so
their exact process ordering cannot be recovered. The WDB hash matched
before and after this read-only inspection.

Partial candidate observations are 673579 checked samples, 673550 raw-equal
plus 29 invalid-only, 475908 active checks, 36 identity consumptions, one
active final fault, 74528 owned-stall edges and 37 reset-owned edges. These
are saved partial counters, not completed coverage or a terminal receipt.

The proposed next correction is limited to added stimulus: place kind-0/1
fault drives at the following negedge, with explicit still-held-final and
ownership checks before driving. For kind 1 the existing three held
posedges remain intact; kind 0 must still inject before the upcoming final
commit edge. All original checkers, current-veto and sticky checks, reset
kinds 2/3, CSV/numerical gates and runtime RTL must remain unchanged.
Offline-only preparation was separately authorized; no actual retry is.

Archive: `hdl/library/starlink_pss_acquisition/evidence/status-qualified-actual-v1/`.
It retains the full freeze, original logs/timing, all 29 invalid-only rows,
failed receipt audit, compressed complete/partial CSVs and WDB, before/after
inventories and read-only inspection logs. Original projects remain intact.
