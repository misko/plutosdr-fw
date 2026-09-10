# Late60 settling correction: offline only, original failure retained

The corrected stimulus passed **694 offline tests in 19.08 s** on original
handle23132: the unchanged 681-test scope plus 13 clock/settling tests. No new
vendor, native service or paired simulation was launched. The original actual
handle88460 remains overallFAIL, frozen and archived at FW `f31036760`, archive
SHA `b731571cbd8ed78af1224d585d483db98b8bcd53a6764f734edf7a255ed55c33`.
Its 670 raw files and external logs remain unmodified.

## Minimal change and exact meaning

The original first audit followed eight control falling edges after a
sample-domain handshake. In the actual clock phase those edges advanced the
integer cycle label by seven, failing the predeclared parser lower bound of
eight. The correction preserves both original eight-edge waits, then waits on
control falling edges until each audit's own original anchor has advanced by
at least eight cycle labels:

```systemverilog
wait(late_handshakes==1); repeat(8) @(negedge clk);
while(cycles-late_handshake_cycle<8) @(negedge clk);
late_snapshot(1);
wait(source_finished && coarse_stopped && map_retained); repeat(8) @(negedge clk);
while(cycles-source_off_cycle<8) @(negedge clk);
late_snapshot(2);
```

This enforces the unchanged **labeled-cycle** rule. It does not introduce a claim
of at least 80 ns of physical elapsed settling. The added wait is zero or one
falling edge for all relevant phases. The first actual schedule would move from
label13565 to13566; the source-off anchored schedule already at32423 would not
move. These are independently modeled schedules, not a new actual-run result.

The HDL delta is eight added/two removed lines in the test-only late include.
No native runtime, healthy source, golden, clock, actual command/lead window,
recipe, negative parser or outer context adapter changes. A strict inverse of
the two scheduling edits restores every original late-include byte and SHA
`b3a059c7f397eba2354eefc366bd6a799e3b1228cac8e9af2429f7e242bfbda1`.
Tests also pin the original recipe/parser/context-adapter hashes. Bundle tooling
only adds both guard tokens and the new test to its source closure.

The snapshot body remains bounded by512 controls for generation and1328 for the
whole audit. The final observation bound remains2048 controls after source-off;
8+1+1328+32 still fits. The actual command window/256-control limit, lead−193..−33,
zero-native contract,62 audit reads,894 scores/447 map words,512 PIL1 samples,
16,423 original raw samples/no tail and160,000 global watchdog are unchanged.

## Phase proof and original-receipt diagnosis

An integer-clock proof enumerates all191,999 source rising and falling edges
through the160,000-control-cycle watchdog under the original quantized oscillator
origin/period. None coincides with a control rise/fall scheduling tie. The old
eight-edge wait produces label gaps7 or8; the corrected schedule always reaches
gap8 and adds at most one edge. Two standalone clock-only units copy each actual
new while loop literally and exercise12 boundary/representative phases per
anchor, including one femtosecond either side of each control-edge boundary.
Both confirm the same old/new relation. No DUT, native engine, FFT or vendor
model is instantiated in those unit executions.

The original failing run was also inspected diagnostically for later issues.
`owner/diagnostic_predicates.py` clones the frozen verifier functions with a
recording predicate observer, without mutating module globals or input logs,
and discards their result objects. It observed58 predicate calls with only the
already known first-audit aggregate failure. Its JSON explicitly says
`DIAGNOSTIC_ONLY_ORIGINAL_RUN_REMAINS_FAILED`; this is not a replacement gate,
post-hoc qualification or evidence that the unchanged frozen verifier passed.

## Source freeze and repeat

| Item | Identity |
| --- | --- |
| Tested FW | `bca3b8e1478bef46dfc953758daded2ec49c7e4b` |
| Tested HDL | `ecbb3712965ff39b144b5adf84a2a262c6c53dff` |
| Bundle | `build/high-rate60-late-settle-prelaunch-v1` |
| Bundle SHA | `79febd5abe231065f9fc77abd7c587104e4608ffd8eae40ebd5b4f20a6ac1043` |
| 119-source signature | `66eac04547dcef402651f4d2cd9a412d1c432b17045c223779076c6d8eaabfd3` |
| Corrected late include SHA | `bd477056926c6329e7c2bfcac91408510c7c049fe746584e5362e5037f8289aa` |
| Unchanged derived runner SHA | `1ca8c38a649bcfc299afb608977ac6487acb68eb16fe0a00d0a4324591e67e2c` |

The final bundle byte-matches the final pytest-generated fixture. Its 376 hashed
payload files total 7,662,700 bytes, with 119 frozen/live sources and 41 Python
import nodes. The original healthy108 source closure and 69 numerical files are
unchanged. Frozen verification CLI invoked from `/` passed. Ruff passed. Full
composition compile-only checks retain the previous inert-stub timescale and
optional-input warnings and before/after hashes; no composition vvp ran.

Initial clock-only proof: 4 PASS, 0.15 s at
`/tmp/starlink-highrate60-late-settle-unit-v1`. The early proof used Git to read
the original include; the final strict inverse pins the complete byte hash,
removing that unfrozen test dependency. Final 694 receipts remain at
`/tmp/starlink-highrate60-late-settle-offline-v1` and
`build/high-rate60-late-settle-offline-v1.{log,xml}`.
Parent independently repeated the exact seven-file scope: original64537 exited0,
694 PASS in14.62 s, retained at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late-settle-parent.26zBTKKN/{pytest.log,results.xml}`.
The earlier parent63525 quota-interrupted attempt remains separate and failed.

The first attempt to write this report encountered the shared `/tmp` storage
quota. Its exact 4096-byte partial is preserved as
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/report-partial-quota-failure.md`.
No source/test/actual process was live in this lane during the pause. Root's
separate quota-interrupted parent test attempt is not represented as a completed
repeat. All new packaging and prospective build outputs now use the non-`/tmp`
recovery directory above. The completed source/pins and original failed actual
run were not changed to recover space, and this lane deleted no artifacts.

## Frozen successor proposal, not launched

The byte-identical copied bundle is at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/frozen-bundle`.
Its own frozen CLI verified the external 79febd SHA after copying. This proposal
uses a new actual run, exclusive owner and two external logs under that same
non-`/tmp` parent. All four must be checked absent immediately before any
separately authorized launch; the following is a proposal, not executed evidence.

```sh
env TMPDIR=/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/main-high-rate60-bank175-late447-settle-v1-owner/tmp \
  LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/frozen-bundle/case/simulate_high_rate60_bank_native_late.tcl \
  -log /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/main-high-rate60-bank175-late447-settle-v1.vivado.log \
  -journal /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/main-high-rate60-bank175-late447-settle-v1.vivado.jou \
  -tclargs /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/main-high-rate60-bank175-late447-settle-v1 \
  /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/late60-settle-agent.7cjlYh/frozen-bundle \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python \
  79febd5abe231065f9fc77abd7c587104e4608ffd8eae40ebd5b4f20a6ac1043
```

Use the sibling `main-high-rate60-bank175-late447-settle-v1-owner` as exclusive
working directory, creating its `tmp` child only after separate launch authority.
Keep the unchanged two-thread policy and sanitize Python
children only. Any new temporary/build output must stay under the recovery
parent. Own the original process through terminal; no retry or parser/source/
tail/budget change after observing the outcome. Record generated-IP and original/
copied source hashes before/after even on failure, and preserve full raw output.

For an independent offline repeat use the original six681 files plus
`tests/test_starlink_high_rate60_late_settle.py`, sanitized Python-B, and unique
non-`/tmp` basetemp/JUnit paths. This remains an expected-expiry, static known
center, ideal-clock reduced447x2 composition. It is not causal acquisition, RF
truth, IIO delivery, physical60 timing or complete15/30/60 scanner qualification.
