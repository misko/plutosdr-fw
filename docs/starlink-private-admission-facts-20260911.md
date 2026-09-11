# Private admission facts — DO NOT MERGE

Branch (FW/HDL): `codex/starlink-rx-only-do-not-merge-private-admission-facts`.
Parent FW `14af35ec6f87b274f677af31c37066eb04db2088`, HDL
`cbb36f3b679b4f0bb22f280429c934a7db0d3236`.

## Result

The private admission snapshot no longer has the parent's wide reset/request
clear path. Actual FFT behavior and service timing are unchanged. **The complete
subsystem still fails setup timing and this candidate is not promoted.** Worst
slack and failing endpoint count regress despite the local structural success.
No radio, PPU/main, primary production HDL, clock, TX or timing-constraint change.

## Implementation

`starlink_pss_admission_certificate` adds opt-in `PRIVATE_FACT_CAPTURE=0`.
Default mode retains the original payload clear/capture behavior. With the
parameter enabled, snapshot payload captures only while `!snapshot_valid &&
!consumed`, including invalid intervals, and holds while owned. The separate
validity, consumption and permit equations are unchanged. Invalid payload has
no reset-value contract; it cannot grant permission without the original
validity and current request/quarantine/reset checks.

Only the 36-fact admission instance opts in. The completion certificate remains
in default mode. There is no extra register or cycle in the RTL. Two runtime
files change out of the 22 compiled modules. Exact inverse tests prove the
parameter/payload rewrite and top opt-in against the pinned parent; all other
runtime files remain exact. Historical inverses normalize this separately
tested change rather than dropping their old comparisons.

The actual bench adds a same-width default-mode reference. Every observed
permit/validity/consumption value must match; every valid payload must match.
The old compressed-fact witness retains control equality and compares payload
when valid. Invalid differences are explicitly counted, not called corruption.
All existing injection/recovery cases and deadlines remain.

## Functional evidence

- 14 new component/source tests pass. Eight width/mode combinations (1, 24,
  36, 42 bits; default/private) each perform 12224 checks, including all
  four-state control tuples, four-state data, captures, stalls, consume,
  quarantine and reset sequences. Four unsafe mutations are rejected.
- 76 focused tests pass. The final full regression is **745 pass in 87.77 s**.
  The first full run had eight test-maintenance failures: seven historical
  source/mutant checks plus their parametrization accounted for changed source
  structure, not failing actual RTL behavior. They were corrected and the
  complete suite rerun. Earlier import/indentation/preflight diagnostics are
  retained. No RTL or frozen bench changes occurred during actual runs.
- Nine new evidence tests plus seven overlapping archive tests pass in 1.57 s.
  Missing/duplicate/short/incorrect witness records block routing. Distinct
  regression plus new-evidence total: **754** (not counting repeated subsets).
- Main actual FFT passes in **209.09 s**, auxiliary in **141.15 s**. All 64512
  indexed numerical records and the complete CSV are byte-identical to the
  completion-receipt parent. Service stays **3663/3663/4929/11729/3663/3663**
  clocks. The intentional stalled case is not a continuous throughput claim.
- Main private-fact witness: 500645 checks, 266 valid/owned observations,
  500193 invalid payload differences. Auxiliary: 334066 checks, 125 owned,
  333816 invalid differences. Permit and owned data are exact in both.
- Actual reset/fault, completion-receipt, ACK, forward/product, publication
  and fresh-recovery campaigns all remain passing. Synthesis takes 99.42 s.

## Physical evidence — local improvement, no subsystem closure

Vivado 2022.2, xc7z010clg400-1, unchanged 100/175 MHz OOC recipe, two threads.
Route completes in 55.72 s. Read-only inspection identifies 35 surviving private
snapshot registers, with CE startpoints restricted to local validity/consumed
registers and no nonconstant register startpoints on their reset pins.

The original `slow_reset_fast_reg[1]/C` source has no path to the corresponding
snapshot bit-zero reset pin (parent −1.560 ns). Its new data-pin path is
**+0.271 ns**. Paths to validity and consumed remain **−0.288 / −0.293 ns**.
The first inspection rejected the old register name; the generated block adds
`private_facts.` to the payload cell names. The original script/log is retained;
only the read-only query was corrected, not the checkpoint or constraints.

| Whole subsystem | Completion-receipt parent | Private facts |
|---|---:|---:|
| WNS | −1.560 ns | −1.661 ns |
| TNS | −479.076 ns | −474.560 ns |
| Failing setup endpoints | 837 | 944 |
| LUTs / registers | 2760 / 5790 | 2819 / 5804 |

Worst same-domain path now starts in the actual FFT status FIFO
`shared_xfft/U0/i_synth/axi_wrapper/gen_status_channel.status_fifo/gen_real_time.data_out_reg[0]/C`
and ends at `output_bank/request_toggle_reg/D`. Nine logic levels, 7.372 ns
data delay, including 5.800 ns routing (78.7%). It crosses status-dependent
fault logic into current publication authorization. It cannot simply be delayed
or waived without proving cancellation/ownership safety.

8473 nets route with zero errors. Hold +0.058 ns and pulse +1.830 ns pass.
21 DSPs / 15 RAMB18s remain. 114 inputs / 124 outputs are unconstrained in OOC.
Reset inspection retains exclusive first-to-second synchronizer fanout and
registered purge signaling. Nine CDC-3 info / 208 CDC-15 bundled-data warnings
remain, with no CDC-1 or CDC-10 critical findings. No board-level CDC signoff.

## Decision and path forward

Keep the candidate as evidence, not a promoted improvement. These local edits
have repeatedly moved the worst path through the shared current-fault network;
another isolated register tweak is not sufficient evidence of a deployment path.
The next bounded task is to map the FFT-status-to-publication predicate by
ownership/phase and identify which checks are truly current publication vetoes
versus private next-job bookkeeping. Any partition must preserve current unsafe
publication rejection; stale status or merely successful private completion
cannot authorize the bank. Prove the partition against actual boundary cases,
then rerun the same integrated FFT and route before adding features.

Preserve native 60 MS/s fine search and independent 2.5 MS/s CI16 inspection.
Subsystem closure, full receiver board clocks/timing/CDC/reset, actual 60 MS/s
RX calibration and sustained IIO/Ethernet remain ahead of reversible `.18`
canary and `.17` PPU Ethernet-only deployment with pinned rollback. The
120 ms valid dwells, 300 s scan and blind host GLRT comparison remain required.
No receiver was flashed or touched; the full goal is not complete.

## Pins and retained evidence

Evidence root: `/dev/shm/starlink-private-admission.jU5bmytc`.
Prepared: `e589b35765220ac3784105df0c96f38f40a1e276a746c79767bc7c57600ff203`.
CSV: `7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d`.
Synth DCP: `2b8ebd592b280a61d40969183ea97157e599ffed2727102b087f3fbf3dcee4ae`.
Routed DCP: `456b3dbb87310f1c68a0188f4568d72552091b8b7e86b9ec81e52a90c7254d1e`.
`record_private_admission_evidence.py` rechecks source inverses, outcomes,
numerical equality, tests, route metrics and inspection pins before packaging.
The archive retains source/bench snapshots, tests including failed diagnostics,
actual CSV/logs, checkpoints and inspections. Duplicate regression CSV/DCPs
are omitted; identical generated vendor VHDL is kept once after equality checks.
No raw local artifacts are deleted.
