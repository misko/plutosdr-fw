# Inverse actual-core preparation: independent offline review

2026-09-10, after 15:49 UTC. **Preparation only; no new vendor execution or
deployment approval.** The failed P1 route remains failed. This is a separate
inverse-output candidate, not a union with the ROM/product experiments.

## Reviewed source and independent repeat

Candidate FW `50a3030a364de12c16fa2a03e1269fd7838c9f95`, HDL
`b26f56dd32106c8e91290d075255ac4a6b9ff72d`, on the isolated bank-arithmetic
DO-NOT-MERGE branch. Runtime RTL remains the previously tested inverse top
`2f988a16…`, issuer `8ad9c2e7…`, CDC bank `ea27c4e2…`.

Parent read the complete additive preparation helper, timing/protocol verifier,
monitor and policy tests, and checked the actual CDC reader/ACK and issuer
logic. The protocol fixture independently enumerates clock edges rather than
calling the verifier's request/read/ACK timing functions. This is useful
cross-checking, not an executed candidate trajectory.

Original parent process **79324 exited 0: 65 passed in 3.88 seconds**. Four
source hashes were identical before and after:

| File | SHA-256 |
| --- | --- |
| inverse_sealed_actual.py | c3c1c764a20061ce2026cbea653464d94752019e91acb8a359a414a5f591e9ab |
| inverse_sealed_actual_timing.py | d28fcac0ef83938e0e096f2426d02f18a7eb9374941df16a5629c72876433f2e |
| test_inverse_sealed_actual_policy.py | 05bcd90c6212682cc1a6c6fa7934ef891028d5db690b7cdeab77254572eadccc |
| starlink_pss_inverse_sealed_actual_checks.svh | 0c31976ad223f774fa991fd843dea84c6a20f243279d12501ad37905aaa969e4 |

Evidence directory:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/inverse-actual-policy-parent.ilD8tUIT`.
Log SHA `b67dc696232a68539f15ade79e0054184929fc93944ef2ae24cd94ddff96ea65`;
JUnit SHA `518ae109cab50e5f9d9c5b90a7e43e2aa0cc038f25704000303f81df78358616`.
The complete parent directory is retained in
`20260910-inverse-actual-policy-parent.tgz`, 10,670,612 bytes, SHA
`20c741d5045dfa5a4cfa40ae859a3f1ccbd2141568f235373071127a37503130`.
`tar -d` against the original directory exited 0.

Reproduction: from the bank-arithmetic tree, run the repository PPU Python
with `-B -m pytest tests/starlink_oracle/test_inverse_sealed_actual_policy.py
-q --tb=short`, unique `--basetemp` and `--junitxml`, removing child
`LD_LIBRARY_PATH`, `PYTHONHOME` and `PYTHONPATH`.

## What the preparation establishes

- Immutable original 49-input actual-core history and all original numerical
  vectors/checks are retained. The ten explicit whole-bench adaptations have
  a strict inverse; overloaded free-capacity READY is not mistaken for owned
  reservation or actual reader ACK.
- The generated profile is explicitly R/B/O/L/E=1 at 175 MHz, with E default
  off. Twenty-one compiled modules are enumerated. Icarus's vendor-absent
  elaboration artifact is **never executed** and is not an FFT model.
- Historical 76-job core phases and every F/P-fast, I-slow event timestamp are
  checked. New inverse publication is predeclared at admission+1813; canonical
  pair ceiling stays 5215 clocks, nominal planning ceiling 4557. Periodic
  backpressure does not inherit a blanket +8 historical-cycle allowance.
- Synthetic protocol tests cover all 38 tagged lifetimes and 19,456 exact
  private words with full metadata, including qualification, certificate,
  seal, publication, real reader ACK, release and reuse. Missing/changed events,
  data, metadata, lease and clock-domain mutations are rejected.
- Mocked launch failures and pre/post source mutations cannot publish success.
  Diagnostic tests cover plain/escaped roots, missing/duplicate objects and
  mixed roots. Inventory success is not recorded waveform-history proof.

The next gate is an exclusive frozen bundle and fully reviewed source-specific
execution owner, followed by one explicitly approved actual FFT evaluation.
Creating either preparation does not authorize execution, retries or routing.

## Parallel implementation decisions

Parent reviewed the complete product design at separate FW
`8358dc568ce682e4bb11eedc146ea9d4b8122389`. A bounded additive prototype is
authorized in that isolated tree: unchanged fast sealed-bank checker, a
descriptor-bound forward completion issuer, and a same-token checked-read
queue. The product descriptor explicitly pads its 70 historical bits with five
reserved zeros; this is not the inverse return's 75-bit encoding. Both write
and read validation must be staged. Three queue slots and +12 service clocks
are hypotheses to test, not accepted throughput or resource results. No
production connection, vendor execution or radio access is authorized by this
prototype scope.

Independent trace inspection also identified serialization while the old
inverse output drains: the next source is already available, but the single
result-guard context holds the FFT idle awaiting ACK. A separate retained
consumer context might overlap next-forward work with prior-result draining.
The reported roughly 3645-cycle conditional period versus 4549 is **not RTL
evidence**. A frozen scheduling ledger and fault/reset/phase ownership analysis
are being prepared. No clock constraint has been changed; any lower clock
requires demonstrated service capacity and a new physical proof.

Full receiver timing/CDC/IO, actual 60 MS/s calibration, causal native fine
search, independent 2.5 MS/s IIO, bounded eight-target scanning and radio
verification remain required. No radio or PPU state changed in this increment.
