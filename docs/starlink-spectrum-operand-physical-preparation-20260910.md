# Operand-register physical A/B: preparation only

The isolated measurement runner is prepared and offline-tested. Final local
tests: **57 PASS in 2.77 s** (28 runner-policy tests plus 29 unchanged wrapper
tests); Ruff passes. Parent independently obtained 57 PASS in 2.72 s.
No Vivado synthesis, placement, routing, actual FFT or receiver build ran in
this task. Successful policy preflights deliberately stop at a Tcl
`synth_design` stub that raises `SYNTHESIS_FENCED_NO_PHYSICAL_RUN`.
Their `tool_error=1` receipts are intentional admission-test fences, not
successful physical measurements.

The previous standalone wrapper/offline slice is pinned at FW
`375c5e6f3cd76db151e908a76792d5283ade40b6` / HDL
`0aeb4c09bf572aaffe5384c49cbaf8f89d3b0dc2`. This preparation adds only three
HDL-side measurement files at HDL
`7d4efdb36629e45187d992a7b86e94825b021dbd`, plus FW policy/evidence files.
Neither the wrapper nor arithmetic source changed.

## Fixed experiment and evidence contract

`hdl/library/starlink_pss_acquisition/measure_spectrum_operand_boundary.tcl`
accepts exactly `NEW_OUTPUT REGISTER_OPERANDS`, with literal option 0 or 1.
Each option requires a distinct absent output directory. Relative output paths
are normalized before changing working directory. It rejects any tool version
other than Vivado 2022.2 and refuses overwrite.

Both arms fix DATA_WIDTH=18, BOUNDARY_ROUND_SAT=1, xc7z010clg400-1,
175 MHz nominal / 5.714 ns, and `general.maxThreads=2`. Only
REGISTER_OPERANDS differs. Constraints and flow match the earlier isolated
round-boundary experiment: BUFGCTRL_X0Y0 clock-source annotation, input max/min
1.000/0.500 ns, output max/min 0.500/0.000 ns; rebuilt hierarchy,
AreaOptimized_high synthesis, ExploreArea optimization, place, physical
optimization and route. No path exceptions or waived clock/IO constraints
are added. These are controlled OOC budgets, not measured board interfaces.

Before either Icarus preflight or physical commands, the runner freezes six
files: unchanged core, unchanged wrapper, XDC, actual-parameter probe, runner,
and runner policy test. It records all names/hashes and FW/HDL commit/status.
The reviewed core/wrapper hashes are hard admission gates. On success or
failure it rechecks the complete frozen inventory and every hash; missing,
extra and modified files fail closed. Compile/probe outputs are retained even
when their subprocess exits nonzero. The source snapshot is an exact six-file
closure of the RTL/Tcl/probe experiment, not an archive of the installed tool
binaries or whole host environment.

The actual elaborated Icarus hierarchy must report wrapper and child widths
18, wrapper REGISTER_OPERANDS equal to the selected option, and wrapper/child
BOUNDARY_ROUND_SAT=1. This zero-clock probe is distinct from Vivado mapping:
synthesized port widths are independently checked after synthesis, and the
requested synthesis generics are recorded. No unsupported post-specialization
Vivado generic property is presented as proof of actual forwarding.

For both synthesized and routed designs the runner records:

- Hierarchical utilization; every DSP48E1 AREG/BREG/MREG/PREG/CREG and cascade
  register setting; CE pins, connected nets and driver pins. Required DSP
  register properties and CEA1/CEA2/CEB1/CEB2/CEM/CEP pins must exist.
- All-path setup/hold summaries and full-clock-path reports; register-to-
  register setup/hold paths and worst slack; verbose timing checks; failing
  endpoint inventories with top-port-origin classification. A 10,000-path
  inventory cap is an error, not silent truncation.
- Separate option-specific synthesized, optimized and routed DCPs and hashes;
  optimized utilization; routed methodology and route-status reports.

Terminal completion is explicitly named a measurement, **not a timing pass
or bank qualification**. Negative slack is evidence to report, not hidden by
changing constraints. Process/source-integrity errors remain errors. Raw
Vivado logs and journals must be retained by the separately authorized launch
outside the not-yet-created result directory.

## Offline results and preserved failures

| Local attempt | Outcome | Meaning |
| --- | --- | --- |
| v1 | 11 pass, 3 fail | Correct parameter marker followed by normal Icarus `$finish` chatter was rejected by the strict one-line parser. No synthesis. |
| v2 | 43 pass | Probe changed to `$finish(0)` with explicit timescale; strict parser and actual hierarchy assertions retained. |
| v3 | 56 pass, 1 fail | Newly added synthetic empty-output fixture omitted Tcl quoting; the runner still rejected it. Test fixture corrected only. |
| v4 | 57 pass | Full final admission and unchanged wrapper suites pass. |

Original unique build directories are
`hdl/library/starlink_pss_acquisition/build/operand-physical-preparation-v1`
through `-v4`. Their XML receipts, raw sources/logs and rejected mutations are
retained. Eleven malformed-output cases include empty, duplicate, wrong
option, wrong child width/rounding, trailing FAIL/FATAL/ERROR, unknown text,
malformed text and the original normal finish chatter. Only the exact single
parameter line is accepted. A synthetic nonzero probe exit is rejected even
with the correct marker. Real invalid-REGISTER and wrong-instantiated-width
probes still produce fatal/nonzero exits, proving `$finish(0)` does not mask
negative execution semantics. Source inventory mutation, version, invalid
selection, nonoverwrite and relative-path tests also pass.

Parent's first independent run likewise reported 11 pass / 3 fail in
`/tmp/pytest-of-mouse9911/pytest-4927`. Its raw files were inspected while
present, but automatic pytest retention removed that directory before archive
creation. **Those parent raw files are not claimed to be archived.** The local
v1 original failure sources and logs are preserved; they are not relabeled as
the missing parent execution. The JSON explicitly records this distinction.

Archive:
`reports/experiments/20260910-operand-physical-preparation-evidence.tgz`
SHA256 `a2567f8255033677990d81db22be292a85aed9686904bd93ed8759fd34fc13be`;
1,836,455 bytes, 953 safe unique regular files, all member hashes verified.
`20260910-operand-physical-preparation-results.json` contains all hashes,
per-attempt outcomes and final six-source identities. Valid option-0/1
preflights in every attempt have exact six-file pre/post identity. Deliberately
mutated temporary inventories are labeled negative tests, not intact sources.
Generated `.vvp` executables are omitted; source, inputs and logs are retained.

## Remaining authorization and interpretation gates

Do not launch this script until the frozen source-specific A/B run is approved.
No physical data or DSP-register inference result exists yet. At width 18 the
logical option adds 152 bits; placement may map them to fabric FFs, DSP input
registers or a mixture. Only the proposed measurement can establish that.

Even a favorable isolated A/B result does not qualify the actual bank
BRAM-to-DSP path, its metadata/ready fanout or full receiver timing. Option 1
adds exactly one no-stall clock, and stalls change absolute overflow-pulse
observation timing. The pulse means core output insertion, not downstream
acceptance. Bank current/late fault veto and private-before-public ownership
must be independently requalified before any integration. No runtime RTL,
bank composition, source/coarse/native/pilot golden, .17/.18 radio, PPU or
primary worktree was changed. Source 15/30/60, continuous canonical coarse,
original-rate native fine, 2.5 MS/s pilot and eventual eight-target/120 ms/300 s
requirements remain open beyond this isolated evidence.
