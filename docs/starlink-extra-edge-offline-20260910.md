# Added final-fault stimulus: phase-aware offline correction

Offline tests pass; **no actual FFT rerun is authorized or performed**.
Tested source FW `48b88f6786334f5a62efaf1972ca430140e2b06c` /
HDL `12ce2854b35ee797f52cc32b6d3668ed65726d79`. All seven runtime modules
remain ae50b1889fd10cd762fb60266aecbb7c163e1d1a.

The only prepared behavioral change is an insertion in the added kind0/1
extra-epoch fault task. Kind0 injects immediately when clock is known low,
or waits for a falling edge when known high. Kind1 retains exactly three
held positive edges before waiting for the falling edge. X/Z phase fails
closed. Still-held-final, ordinal511, readiness and no-ownership checks
precede the original force/release. Every old posedge+1ps checker, current
veto, sticky reason, reset kind2/3, numerical/CSV gate and status observer
remains literal; a whole-file inverse and paired compile prove this scope.

Final original49596 exited0: **53 PASS/13.52s** (24 phase-edge,23 qualified
observer,six diagnostic preparation). Twelve synthetic-provider/real-guard
cases reach their declared low/high qualification phases; all kind1 cases
retain three held posedges. Fault lead is2.857143ns except the kind0
low-half offset at1.428572ns. This meets the frozen positive/half-period
bound for these deterministic providers, not arbitrary asynchronous input.
Ten mutants reject timing, hold-count, unknown-phase and ownership errors.
The guard is real, but core events and bank/ordinal models are synthetic;
this is not actual FFT/arithmetic/reset qualification.

The initial **7 PASS/5 FAIL** v1 is retained. Its unconditional next-negedge
wait allowed kind0 to cross a commit edge under the negedge provider; the
phase-aware correction fixes that demonstrated failure without narrowing
the admitted provider phase. V2 passed24/0.60s. V3 collected no tests due
to a mistyped filename (exit4), retained. Parent independently passed47
tests before the final additive provider-phase receipt fields.

Actual vendor source inspection establishes direct fft_clk/raw-valid wiring,
not its protected model's internal transition schedule. Existing WDB/CSV
does not recover that schedule or the exact same-slot process ordering.
The original8757 failure and29 invalid-status-only rows remain separately
preserved at FWabf481b4/HDLa4d0bc65, with both complete original CSV hashes
b0d60e80...; no raw217 or actual baseline pass is claimed.

New prepared directory:
`/tmp/starlink-completed-input.5EaJuD/extra-edge-prepared-v1`.
SHA256SUMS:
`8efa2657fd43d4c7d2804d90abf9aa169fb8d916136ee681d38d4b533885ad92`.
R0/D0/S0/extras1/FAST175/QUICK0; project absent. Frozen runner remains
`496a3ed4a2b55d494a22fd78f64b4a68580d923b398f5282e31145dc6a7951b0`.

Archive `hdl/library/starlink_pss_acquisition/evidence/extra-edge-offline-v1/`
contains the full freeze, exact pre-evaluation gates, failed v1 source/logs,
all final fixtures/results, provenance, and future invocation recipe.
Its README specifies the additional frozen qualified-observer receipt
audit required after the unchanged runner gates. Await parent review and
source-specific actual authorization; no RTL, physical or runtime promotion.
