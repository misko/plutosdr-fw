# Frozen 30-upper healthy343 and late447 preparation

Offline preparation passed 652 tests in 31.57 seconds. No actual FFT was
executed by this preparation. Parent independently repeated 253 relevant
tests (162 new + 91 unchanged harness/budget), all passing in 18.91 seconds,
and verified both bundles and all 104 live source hashes.

This adds two context-specific cases over the accepted healthy447 source
closure. All runtime RTL, guards, original447 helpers and 51 numerical
goldens remain byte-identical. The completed actual447 proof is separately
committed at FW `94de11b912a9783eb8879b4b94b700ed83b18793`; its loader failure
and successful v2 run are preserved, not rerun or reclassified here.

## Frozen identities

Worktree: `/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired`.
HDL additive commit: `529dc8e8d33afc237c7b26f8969ec32fa97cdbdd`.
Original base FW `6a99d1d538889c79630758ac86c4493ea254640d`, HDL
`446a8617adbabcce5122705e528dc997ff06d263`.

Both cases share source signature
`b9d4d306fd9665133e36dc21e24125bce9ac7a6b3b34ed335b45fd5e2ba9ab09`.

| Bundle under build/ | Files excluding receipt | bundle.json SHA256 |
| --- | ---: | --- |
| high-rate-cases-healthy343-prelaunch-v1 | 515 | bbec5b49d80caf3ec50b6d595e33e7cf62d4ca18e665caa1573099e90ad99bd7 |
| high-rate-cases-late447-prelaunch-v1 | 518 | 9cfded42cd006d0524531dc36739461d86d8612c908e55810e81b4c08fa566ae |

Each contains the exact original447 bundle (SHA
`2d410bc8a7984425751a527725e8f43c8406596b23f610e904199d1524863da5`),
generated bench/includes, strict inverse receipts, and actual native-only
late-probe evidence. The 104-source closure is original95 plus exactly nine
additive files. The explicit local-import graph contains 12 Python modules;
its five inherited dependencies are high_rate_harness.py, native30_budget.py,
the original harness/budget tests, and prepare_starlink_high_rate_harness.py.
All are present and tied to the file inventory; package initializers are
also retained in original95. No import relies on another worktree.

## Case contracts fixed before actual evaluation

Healthy343 retains the positive native132 job: 260 original-raw captured
samples, 129 raw/121 qualified tuples, 26 packet words read twice, and
independent native result release while the map stays retained. Exactly
686 scores enter the 343x2 map. Residue is 239 into the second 447-score
FFT block, with at most 208 visible provisional tail scores; every visible
score/index/denominator remains exact. The second block can stop after
512 + 65 + 239 = 816 slow inverse outputs. This is a geometry-specific
minimum, not a weakened expectation for447 or permission to ignore tail.
Every actually visible FFT input/forward/product/inverse word and exponent
is compared to the original independent oracle. The original343 map
golden is used without regeneration. The final CASE_LEDGER explicitly
reconciles selected, residue, potential/visible tail and map-read counts.

Late447 preserves the coarse894/447-map and 512-pilot paths, but requires
one rejected/late command and zero native admitted/capture/compute/raw/
qualified/packet/result/IRQ work. Coefficients first complete legitimate
132-tap preparation with generation30000001 and energy1073746351;
config-ready is explicitly witnessed. No-work checks then remain active
through the entire source, including after the negative observation.
The expected rejection is not a detector miss or a healthy native result.

The late command keeps center17179870192/start17179870128. It triggers
at raw17179870160 (start+32); accepted handshake interval is
[17179870160,17179870240], signed lead [-113,-33], at most256 control
cycles. The predeclared command bound is 8 AXI transactions*24 +8 entry
edges +32 queue/CDC clocks =232; 80 raw beats cover256 clocks at30/100.
Public telemetry snapshot completes within512 clocks. Negative observation
starts at17179875609 (original source offset8000). Bounds were accepted
before the first probe and were not moved to match its result.

Actual native-only probe: handshake17179870177, signed lead-50, 58 clocks;
rejected=late=1, all forbidden native work/result/IRQ=0. It uses actual
native RTL and public AXI commands, no hierarchy forcing or FFT substitute.
It has no actual FFT, PSMA or PIL1, which remain pending integration tests.

## Shared source, support and lifetime

Both cases retain two disabled-DDC prime beats, original8205 raw samples,
1549 raw/768 canonical preroll, and the already justified4096 source-only
tail: exactly12303 offered/observed source beats. The original raw range
is [17179867609,17179875814), tail [17179875814,17179879910).
Native capture support is [17179870128,17179870388). Positive native
publication/readout budgets remain24000/28000 control cycles; fixed tail
was already justified by the native FSM and measured module-only probe.

The x2 conditioner is closed by the512-pilot auto-stop. Therefore actual
canonical/stage exposure is an independently checked enabled prefix, not
a claim that all4096 canonical samples or seven FFT jobs execute. All
original source samples still advance through the source/CDC ledger.
STOP closes only coarse work; positive native compute can outlive STOP.
Map retention/release and native result ownership remain independent.
The negative case retains the map through its explicit no-result
observation, not a fictional native release. Bank-only quiescence is
required after safe source end. Static known-center commands are not
causal coarse-to-native handoffs, RF timing accuracy, DMA/IIO, physical
175 MHz timing, production-map or scanner capacity qualification.

## Offline tests, rejected attempts and result policy

Full receipt: `build/high-rate-cases-regression-v1/{pytest.log,junit.xml}`.
This uses the unchanged 490-test scope plus the three new case tests:

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest \
 tests/starlink_oracle/test_psma17_contract.py \
 tests/starlink_oracle/test_psma_boundary_stop.py \
 tests/starlink_oracle/test_stop_health_integration.py \
 tests/starlink_oracle/test_health_stop_summary.py \
 tests/starlink_oracle/test_shared_xfft_integration.py \
 tests/test_starlink_high_rate_paired.py tests/starlink_oracle/test_ddc.py \
 tests/starlink_oracle/test_pilot_ddc.py tests/test_starlink_pss_tracker_coefficients.py \
 tests/test_starlink_bank_native_paired.py tests/test_starlink_high_rate_harness.py \
 tests/test_starlink_native30_budget.py tests/test_starlink_high_rate_cases.py \
 tests/test_starlink_high_rate_case_result.py tests/test_starlink_high_rate_case_bundle.py \
 --basetemp=build/high-rate-cases-regression-v1/pytest-tmp \
 --junitxml=build/high-rate-cases-regression-v1/junit.xml -q
```

Use a new basetemp for any independent rerun. Two full derived tops were
elaborated only with a fail-fast inert FFT interface: never executed.
Parser-only healthy/negative specimens are explicitly synthetic. Mutations
cover missing/duplicate/context-wrong receipts, tails, no-work/lead/budgets,
PIL1/tuples, changed oracles, source/closure/dependency graph, strict inverse,
runner mismatch, no-overwrite and unsupported entry arguments. Tcl stubs
test project/launch failures, original-error preservation and post-failure
integrity without launching Vivado. Python subprocess environment overrides
are removed only from that subprocess, not parent Vivado.

Retained attempts under build/high-rate-cases-offline-v1..v4:
v1 had19PASS/3FAIL: two mutable dictionary-receipt test bugs and one
native-only endpoint observer incorrectly counting pre-configuration
coefficient preparation. Actual late handshake/rejection was already
correct. Only recipe copying and config-qualified test observer changed;
no RTL, bounds, goldens or expected zero-work behavior was relaxed.
v2:22PASS; v3:128PASS; v4:160PASS. Final652 includes two added dependency
graph mutation cases. Initial logs, source snapshots and contract-before
are retained. No failed actual FFT run is hidden because none was launched.

`original51-rederive.log` records the immutable snapshot producer's PASS.
`source-after.json` verifies all104 live sources, both bundles and all51
original goldens after regression. The portable archive/adjacent JSON in
reports/experiments carries both frozen bundles, this report, logs and
failed/passed native-only provenance; duplicate transient test bundles and
compiled bytecode are omitted, with all raw local attempts retained.

Parent authorized one actual healthy343 launch only after these local
commits/receipts. Late447 remains offline-prepared, not launch-authorized.
The new runner requires exactly NEW_RUN, frozen case bundle and explicit
Python, Vivado2022.2 and two threads. Working parent environment must use
`env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE` before
`/opt/Xilinx/Vivado/2022.2/bin/vivado`. No retries, tail extensions,
runtime changes,60 profile, physical work or radios are authorized.
