# XSim conditional-string logger crash independently reproduced

Parent22575 reaches terminal0 after completing12 separately owned minimal
cases. Each compiles with xvlog --sv, elaborates with xelab --debug typical
--relax --mt2 and its exact CASE parameter, then runs in a unique directory.
There is no FFT, receiver RTL, clock or radio in this experiment. The task body
and CSV format are byte-identical to the full actual witness.

| Cases | Construction | Observed outcome |
| --- | --- | --- |
| 0,1,6,7 | Literal strings, both stream families/phases | Exact two-row CSV |
| 2,3,8,9 | Conditional string expression | Kernel crash; partial second row |
| 4,5,10,11 | Explicit if/else with literal calls | Exact two-row CSV |

All36 tool exit codes are0, including the four kernel crashes. The parent
therefore checks text markers and exact bytes, not exit code alone. An
independent audit confirms each crash leaves precisely the header, complete
literal source row, and partial `0,`; all healthy controls preserve the exact
expected numeric fields/times. This reproduces the specific compatibility
failure seen at the first input logger call in actual43908, without changing
the design or ignoring an assertion.

Approved next workaround: replace only the input/raw conditional-string call
sites with explicit if/else literal calls. Preserve the automatic task, full
format, numeric arguments, sampling position and receiver runtime. Require a
strict two-site inverse, full scripted CSV byte equality, a new source-bound
package and actual campaign verification. This report does not qualify the
workaround in the full campaign.

## Additional failure-marker counterexample

The frozen v3 result checker uses word boundaries around `fatal|error`, so an
underscore prevents recognizing XSim's `FATAL_ERROR` token. Parent probes the
frozen checker with the complete155-gate scripted log and matching77953-row
CSV: untouched input is accepted; appended ordinary `Fatal:` is rejected;
appended actual kernel `FATAL_ERROR:` is incorrectly accepted.

The real43908 incomplete run was nevertheless rejected by exact marker
inventory, and no earlier passing actual result is withdrawn here. Before the
next campaign, add explicit kernel-marker rejection and a regression using the
preserved counterexample. This tightens failure handling; numerical criteria
remain unchanged. Do not classify simulator crashes as successful runs merely
because XSim returns0.

## Evidence and limits

Bench SHA256 `2d76d74eb8012c8b4d627aadb8beeaf068e31c61085e80a131ab1fe69571e5f6`.
Archive `20260910-retained-logger-repro-parent.tgz`, SHA256
`e3e6d57a5e7f616f2fdd78804288424ad698b5a09efc2a413f974dabf1fbc8de`;
tar comparison exits0. Includes all12 copied sources/commands/process/terminal
receipts, compiler/simulator/crash logs, exact CSVs, independent audit and
frozen-checker negative probes. The latter reference the complete CSV preserved
in `20260910-retained-declaration-parent.tgz`; no new simulated data is invented.
Recovery: `retained-logger-repro-parent.u30ykGsn` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

Firmware startup correction is independently tested and published separately;
full FFT numerical verification, routed timing, complete60MS/s receiver/IIO
tests and deployment remain open. No radio or PPU changes occurred.
