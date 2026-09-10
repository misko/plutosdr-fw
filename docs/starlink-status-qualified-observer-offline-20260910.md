# Status-qualified observer: offline evidence, different observation scope

**73 tests passed in 14.02 s**, original handle 15112 exit 0: 23 new tests
plus the unchanged 50 actual-preparation/diagnostic tests. No vendor FFT,
physical implementation or runtime change was made for this offline study.
The earlier strict-raw diagnostic failure remains immutable at FWf98abdb3 /
HDL0c1a23a7; it is not reclassified as a pass.

Tested source: FW `3bb9fcc20b4ed8f8a9417e8002f69a092b995b4a` /
HDL `80e652c038121308b966797627ea120d0c91acdb`.
Three additive files implement preparation, its tests, and the standalone
real-guard bench. All seven runtime RTL remain identical to tested ae50;
all old preparers, original benches, diagnostic freeze and runner are
unchanged. No production receiver, radio or PPU work is included.

## Exact observation contract

The original 217-field `exact_public_equal` remains byte-for-byte intact as
the raw witness. The new decision is an additional 216-field case equality
(only `dut.core_status_data` omitted), AND a payload condition:

```verilog
both_invalid = (candidate_valid === 1'b0) && (reference_valid === 1'b0);
payload_equal = both_invalid || (candidate_status_data === reference_status_data);
qualified_equal = other_216_fields_equal && payload_equal;
```

Status-valid itself stays in the unconditional 216-field comparison. All
eight status bits therefore remain compared whenever either valid is 1,
X or Z. Only a complete status-payload difference while both valids are
exactly zero may pass the new observer. This deliberately differs from
the original raw217 scope; it does not explain the mixed-language/vendor
post-release driver behavior or weaken any valid-status check.

The observer retains its original 2 ps sampling, fatal and all named
diagnostics. A mismatch in any other field still fatals, including one
coincident with an invalid status-payload difference. Successful samples
are separately counted as raw-equal or invalid-status-only. Every latter
sample logs time, epoch, both valid bits, complete eight-bit hexadecimal
and four-state payloads, raw equality and qualified equality. Bookkeeping
asserts both valids are exactly zero, all other fields match, and the
payload actually differs before classifying a sample as invalid-only.

The labeled terminal receipt asserts positive sample count, equality with
the original observer check count, and `samples=raw_equal+invalid_only`;
it explicitly prints `original_raw_contract_pass=0`. The additional frozen
`verify_observation_receipt(log, exact_checks)` independently validates
that scope, count, every invalid-only row and both-zero valid values.
It must be called independently against the original exact-checks terminal
after any separately authorized actual run. It does not replace or modify
the old runner's numerical, full-CSV, extra-epoch or receipt gates.

## Executed offline proofs and negative witnesses

The strict whole-file inverse restores every original frozen file, including
all stimulus, reference bench, diagnostic task, extra epochs, runner and
settings. Full paired bench elaboration with a never-executed quiescent
vendor stub measures 2168 bits in the original raw tuple and 2160 bits in
the remaining tuple. This is elaboration evidence, not FFT numerics.

The standalone predicate matrix executes 1045 rows: 16 four-state valid
pairs times equal payload plus all eight single-bit/unknown/high-impedance
payload changes, and 215 other non-valid fields with high-bit 1/X/Z changes.
The valid field is independently swept as a scalar. A separate executable
observer fixture corrupts each of all 216 unconditional fields individually
while also presenting the literal `xx100101` versus `00000101` invalid
status difference. All 216 cases retain the original fatal at 9.002 ns and
print the exact named field. The healthy fixture logs four invalid-only
rows and two raw-equal samples, accounting for all six observations.

Six predicate mutants (low-five-bit comparison; omitted bits 5, 6 or 7;
permissive X/Z-valid classification; omitted other field), three accounting
mutants, and eight guard mutants are rejected. Guard mutants remove reserved
bit validation, exponent validation, final current-status veto, ready-high
ACK veto or simultaneous-output status-reason accounting. Mutated guards
exist only in isolated test outputs; no runtime RTL was edited.

The guard bench instantiates current real guard RTL beside an independent
whole dec20 frozen guard. It uses synthetic core events, not a vendor FFT.
For each mode 0 and 1, natural reset/admission/512-input/output sequences
construct idle, active pre-output, active nonfinal, held unqualified final,
held qualified final and awaiting-ACK states. Each state's active, ACK,
return-last, final-qualified, exponent-seen and exponent tuple is asserted
before fault injection. Complete public outputs, detailed current/sticky
reasons and the listed full internal guard-state tuple compare on both
clock edges. Original four-state behavior is preserved, not replaced by
an invented fail-closed interpretation of unknown TVALID.

Both modes report exactly:

```text
rows=72 phases=6 invalid_payload_rows=6 known_reserved_reasons=24
checks=106585 phase_witnesses=77 coincident_output_rows=3 ready_ack_rows=2
synthetic_core_not_fft=1
```

The 72-row matrix includes valid reserved bits 5/6/7, bad exponent, duplicate/
orphan status, valid X/Z payloads, X/Z valids and invalid-only raw differences.
Three separate output-coincident rows test matching status, bad exponent
(exact reasons 0x30), and reserved-bit error (0x10). Two ready-high awaited
ACK attempts inject status alone (0x10) and status plus orphan output
(0x30); ownership remains held on the fault edge and after sticky quarantine.
These are fixture interface/guard results, not actual bank/FFT coverage.

The source audit retains every actual status-data consumer unchanged:
valid-gated reserved/exponent checks, simultaneous-output exponent checks,
valid-gated capture, bit-4 sticky status reason, and all current final,
nonfinal, idle and ACK publication/admission vetoes. Every source body is
preserved by the inverse and runtime-byte comparisons.

## Freeze and retained earlier results

Prepared baseline only: `/tmp/starlink-completed-input.5EaJuD/status-qualified-prepared-v1`.
Settings R0/D0/S0/extras1/FAST175/QUICK0 are copied unchanged. No project
exists at completion of this offline freeze. SHA256SUMS hash:
`36e44321ea694ee324f12613a54d0758219a62c7f9edd73b0106a45f6e70dd09`.
Frozen helper:
`700963124589820a1580c641372666a720e21f825f0c2a090aa89f7f37f8272f`.
Runner remains:
`496a3ed4a2b55d494a22fd78f64b4a68580d923b398f5282e31145dc6a7951b0`.

Archive: `hdl/library/starlink_pss_acquisition/evidence/status-qualified-observer-offline-v1/`.
It contains the full prepared freeze, source/dependency copies, final logs
and generated test witnesses, including all 216 fatal observations and
guard mutants. Earlier incremental results are retained: 10 PASS (50112,
8.88 s), 16 PASS (85748,10.17 s), and 69 PASS (54057,11.76 s). The exact
69-pass source precedes the explicit coincident-output/ready-ACK expansion
and is retained separately; it is not credited with that later coverage.
Initial Ruff alias findings were corrected before the first test run;
final Ruff and diff checks pass. No test failure was suppressed or retried
as an actual run. Future actual execution requires source-specific parent
authorization and all original gates plus the additional receipt audit.
