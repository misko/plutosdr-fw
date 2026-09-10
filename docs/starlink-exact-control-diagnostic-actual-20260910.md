# Exact-control baseline diagnostic: one raw status-payload mismatch

The one authorized diagnostic run reproduced the original baseline fatal,
now identifying exactly one of the 217 compared fields. It is **not a
qualification pass**. No RTL, stimulus, comparison, numerical/CSV gate,
sampling delay or receipt was changed during or after this run. No retry,
combined-mode diagnostic, physical run or runtime promotion was performed.

Measured pins: FW `c13a04e539f4a36cda27f3e1c79a8d5c88bd38c6` /
HDL `f43cdcf9ef817670ccb9bfbc53c890027ba5543b`; all seven runtime RTL files
remain byte-identical to `ae50b1889fd10cd762fb60266aecbb7c163e1d1a`.
Frozen directory: `/tmp/starlink-completed-input.5EaJuD/exact-control-diagnostic-actual-v1`.
Its input SHA256SUMS hash remains
`68511c5c9b7d0fb980ebdab498066fcf8d2ac41925e7ff9adfa0627f8249403f`.
Settings remain R0/D0/S0/extras1/FAST175/QUICK0. The frozen runner hash is
`496a3ed4a2b55d494a22fd78f64b4a68580d923b398f5282e31145dc6a7951b0`.

Original handle **69434 exited 1**. Vivado 2022.2 used two threads; the
journal begins 07:01:14 UTC and Vivado exits 07:04:40 UTC on September 10.
Wall time was 216.70 s, CPU user/system 215.26/1.86 s, maximum RSS 837136 KB.
The original first fatal remains at **1198594347644 fs**, epoch 11:

```text
EXACT_DIAGNOSTIC_FIELD name=dut.core_status_data candidate_width=8 reference_width=8 candidate_hex=X5 reference_hex=05 candidate_fourstate=xx100101 reference_fourstate=00000101
EXACT_DIAGNOSTIC_TERMINAL mismatches=1 original_equal=0 fresh_equal=0
Fatal: EXACT_ACTUAL_PUBLIC_REASON_OWNERSHIP_MISMATCH actual=0 old=1
```

Bits [7:6] are X **and bit 5 is 1** in the candidate; this is not merely
unknown zero padding. All other 216 named fields compare equal, including
status-valid, current/sticky reasons and ownership. Both benches report
injected_status=05, test_kind=4, fast_cycle=209754, epoch=11, both clocks=0,
and both resets=1. Original and freshly evaluated equalities both fail:
this is not the tested zero-named-mismatch/stale-boolean case.

## Exact edge and status qualification

The unchanged epoch-11 test suppresses forward status, forces an apparent
product-bank candidate, checks that inverse admission remains blocked,
then holds product-bank readiness low and injects the delayed status 05.
Both independently driven benches execute the same force and release:
`tick(); @(negedge fft_clk); release dut.core_status_data; release dut.core_status_valid;`.
The failure is the observer's unchanged 2 ps sample after that release.
The last CSV row is the preceding posedge, where forced status-valid is 1;
that CSV row alone cannot establish valid at the fatal's negedge.

Read-only WDB handle **90275 exited 0**, without launching a live simulation.
Raw candidate/reference status-valid and vendor-port aliases are unlogged
and return `<Blank>`. The saved top-level `forward_old_valid` and
`shadow_valid` are both 1 at the exact fatal time (both were 0 on the
preceding forced-status posedge). The following is therefore a
**source-backed inference, not a direct raw-valid waveform reading**:

1. `forward_old_valid` is the independent ce6a885e whole-guard output, wired
   to the candidate's complete raw status bus and valid, with COMPLETED=1.
2. Its nonfinal publication branch vetoes `status_error`; the candidate's
   [7:5]=xx1 makes the reserved-field `!=0` term definitely true. Its final
   branch vetoes `core_status_tvalid` directly, regardless of payload.
3. A known public-valid 1 in either branch consequently requires
   `core_status_valid=0`, excluding 1/X/Z. The unchanged 217-field comparison
   establishes equal candidate/reference valid, so both are 0 here.

This identifies an unqualified payload mismatch at this observation, not a
valid-status mismatch. It does not identify the post-release driver cause,
justify weakening valid-status checks, or turn the failed full-raw-field
contract into a pass. No later behavior is observed after the fatal.

## Driver and consumer audit

Each SV wrapper declares an eight-bit wire, normally driven only by
`shared_xfft.m_axis_status_tdata`; the generated VHDL wrapper maps that
eight-bit output directly from its FFT component. There is no SV payload
mask or alternate functional driver. The generated core uses C_HAS_BFP=1,
C_HAS_OVFLO=0, C_M_AXIS_STATUS_TDATA_WIDTH=8 and ties internal status-ready
to 1. Both benches force their respective SV wire from equal eight-bit
injected registers and release on the same clock edge. Source wiring does
not establish how XSim implements the mixed-language driver alias on
release. `report_drivers` refuses an exited simulation, and the underlying
2022.2 vendor HDL is protected. No decryption or simulator replay was tried.
Whether the observed value originates in the invalid vendor payload or
force/release handling remains unproven.

All actual payload consumers remain literal. `status_error` checks [7:5]
and low-five exponent consistency when status-valid is asserted; the full
and completed output checks compare a simultaneous valid status exponent
with the arriving output exponent. Status capture updates `status_seen`
and `status_exponent` only on a valid status during an active, unpoisoned
job. The status reason is bit 4 of `faults_now`, ORed into sticky reasons
on the same edge; full and completed nonfinal publication retain this
current veto. Final publication and idle admission/ACK fences reject any
new status-valid event, and the forward-only final/nonfinal expressions
retain the corresponding checks. Wrapper completion also excludes current
status-valid. No RTL consumer uses the raw payload unqualified; the new
whole-island observer does compare it on invalid cycles.

AMD's published PG109 v9.1 status definition specifies a five-bit BFP
exponent zero-extended to the eight-bit boundary, not ignored upper bits;
its status pinout qualifies status availability with TVALID. These are the
retrieved 2026-07-17 documentation pages, not a recovered 2022.2 internal
model specification. They do not explain this force/release observation.
[Status fields](https://docs.amd.com/r/en-US/pg109-xfft/TDATA-Fields),
[status pinout](https://docs.amd.com/r/en-US/pg109-xfft/Pinout?contentId=41y3_FjnC0vC3~xslLYPjg).

## Preserved evidence and limits

Both partial CSVs contain 209755 lines and are byte-identical to each other
and the original failed baseline partial CSV, SHA256
`dd695cd5afb7da1df04e2b6ec731e18f42dbe7c361b1c518f1a1d126e216ab3c`.
No original suite, extra-epoch or EXACT_CONTROL_ACTUAL_PASS terminal receipt
exists; no historical full-CSV gate was reached. Partial WDB counters are
419508 successful comparisons, 318945 active checks and 36 identity
consumptions, not completed coverage. The extra epochs were not reached.
All 27 warnings are retained: 16 VRFC10-8426, 8 VRFC10-3380, and one each
VRFC10-3532, IP_Flow19-4832 and Vivado12-13277. No warnings are waived.

Archive: `hdl/library/starlink_pss_acquisition/evidence/exact-control-diagnostic-actual-v1/`.
It retains full frozen inputs, original logs/timing, after-source checks,
compressed partial CSVs and WDB, generated VHDL port wiring, and the full
read-only inspection logs including failed command attempts. The raw WDB
hash after read-only inspection is
`b5b80714a01d82d15e79db9cba17dfd2b2cedc09c55e9297d89dd63c7221b916`.
Original projects and prior failed runs remain untouched.

Direct upstream-driver attribution would require both raw SV status-valid/
data and generated VHDL component-port aliases at force assertion/release,
plus live driver reporting. Those observations are unavailable here; no
identical blind diagnostic is proposed. Parent requested a separate,
read-only proposal to qualify ONLY the new observer's status-payload
comparison by status-valid, with all eight bits still exact whenever either
valid is not exactly zero. That would change the observer's invalid-cycle
scope, not explain the vendor driver. The original strict failure remains
evidence. No additional run, source edit or acceptance change is authorized.
