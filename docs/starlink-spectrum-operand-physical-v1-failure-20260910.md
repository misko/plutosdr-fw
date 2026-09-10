# First operand A/B attempts: pre-synthesis environment failure

Both authorized original Vivado launches exited **1 at 07:08:40 UTC** on
2026-09-10, during the Icarus actual-parameter probe compilation. Neither
started synthesis. No DSP AREG/BREG/MREG/PREG/CE inventory, resource count,
setup/hold/internal timing, failing-port count, DCP or fully-routed status
exists for these attempts. These quantities are unavailable, not zero and
not passing.

The unchanged reviewed sources were FW
`184223801cc744c67f98dae071dd4492c6c710a2` / HDL
`7d4efdb36629e45187d992a7b86e94825b021dbd`. REGISTER_OPERANDS was the only
requested arm difference; DATA_WIDTH=18, BOUNDARY_ROUND_SAT=1, 5.714 ns,
xc7z010clg400-1 and two threads remained fixed. Actual parameter qualification
did not complete because its compiler subprocess failed first.

| Arm | Original handle | Output directory | Terminal |
| --- | --- | --- | --- |
| REGISTER_OPERANDS=0 | 19364 | `hdl/library/starlink_pss_acquisition/build/operand-route-0-v1` | Exit 1 before synthesis |
| REGISTER_OPERANDS=1 | 49440 | `hdl/library/starlink_pss_acquisition/build/operand-route-1-v1` | Exit 1 before synthesis |

Both original handles were owned and polled to terminal; neither was restarted.
Outer stdout, Vivado log and journal are in the sibling
`operand-physical-launch-0-v1` and `operand-physical-launch-1-v1` directories.
All six pre-run frozen inputs match each other, the reviewed preparation
inventory, their post-run bytes and the still-unchanged working sources.
Both receipts report `tool_error=1 source_integrity_error=0`.

## Exact cause and bounded proposed correction

Both `parameter_compile.log` files record:

```text
/usr/lib/x86_64-linux-gnu/ivl/ivl: /opt/Xilinx/Vivado/2022.2/lib/lnx64.o/Ubuntu/libstdc++.so.6: version `GLIBCXX_3.4.32' not found (required by /usr/lib/x86_64-linux-gnu/ivl/ivl)
child process exited abnormally
```

Vivado was launched with the approved SuSE library path. Its installed
`bin/loader` prepends its own platform libraries and exports LD_LIBRARY_PATH;
the system Icarus subprocess then resolves Vivado's Ubuntu libstdc++ rather
than the required system library. This actual error explains why the earlier
Tcl-only preflight passed but the same probe failed inside Vivado. Neither
arithmetic, operand ownership nor timing was exercised by this failure.

Proposed next change, **not implemented here**: invoke only `iverilog` and
`vvp` through `env -u LD_LIBRARY_PATH`, retaining every argument, actual
hierarchy assertion, strict single-line terminal check and nonzero-exit gate.
Do not alter the Vivado process environment or its synthesis/route flow.
Before any separately approved retry, offline policy tests should establish
that both Icarus children omit the inherited library path, the parent retains
it, and malformed/nonzero/fatal probes remain rejected. New frozen runner/test
identities and unique output directories would be required. No global library
replacement, constraint change or RTL edit is proposed.

## Preserved evidence

Archive: `reports/experiments/20260910-operand-physical-v1-failure-evidence.tgz`

SHA256 `95f9a5df380fe98eeb0aeff6e7536ec46973192a3fb4aee81f587fd7f5bd9514`;
22,912 bytes, 26 safe unique regular files, all member hashes verified.
It contains both complete six-source freezes, inventories, scopes, compile
failures, terminal receipts, outer stdout, logs and journals.
`20260910-operand-physical-v1-failure-results.json` records all hashes, original
handles and explicitly null unavailable measurement fields.

No retry, bank integration, actual FFT, other physical run, radio/PPU, primary
worktree edit or push was performed. The isolated A/B question remains
unanswered; bank/receiver qualification and full coarse/native/pilot goals
remain separate and unchanged.
