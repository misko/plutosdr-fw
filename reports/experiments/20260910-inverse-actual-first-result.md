# Inverse actual run: original automation fails; diagnostic isolates parser boundary

**Original 21014 FAILED (exit 1). It is not reclassified as a passing run.**
Start 2026-09-10T15:53:57.717387Z; end 15:58:17.111528Z; 259.394 seconds.
Owner launch/after-integrity errors are null, all frozen sources unchanged.
Tcl run_status=1, after_status=0, and results.json remains absent. There is no
live vendor handle and no retry, synthesis, route or deployment approval.
The [preparation review](20260910-inverse-actual-preparation-review.md) records
the exact 64-file manifest, reviewed owner and single-execution authorization.

## Rejection and source-derived cause

The vendor simulation emitted the original guard/arithmetic terminal receipts
and the new inverse protocol receipt. The result collector then rejected
`healthy trace profile/fault` while parsing the complete trace. This combined
error text does not mean a fault occurred: parent surveyed every healthy-running
row and found **zero fault rows and one profile mismatch**.

That row is fast cycle146691: epoch1, profile1, running1, core_resetn0, inverse0,
result_busy0, output_bank_ready1, fault0, with no admission/config/input/output/
status/commit events. The preceding final result was ACKed/released and the
bank was reusable at146687. At146692 running becomes0.

The unchanged bench explains the ordering: `await_results` requires all32
outputs, WAIT_BANK and next_inverse0, then assigns profile=1 immediately.
`reset_epoch(0)` waits for the **next slow falling edge before asserting reset**.
One fast observation may therefore retain old epoch/running with the new
profile while no transform is active. It is not an in-flight profile switch,
nor evidence of a hardware fault. The older reference clock phase happened not
to exercise this parser assumption.

The correction must recognize a bounded, fully retired/quiescent transition,
not blanket-ignore profile mismatches or faults. Tests must reject a changed
profile with active input/output, ownership, missing terminal work, unknowns,
or no following reset. Only a separate offline correction/test cut is presently
authorized; the failed frozen inputs and original outcome stay immutable.

## Independent post-hoc diagnostic, not original automation PASS

Parent original23732 exited0 using separate read-only
`inverse-actual-audit-parent.WkCdfycM/diagnose_failed_run.py`. It verifies all64
before/after/live source hashes and the failed original outcome, independently
extracts actual admission/core-event jobs, records the mismatch rather than
discarding it, and invokes the unchanged frozen numerical/timing/protocol
checks on those jobs. This is explicitly a diagnostic, not a repaired collector
or future-run acceptance rule.

| Measured evidence | Result |
| --- | --- |
| Complete core job inventory | 76: 38 forward, 38 inverse |
| Exact ordered F/P/I words | 19,456 per stream |
| Output-derived exact sample scores | 16,986, oracle only; no scorer RTL claim |
| Nominal forward-admission intervals | 4554 or4555; max4555 <=4557 planning ceiling |
| Stalled intervals | 4827,4827,4835,4827,4828; all <=5215 canonical ceiling |
| Inverse qualification/publication | +1810/+1813 from actual admission |
| Full tagged lifetime evidence | 38 lifetimes,19,760 events,19,456 private takes |
| Reader ACK to tagged release | 1 fast clock |

Every F/P-fast and I-slow timestamp passes the phase-aware clock model. The
4835 stalled interval illustrates why the predeclared absolute bound was
retained instead of assuming every stalled historical delta is at most8 clocks.

Full raw CSV hashes:

- fft_bank_owned_trace.csv:
  `b824b9cffa9cd28c7572f5a906efe92e589fa2775d59fef88b5d345274f682b4`
- bank_arithmetic_events.csv:
  `777d36224edd47910271b8ac6e1b74171a9ef72e7b3ae8fae615b6bd568bb16f`
- inverse_sealed_protocol.csv:
  `7b96ace09355c6f11ba24e4a4717a4d561c9a00f3c5185ecbc7f5311f80fde87`

## Preserved evidence and remaining gate

Parent also verified the committed preparation archive at separate FW
`577c670acbdcc9c2758036f1f76b1c71ff87b708`: all4506 safe regular members and
every hash, including separately pinned inventory.json; 31,039,671 bytes,
SHA `38fad05b62eca8a189c8b8ff3a67675b708c3f7a0bc4ab26c69a8c375cd27936`.
The first parent archive audit27457 failed because its expected set omitted
that separately pinned inventory, not because the archive changed. The failed
audit source and corrected verification are retained; tool-only traceback is
not presented as an invented raw log.

Parent scripts and diagnostic results are archived in
`20260910-inverse-actual-parent-diagnostic.tgz`, 5441 bytes, SHA
`14295f12350a709a546482762f22fa0dc1857ae6ec82a873dac521d313ba5388`.
`tar -d` against the recovery directory exited0. The original success-only
parent verifier is retained but not executed or changed to accept this failure.
The inverse owner is preserving the full failed vendor run separately.

Next: test the precise parser-boundary correction and independently review the
resulting full post-hoc assessment. A new automated run needs a separately
reviewed frozen preparation. Even a future complete actual-core PASS will not
establish routed timing, full receiver capacity/CDC/IO, RF calibration, causal
60 MS/s native fine search, independent2.5 MS/s IIO or300-second scanning.
Those deployment gates remain, and no radio or PPU state changed.
