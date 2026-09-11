# Private descriptor capture — DO NOT MERGE

Baseline FW `d29d076b3`, HDL `8c8568646`: staged writer validation passed actual
FFT and 366 regression tests but routed at -3.251 ns. The critical fault-qualified
completion signal drove descriptor payload enables with fanout 181.

## Implemented contract

The 178-bit descriptor bundle (tag, payload, expected descriptor and lookup-good
flag) now loads on `inverse_descriptor_live && !output_descriptor_locked`.
This depends only on registered local ownership. Before accepted completion,
invalid private lookup values may load, but grant no publication authority.

Actual `output_complete_accept` still uses the original qualified guard/bank/
controller handshake. On that edge, the bundle captures exactly the previous
qualified-capture values, sets the lock and pending flag, and clears public
descriptor-valid. The next edge compares the frozen values. The lock remains
through pending validation, publication and actual reader completion, reopening
only on the actual descriptor release or coordinated reset. No public-valid,
fault veto, bank request or reader ACK check is removed. A fault-edge private
load without accepted completion cannot become pending, valid or published.

The global current-fault tree no longer drives wide payload enables. Only small
control/receipt registers use accepted completion. This is an isolated FFT/
buffer implementation; it does not alter the primary production HDL gitlink.

## Executed verification

- Actual generated-FFT simulation passes in **108.78 seconds**. All **64,512
  numerical records** independently match the pinned reference; the numerical
  CSV is byte-identical to replay V1/V2. Six healthy contexts retain service
  intervals 3659/3659/4927/11727/3659/3659. The 5215-cycle bound still applies to
  all except the deliberately 9000-clock-stalled reader context.
- The entire earlier reset/fault/admission/completion/replay/writer campaign
  passes. A clock-by-clock healthy-context monitor checks **32,616 loads**,
  **74,846 holds** and **18 accepted captures**. Actual bank authorization is
  still checked against its current-fault predicate across the campaign.
- Three new actual cases: invalid/X lookup churn before completion followed by
  512 correct reads and one release; invalid/X lookup churn from pending
  validation through real reader completion, again 512 reads/one release; a
  coincident vendor fault at poised completion that allows private loading but
  no receipt/lock/publication/reads/release. Total handover receipts are 98
  admissions and 73 completions, including aborted jobs.
- A separate Icarus test executes the actual writer always-block against the
  pinned previous qualified-capture block for 80 epochs, including missing/
  unknown lookup evidence, descriptor mismatches, reset and release. All public
  control outputs match each cycle and accepted/locked payloads match. Private
  load/freeze is checked independently. Five mutations (missing lock, early
  unlock, qualified-only payload load, ignored lookup-good and skipped compare)
  fail. This is writer-block verification, not a substitute for actual FFT/CDC.
- The first isolated test run failed because its wrapper omitted a simulation
  timescale, rounding its post-edge observation delay to zero. The retained V2
  test harness specifies 1 ns / 1 ps, with no RTL change: **6 tests pass**.
  The failed harness logs are retained, not claimed as RTL failures or passes.
- **382 combined regression tests pass in 49.09 seconds**, including ten capture
  evidence-parser controls. These reject missing cases, weak cycle coverage,
  wrong acceptance counts, missing release, veto leakage and missing freeze
  assertions. Initial source/lint preflight passes two tests.

## Measured route: improvement, still FAIL

Source-matched synthesis completes in **103.43 seconds**, route in **57.70
seconds**. The independent audit verifies unchanged sources/checkpoints and
compares global summary, clock-pair reports, utilization and route status.

| Version | WNS | TNS | Failing setup endpoints |
|---|---:|---:|---:|
| Replay-only V1 | -2.265 ns | -1021.803 ns | 936 |
| Staged writer V2 | -3.251 ns | -1733.553 ns | 1364 |
| Private capture | **-1.969 ns** | **-813.676 ns** | **914** |

Private capture improves all three metrics versus both replay references, but
914 / 13803 endpoints still fail setup. Hold +0.058 ns and pulse +1.830 ns pass.
8403 nets fully route, zero errors. Resources: 2790 LUT / 5667 FF / 21 DSP /
15 RAMB18, zero RAMB36. Device, actual FFT configuration, diagnostic 100/175 MHz
clocks and route recipe are unchanged; no timing waiver was introduced.

The worst path is still publication phase → metadata/fault qualification →
completion acceptance, now ending at the **single pending-bit D input**, not
the wide payload enables: 12 levels, 7.631 ns data delay, 5.687 ns routing.
The next reported path is held phase → inverse guard's awaiting-ACK bit,
-1.943 ns. Payload fanout removal helped, but did not eliminate the long
completion/guard control dependency. Five critical CDC findings, 208 warnings
and 114/124 unconstrained I/O remain. Neither subsystem nor board timing closes.

## Next implementation gate

Stage producer-final validation/ownership transfer itself, rather than adding
another register after a still-global acceptance predicate. Inspect the guard
completion and awaiting-ACK paths together. A held final word and its descriptor
must stay owned while validation is pending; an accepted receipt must be bound
to that exact job and cancelled on fault/reset. Retain independent immediate
publication vetoes and actual reader ACK before reuse. Prove added latency,
fault-edge cancellation and no double close in the actual FFT test before
another route. Do not lower the diagnostic clock or waive these same-domain
paths merely to obtain a passing report.

Native **60 MS/s fine search** and independent **2.5 MS/s CI16 IIO inspection**
remain required. Full receiver routing/CDC/reset/board constraints, sustained
capture and actual 60 MS/s RX calibration remain prerequisites for `.18`
reversible canary, then `.17` PPU Ethernet deployment with pinned rollback.
Final verification remains a 300-second scan with 120 ms valid dwells and
blind host GLRT comparison. No radio, PPU or main branch is changed here.

## Source and artifact identity

Recovery root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Folders: `staged-capture-prepared-v1`, `staged-capture-actual-v1`,
`staged-capture-synth-v1`, `staged-capture-route-v1`. All runs are terminal.
The prepared inventory contains 34 files and includes the exact test bench,
runner, generated-FFT recipe, runtime RTL and vectors. The route also preserves
its orchestration source. Before/after source checks pass.

Inventory: `b873108f88659eb8c17d206a5415718404146823d69119f56be446d6ef7c676a`.
CSV: `d3072823cfbd0fbdfa2d885215ca7696582e415969d6a679523a939af52d62eb`.
Synthesis DCP: `19465164a70afe872316cd74ccdae505184299527d60a582d75629440babe50e`.
Routed DCP: `8dd7f2735482e3c6a0158693bf24340130770a51362182690bba43ffdc8e5d5b`.
Qualified-capture reference RTL:
`a7586aa38c2548be4797671fa7c40cac784e0d331745f05ca3fe452a1d036b21`.
