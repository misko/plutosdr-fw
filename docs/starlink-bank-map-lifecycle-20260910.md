# Actual-core bank-map lifecycle verification, 2026-09-10

Eight bounded lifecycle cases pass at a 175 MHz FFT clock, 100 MHz map/control
clock, 1.3 ns initial FFT phase and independent 15 MS/s source cadence. The real
bank-owned XFFT, unchanged score arithmetic, reduced 447-bin × 2-frame map and
synchronous PSMA control are instantiated together. All 7,560 visible scores
and 3,129 completed-map words matched the unchanged frozen numerical fixture.
No RTL defect was found and no existing RTL or arithmetic was changed.

This is additive offline verification, not production-map, paired pilot/native
fine, resource-capacity, routed-timing, RF, receiver or 120 ms dwell qualification.
Only 175 MHz was evaluated here; the runner also admits an explicit 200 MHz
comparison, which was not run for this lifecycle suite.

## Frozen expectations and scope

The existing [map-stop contract](starlink-map-stop-boundary-plan.md),
[bank IQ-to-score contract](starlink-bank-owned-iq-to-score-20260910.md) and
[bank-owned FFT contract](starlink-fft-bank-owned-study-20260910.md) were read
before defining the cases. Their distinctions are assertions, not post-hoc
interpretations of a winning output:

- A fault already visible to the map consumer before its final FILL acceptance
  aborts that partial tile exactly once; a prior complete map remains readable.
- A final score accepted while healthy makes the tile complete. DRAIN and
  pending-publication must finish the last RAM write and retain that map, even
  if terminal health subsequently fails. Do not retroactively undo healthy work.
- Every visible score, including a provisional prefix in a failed epoch, must
  match frozen value, index, phase and denominator status. Fault cases do not
  waive numerical comparisons. No FFT output, score or arithmetic result is
  forced. Four cases model already-visible slow-domain service faults; a separate
  case injects a vendor event into an actually live fast-domain core.
- A healthy stop requires exact map data, healthy counters, stable ticket/map
  coordinates, a clean read/release and local coarse shutdown without flush.
  CONTROL re-enable must allow ticket 2 without external reset after ticket 1.
- Independent `fft_resetn` must not erase the still-live slow PSMA epoch's
  sticky health/evidence. Explicit hardware-epoch reset must permit exact replay.
- Raw fast-domain event time and the first slow consumer edge seeing a fault
  are separate. Remote boundary outcomes are selected by actual healthy final
  acceptance, never by imposing impossible retroactive fault visibility.

The fixture has 1,406 CI16 samples and 1,341 score bytes: three overlapping
512-point transforms, stride 447. Every source epoch replays the same bounded
fixture at a distinct monotonically increasing synthetic index origin; no
fourth block or unknown zero tail is used. All seven original input/intermediate
fixture files are retained, but this bench independently compares visible scores
and completed map sums, not every retained transform intermediate.

## Actual 175 MHz results

| Case | Exact visible scores | Exact map words read | Required result observed |
| --- | ---: | ---: | --- |
| Healthy stop/re-enable, two visits | 1,788 | 894 | Tickets 1 then 2, generations 1 then 2; no external reset between visits; flags `0x16`; no flush or health error |
| Prior map retained, later partial tile faults | 1,002 | 447 | Prior generation 1 retained/read/released after fault; second partial tile aborted once; failed partial receipt with history `0x1a` |
| Independent FFT reset | 300 | 0 | Slow reset stays deasserted; partial abort once; flags `0x0a`; sticky slow health `0x00000001` survives fast reset release |
| Hardware-epoch reset/replay after fault | 894 | 447 | Clean first ticket/generation and exact healthy map after explicit epoch reset |
| Slow-visible fault before last FILL acceptance | 894 | 0 | Last public score was exact, but last map acceptance was prevented; no map publication; flags `0x0a` |
| Slow-visible fault in DRAIN | 894 | 447 | Already complete map published/read/released; failed complete receipt `0x1e` |
| Slow-visible fault with publication pending | 894 | 447 | Final RAM word committed and complete map retained/read/released; flags `0x1e` |
| Raw live vendor event near final score | 894 | 447 | Healthy final acceptance preceded consumer-visible fault; complete map retained; failed complete receipt `0x1e` |
| Total | 7,560 | 3,129 | Eight case identities, eight hardware-reset epochs, terminal PASS |

The retained-map case asserts that a complete ready map and a later FILL tile
coexist before injection. Full map reading and release occur after the failed
terminal receipt; the test does not claim to sweep simultaneous AXI read/release
and fault edge races. Healthy re-enable replays source IQ under a new index
origin, not a continuous pilot/fine visit or RF retune.

The final raw-event witness is:

```text
raw fast-domain vendor event       1329241.366 ns
healthy final map-score acceptance 1329245.000 ns
first slow consumer fault edge     1329275.000 ns
first monitor observation of ready 1329275.000 ns
```

Thus this single sampled phase has 33.634 ns between injection and slow consumer
visibility, with the final acceptance 3.634 ns after the remote event. `publish_ns`
in the log is the first posedge monitor observation of ready, not a claim that
the ready register's preceding nonblocking assignment happened on that edge.
This is a concrete CDC-order witness, not an exhaustive phase/latency bound or
physical CDC signoff. The expected failed receipt does not invalidate a completed
map or make provisional valid prefixes arbitrary.

## Implementation, provenance and reproducibility

Independent worktree only:
`/tmp/starlink-coarse-alternatives.Y3JzOI/bank-map-lifecycle`, branch
`codex/starlink-rx-only-do-not-merge-bank-map-lifecycle`.
Starting FW `249edd4b535bea7e6537e8c102f49ad1b5f8b07f`,
HDL `69f84febf0a2788f23e04f2f6b3cfec5b33b9c9a`.
Additive HDL bench/runner commit:
`1800c665a29ebcc7aae3218ba7189001674d9687`.

Files:

- `hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_bank_map_lifecycle.sv`
- `hdl/library/starlink_pss_acquisition/simulate_bank_map_lifecycle.tcl`
- `tests/test_starlink_bank_map_lifecycle_policy.py`

Successful evidence directory, here abbreviated `E`:
`hdl/library/starlink_pss_acquisition/build/bank-map-lifecycle-175-v2`.
`E/frozen_sources` contains 43 files: every local RTL/helper/bench/kernel input
and all seven numerical fixtures. `E/scope.txt` records all their SHA-256 hashes,
the starting commit, dirty additive sources, clocks and host. These tested
bench/runner bytes are the bytes in the additive HDL commit. The unchanged
Vivado 2022.2 real XFFT helper generates and checks the vendor IP configuration;
`E/generated_ip.txt` records the generated wrapper hash. The generated project
and simulator products remain under `E/project`.

Selected SHA-256 values:

```text
fixture samples  4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723
fixture scores  c22f751a2a82244268dd9ea4989c4ff3b5364c172526e80886c5da3d1959e45d
fixture kernel  694d0d9b8dd55368bcaaedec37a7cda3a837d491d592ede60eec57a9821fc99a
new bench       7650408dbe628041007539258c30474690714aa7982d5b32b0df19978943418b
new runner      2ce831f2d3283bb596e39d18bcecaa43ff948aa03d06948787371a24f6f35d51
scope.txt       7695104751803ded2157034f7c736cd6117bfe4f070bbad70d22da95d2823b5b
generated IP    a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68
simulate.log    e786260867a22b16a6e93e74b44b9274053f6f4a2a56f687ecb13c1673a8e1c5
```

Run from `hdl/library/starlink_pss_acquisition`, choosing a new output path:

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vitis_HLS/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source simulate_bank_map_lifecycle.tcl \
  -tclargs NEW_OUTPUT /tmp/starlink-bank-route.I50MDJ/main-phase-map-175-v1/frozen_sources
```

The runner refuses existing output paths, wrong tool version, missing inputs,
wrong vector row counts/hex widths and clocks other than 175/200. It requires
exactly one terminal PASS, all eight distinct case identities and no FAIL/FAULT
or simulator fatal/error diagnostic. Every assertion uses a message-bearing
`$fatal(1, ...)` to avoid the previously observed simulator continuation trap.

Host: Linux `gauss`, x86_64, kernel `7.0.0-30-generic`, Vivado 2022.2. Successful
simulation covered 1.377570 ms of simulation time; simulator kernel reported
73.070 s CPU, and `launch_simulation` reported about 87 s elapsed. These are host
offline simulation measurements, not Zynq execution or real-time capacity.

The first run, `bank-map-lifecycle-175-v1`, is retained as incomplete evidence.
It passed healthy re-enable but waited for a live vendor core after 1,000 scores;
the bounded fixture did not supply a subsequent live job there. Only that
simulator was terminated, and the runner correctly rejected its missing terminal
PASS. V2 replaces that unsuitable stimulus with explicitly slow-visible fault
injection at the required ready-map/partial-FILL state. The separately asserted
live-core raw-event case is retained. This was a test-stimulus correction, not
an RTL fix or relaxation of the map/health/numerical expectations.
The complete rejected Vivado transcript is frozen as
`bank-map-lifecycle-175-v1/rejected-run-vivado.log`, and the complete successful
transcript as `E/verified-run-vivado.log`. The adjacent
`starlink-bank-map-lifecycle-20260910.json` records source, report, test and
both-run artifact hash receipts, including the rejected stimulus's frozen inputs.

## Tests and remaining boundaries

The new executable runner-policy suite has 67 passing tests. Together with
existing bank phase-map, realtime PSMA stop and paired realtime PSMA stop policy
tests: 218 pass; JUnit output is `E/policy-tests.xml`. Ruff and both worktree
`git diff --check` checks pass. Policy tests exercise input admission, unchanged
source freezing, bounded vector geometry, case identity inventory, duplicate or
missing terminal/case rejection, wrong clock, explicit FAIL and simulator fatal.
They are not substitutes for the actual XFFT run above.

Still unqualified: arbitrary clock phase sweeps, simultaneous bridge operations
at publication/fault edges, both ready banks retained through faults, combined
independent resets during every fast-core ownership state, ticket/generation
wrap in this actual-core composition, long source gaps, continuous retunes,
production 20,000 × 64 maps, and native fine/pilot delivery across stop/re-enable.
Sticky-health rejection of a new stop without hardware-epoch reset is a contract
requirement; this suite confirms sticky preservation and successful explicit
reset/replay, not a full driver recovery protocol. A failed terminal can expose
retained completed/provisional evidence, but is never a qualified healthy visit.

No synthesis, routing, radio operation, PPU edit, remote write, deployment,
production selector switch, primary worktree edit or full receiver build occurred.
