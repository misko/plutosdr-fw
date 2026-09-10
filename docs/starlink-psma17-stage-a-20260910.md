# PSMA 1.7 Stage A — explicit 30-upper module contract

Implementation/offline interface verification only. This is **not actual bank
FFT admission, a paired native/PIL1 run, a receiver image, RF qualification,
physical timing/capacity, or a live 30 MS/s deadline result**.

Isolated tree: `/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired`;
branch `codex/starlink-rx-only-do-not-merge-high-rate-paired`.
Starting FW `d3371d154d24ae07665505ab42a5e5bc32a2dd46`, HDL
`b49553c16319f59ad8d7b44fd24c494f96eba142`.

## Edited interfaces

Only two runtime files change:

- `hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_acquisition.v`:
  append public `USE_BANK_OWNED_XFFT=0`; forward it to the existing internal
  IQ-to-map core and controller; forward pilot/realtime identity to control.
  Bank=1 requires exactly source30, pilot=1, shared=1, realtime=1, STOP=1.
  Existing non-bank STOP/realtime admission stays source15-only.
- `hdl/library/axi_starlink_pss_acquisition/axi_starlink_pss_phase_map_sync.v`:
  append bank/realtime/pilot parameters after **all historical parameters**;
  require the same exact contract and conditioned energy; add ABI/capability,
  counter exposure, and conditioned STOP-health selection described below.

The legacy inactive acquisition stub only gains a trailing default-zero bank
parameter. It still fatals if used as a STOP engine. Two additive benches use
explicitly different compositions; their names and PASS fields identify the
real versus substituted components. No port, memory map, STOP packet length,
coarse arithmetic, DDC arithmetic, map core, native tracker, kernel, golden,
build option, IP packager, receiver profile, BD, clock or driver is changed.
The unchanged packager does not yet supply the bank-owned dependency/clock
rollout: a module selector is not a deployable packaged receiver option.

| Mode | ABI | Capabilities | Source | DDC high words |
|---|---|---|---|---|
| Legacy default | 1.1 | 0x3f | 15 | zero |
| Legacy x2 | 1.2 | 0x7f | 30 | zero, including pilot-enabled legacy mode |
| Legacy x4 | 1.4 | 0xff | 60 | live high/low/high retry |
| Legacy shared | 1.5 | 0x13f | 15 | zero |
| Legacy shared STOP | 1.6 | 0x33f | 15 | zero |
| Explicit upper bank paired STOP | **1.7** | **0x7ff** | **30** | live high/low/high retry |

New mode retains config `0x000f0203`, delay7 raw samples, coefficient energy
1073744004, and DDC contract
`731426047077b036f9213db3574e4a556fd424b97a293843bd6ee085c2bf33af`.
Its conditioned kernel is `upper_edge_pss30_x2_ddc_kernel_q17.mem`.
No source60/lower-bank admission exists. Cap bit10 means bank ownership;
bit7 exposes the existing 64-bit observation counters. STOP remains PSS T
magic `0x50535354`, format/length `0x0001000c`, twelve words.

## Health, lifetime and counter read contract

Legacy STOP uses the unchanged `0x57ff` fatal mask. Only bank1/ABI1.7 selects
`0x77ff`, adding DDC saturation bit13, **plus independent nonzero cumulative
DDC discontinuity count**. Existing ingress, map, bridge and detector causes
remain. Bit11/denominator zero stays diagnostic; reserved bits15..31 are not
silently added to the specified mask. These are live observations, not one
atomic RF-health snapshot.

- A known DDC fault rejects a new ticket without claiming engine acceptance.
- During accepted partial work, the controller disables at the next control
  edge after an AXI-domain DDC fault is visible. The real map core aborts its
  unfinished prefix. Expected reason is **0x0b**: upstream1 + map-health2 +
  engine disable/abort8. No invented healthy empty-map terminal.
- A previously published complete map remains readable/releasable even if
  a later fault rejects admission or changes a retained STOP terminal to
  complete+has-map+failed-health. The late retained terminal reason is1;
  its generation/start/end and accepted/publication counts are unchanged.
  This does not retroactively reject an already accepted score.
- DDC accepted/emitted counts and discontinuity/saturation counts survive
  map disable, map flush and conditioner disable. Source-only reset also
  does **not** clear these AXI-domain counters. Only the existing common
  upstream `s_axi_aresetn` reset clears them; no software-reset fiction,
  per-visit subtraction, or new counter-clear command was introduced.
- The real FIFO marks its first reset-epoch beat as a gap. Enabling DDC at
  that point correctly counts a discontinuity. Clean startup consumes this
  beat **and a subsequent clean beat with map and pilot disabled**, then
  enables conditioning. The two beats are outside the frozen numerical
  cohort. Arrival/settling must be observed, not guessed from a host sleep.
- Each AXI read response remains stable under backpressure. A 64-bit read
  uses high/low/high and retries if high changes across carry. Accepted and
  emitted are individually coherent samples, **not an atomic counter pair**
  and not part of the PSMA map snapshot. The test's artificial carry is
  directly driven at public PSMA counter inputs, never forced real DDC state.

The same-domain witness checks admission closure as soon as the real DDC
counter is visible, and active-disable on the next control edge. It makes no
instantaneous remote-event claim. The separate startup bench exercises real
source CDC arrival, but not RF transport/control latency or asynchronous
fault closure under actual FFT traffic.

## Executed evidence and exact provenance

Final run: `build/psma17-stage-a-final-v4/pytest.log` and `pytest.xml`:
**340 PASS in 10.24 s**, exit0. It includes101 new Stage A cases and239 existing
cases (105 legacy interface/STOP/summary/build-policy, plus134 offline
cohort/DDC/pilot/native-coefficient cases). Host is gauss/x86_64, Intel Core
Ultra9 285K; these are host runtimes, not ARM/Zynq capacity.

- Four real AXI + 8-bin/4-frame map + unchanged integer-DDC lifecycle runs,
  both settings of each independent health-summary option. Synthetic scores
  are phase+1; every retained map word is checked as4*(phase+1). No FFT stub
  scores are described as C-model results. Real clipping waveform accepts16,
  emits1 at canonical index4 with I32767/Q0 and saturation1. Explicit-gap
  waveform accepts33, emits9 and has discontinuity1, saturation0.
- All32 flag bits, all32 source30 boolean combinations, bad rate/value/energy
  combinations, exact legacy/new public identity, parameter forwarding and
  historical positional parameter order. Negative mask/discontinuity/highword
  mutants must terminate failure, never yield the terminal PASS.
- Thirty additional literal-instance guard negatives cover X/Z for every
  required wrapper/controller field, including controller energy, plus bank
  selector -1/2. These use actual SV literals, not unreliable Icarus -P
  unknown overrides. Only new bank guards use case inequality and exact
  `bank === 1`; all literal historical guards remain unchanged outside it.
- Two counter carry/retry tests and four stalled register responses per
  lifecycle run; public-input mock counters explicitly labeled.
- Actual wrapper/CDC/DDC startup:66 source beats and18 canonical outputs
  checked across naive and primed epochs, including first-gap and index
  mapping, zero loss, source-only reset retention, common reset clearing.
  Zero-data wiring stimulus; inactive acquisition core, no real STOP engine.
- Existing legacy STOP traces compare the **live edited controller** with
  its historical implementation cycle-for-cycle. The historical whole-body
  optimization test first applies a strict inverse of only Stage A. Exact
  whole old/new SHA256, positional hunks and reconstructed old SHA are all
  required; mutation tests reject altered changed and unchanged regions.

`tests/starlink_oracle/psma17_stage_a_delta.json` freezes the complete runtime
delta, not just self-consistent ABI constants. Final runtime SHA256:

- wrapper: `2ce3a4943b43af7120500ba5064bedf0e7b1338517cc1d41b7ea30a33b0951d0`
- controller: `8911f045cb0811b9aabb008f8954f8c00f19bae7ba596996ec1e3c6b61f6bd4a`

The original cohort remains at `build/high-rate-offline-v5/cohort`, receipt
SHA256 `ba3046d56a6eb1cf2792070cf63f8d7ffb44958f0ef9f4999907b2b2a49bdb4d`.
Its **snapshot producer** independently rederived all51 goldens unchanged;
do not run the live modified producer against the old receipt or relax its
source pins. Replay from this tree:

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B build/high-rate-offline-v5/cohort/source_snapshot/tools/generate_starlink_high_rate_paired.py /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired/build/high-rate-offline-v5/cohort --verify
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest tests/starlink_oracle/test_psma17_contract.py tests/starlink_oracle/test_psma_boundary_stop.py tests/starlink_oracle/test_stop_health_integration.py tests/starlink_oracle/test_health_stop_summary.py tests/starlink_oracle/test_shared_xfft_integration.py tests/test_starlink_high_rate_paired.py tests/starlink_oracle/test_ddc.py tests/starlink_oracle/test_pilot_ddc.py tests/test_starlink_pss_tracker_coefficients.py -q
```

Retained attempts: v1 missing pytest parent directory (67 setup errors, no
RTL); v2 four bench-expectation failures at partial terminal reason0x0b,
63 PASS, fixed expected reason from unchanged engine contract; v3 67 PASS;
v4 174 PASS; v5 70 PASS; final-v1 nonexistent test filename/no tests;
final-v2 309 PASS; final-v3 310 PASS after trailing-parameter compatibility
check. Parent review then found unknown parameter literals could bypass the
new ordinary-comparison guards. Only those new guards were hardened; the
full final-v3 edited source/report receipt is retained alongside its passing
logs, and final-v4 passes340 cases including30 new literal negatives.
First snapshot verification rejected12 generated .pyc files after
golden rederivation; these files were moved into v4/generated-bytecode for
retention and verification passed with `python -B`. No golden/source changed.
The portable freeze receipt inventories the final source closure, original
cohort, traces/logs, and failures; no proprietary C-model binary is included.

## Exact deferred Linux/rollout proposal (not implemented)

Read-only reference: primary `linux/drivers/iio/adc/adi_starlink_pss_map.c`.

1. Lines89–94: introduce a distinct1.7 bank contract constant/cap0x7ff and
   raise accepted maximum only together with strict identity validation;
   preserve `MAP_STOP_VERSION=1.6` and twelve-word packet format.
2. `map_require_contract()` lines996–1073: add an explicit1.7 case using
   source30, config0x000f0203, delay7, Eh1073744004, all eight existing30 hash
   words and exact0x7ff. Never admit arbitrary “version>=1.6” or shared30.
3. `map_require_stop()` line452: retain the exact1.6/15 branch and add a
   separately validated1.7/30 branch, rechecking live identity/caps/geometry,
   config/delay/Eh/hash. Preserve shared mutex/ticket/selector serialization.
4. `map_take_health()` line328 (mode selection374): mode2 for validated1.4
   **or1.7**, preserving existing high/low/high retry and46-word receipt.
   Legacy1.2 must remain low32 even if its internal pilot counts are64bit.
5. `map_snapshot_fault_free()` line428: explicit1.7 mask0x77ff plus live
   nonzero DDC discontinuity veto; the latter is not in the old snapshot.
   Record before/after live DDC health around delivery/STOP observation so
   a later fault is not mistaken for a clean immutable RF-health snapshot.
   Preserve failure evidence and retained-map ownership; do not label failed
   retained data as healthy or silently discard it to obtain a clean result.
6. `map_attr_store()` fault_clear around917 only clears software state;
   it cannot clear cumulative1.7 hardware faults. Keep hardware recovery
   blocked until a reviewed common upstream reset/epoch coordination exists.
   PIL1/local/source resets are not substitutes. Driver startup must order
   both map and pilot disabled, source priming/drain, clean health check,
   then pilot/coarse enable; preserve original native capture sample indexes.

Before actual harness admission: separately review the common original-source
30-upper bank+STOP+native132/PIL1 composition, startup/continuation halo and
cleanup, then freeze its actual FFT/source witnesses. IP packager dependency
and clock constraints, public build/profile/BD selection/readback, driver
rollout, receiver capacity and physical timing remain later gates. No
dedicated-only composition is a substitute for this bank integration.
