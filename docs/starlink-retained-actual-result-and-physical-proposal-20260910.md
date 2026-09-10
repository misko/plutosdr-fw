# Retained-output actual result and bounded physical proposal

## Actual result: qualified seven-context increment

Parent-owned original 13931 completed with terminal **0**, 56.16 s, at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-actual-frame-parent.2nhHxm1Q`.
Tested FW `e1fa85a290e60c40bc16cc13608f48f1239e7ab2`, HDL
`28a822025a3ba5e47608b8875ff252baf73e8f42`, exact v5 bundle
`c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8`.
Parent independent 251 tests passed in 46.48 s, with 80 source pins unchanged.

Independent lane audit rehashed all 83 copied-bundle receipts and generated FFT
wrapper before/after (`a3a650654118016012bdfb8553114ee4a89866466d8ca774fa0f281640168a68`).
It independently read every numerical CSV row against the frozen vectors,
including 48-bit zero-padded inputs, sign-extended raw outputs, exponents, source
identity, physical input coordinates and frame/reset/configuration joins.
The frozen standalone result CLI was also rerun from `/` and passed.

| Evidence | Actual measured result |
|---|---:|
| Contexts / admissions | 7 / 40 (21 F, 19 I) |
| Complete jobs / pairs / aborted F | 38 / 19 / 2 |
| Raw / physical input words | 19,456 / 19,585 |
| Source / product / private inverse / slow reads | 10,752 / 9,728 / 9,728 / 8,704 |
| Frame records / reset-release joins | 40 / 40 |
| Aborted F input lengths | 64 and 65 |
| Eligible dispatch / nominal recurrence | 8 / 3,645 fast clocks |
| Parked-reader recurrence | 4,912 fast clocks |

All 40 actual frames were observed at admission +8, with two accepted inputs
before the event, one on the event edge, three after counting that edge. This is
a measurement of these inputs/core/contexts, not a universal vendor timing rule.
All original exact config, 513-cycle input span, raw-first +781, status ordinal 2,
publication +1810, guard and global bounds remained unchanged.

CSV SHA: `07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`
(77,953 rows, byte-identical to the frozen scripted numerical CSV).
Actual simulation log: `e9a77faa32ace748f606f00753a43da3dd542301c39f44ffa7ad0e9432116e52`.
Saved result: `a4f9fe4936a8353ab282a9c54b708c2fb3d072b83947aab80b3fa4a4c99a6585`.
The earlier compile, declaration, logger and frame-assumption failures remain
preserved; this result does not reclassify them or qualify all 415 scripted cases.

The independent offline raw audit also verified all 40 first-input, idle-gap and
mixed-later frame placements in each directed healthy script, with identical CSV
bytes. Eight malformed producer runs rejected. Those malformed injections stop
in the first F job; they are not an executed all-phase fault matrix. Pulse width
is a sampled-clock property, not a subcycle glitch measurement.

Compact evidence: `artifacts/retained-frame-actual-v1.tar.gz`, SHA
`3e70328c934ba6ae767806e4738134152d41bca5ad0a074b3a13dc6126d05d68`,
1,510,205 bytes, 126 safe regular members / 125 file receipts. It includes the
complete frozen bundle, owner/terminal/raw compile and simulation logs, complete
CSV, and generated wrapper. All 214 raw-run files / 37,205,852 bytes were hashed
before/after packaging and remain in place; the generated project is not duplicated.
The collector is separate packaging tooling, not code claimed covered by the 251
test run. No agent vendor invocation occurred.

## Proposed next gate — no invocation authorized by this document

Use the exact qualified default-off public top
`starlink_pss_fft_bank_owned_retained_output_probe`, with explicit, unique
`ENABLE_RETAINED_OUTPUT=1`, `REGISTERED_SCHEDULING=1`, `BOUNDARY_ROUND_SAT=1`,
`REGISTER_OPERANDS=1`, `LOCAL_FIRST_ADMISSION=1`, and the frozen kernel path.
Do not synthesize the actual bench or replace the wrapper with a shortcut top.
Copy source bytes from the reviewed actual bundle, not a moving worktree.

The source closure is the **16 `.v` files** already compiled by that actual run:
the nine `retained_output/baseline/*.v` files and seven direct
`retained_output/*.v` files, plus the original kernel and exact FFT factory.
This retains the inactive default branch as source without elaborating a second
FFT. Exclude only the simulation bench, clock witness, shadows and test-only
reference bodies. Mark the exact RTL list as SystemVerilog, as the successful
actual runner does; do not modify the files or the generated VHDL language.
Require one FFT/DSP datapath and three payload banks, zero black boxes and no
unresolved/implicit control nets. Preserve all diagnostics, not just tool exit.

The preliminary source-state budget remains +223 declared non-array bits:
one additional 180-bit result guard, 17 retained-owner bits, 17 cutover bits and
nine barrier bits. This is not mapped FF utilization. Compare full mapped
LUT/FF/control-set/DSP/BRAM and hierarchical counts to the R1/B1/O1/L1 reference;
that prior synthesis reported 21 DSP48E1 and 7.5 BRAM tiles. No resource bound or
area saving is inferred before the new run.

Reuse the source-specific preparation/owner pattern of
`local-admission-ooc-L1R1B1O1-175-prepared-v1/synthesize_local_admission_prepared.tcl`
(SHA `45eadaf8042a34451d40a555b35343fc84b214dd61b4d4fb5426c29c7a2e3281`),
with only the exact top/source/generic/source-proof adaptations above. Keep
Vivado 2022.2, `xc7z010clg400-1`, two threads, OOC synthesis, rebuilt hierarchy,
`AreaOptimized_high`, IP `Flow_AreaOptimized_high`, control-set threshold 4, and
the existing synthesis-thread pre-hook. Keep FFT factory SHA `0795ea7e...`,
including its original target-frequency 200 / throughput 40 configuration;
those IP-generation settings are not changed to manufacture a timing result.

### Constraints and reports

Copy the literal prior clock XDC SHA
`bac30eff84cc71d1f273104b716b388b55e51d33be10f9beaf1901232193ba3f`:
`source_100` on `clk` is 10.000 ns; `island_175` on `fft_clk` is 5.714285714 ns.
**There are no clock groups, false paths, multicycle paths or I/O delays in this
comparable resource-probe XDC. Preserve that absence.** Do not add asynchronous
groups to hide cross-domain paths. Vivado's inherited XDC displays 5.714 ns;
record both literal input and effective clock properties rather than confusing
display precision with an intentional clock change. Keep generated-IP OOC
constraints unchanged and inventory every effective constraint file/exception.

Synthesis is a first separately approved stage: exact source/generic admission,
full hierarchy/resources/clocks/CDC/check-timing/unconstrained reports and hashed
DCP. A second separately approved route takes that exact DCP hash, never an
arbitrary newly selected checkpoint. The prior route script SHA
`0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`
provides the `opt_design; place_design; phys_opt_design; route_design` sequence.
Do not change directives or retry opportunistically after a negative result.

Extend only observation reporting: setup and hold top 20 paths in each
source→source, island→island, source→island and island→source clock pair, plus
global min/max timing summary with unconstrained paths, route status, clock
interaction, exceptions, CDC details and verbose `check_timing`. Keep start/end,
logic/net delay and fanout detail for remaining cones, including admission,
result-guard live faults, completion/cutover, retained release and epoch barriers.
Never report only the best internal group. Include pulse-width results and
all missing/unconstrained endpoint diagnostics. If a group has no paths, record
that explicitly with its clock inventory; do not silently omit it.

Use unique absent non-`/tmp` preparation, synthesis and route output/owner paths;
explicit external logs/journals; SuSE library environment only for Vivado;
sanitized pinned Python for child verifiers; original process ownership and
bounded terminal handling without retries. Before and after success **or failure**,
verify original/copy source closure, generated-IP settings/wrapper and DCP hash.
Do not alter a runtime source, clock, timing exception or budget during the run.

Any physical outcome remains an isolated two-clock OOC diagnostic, not full
receiver placement, CDC sign-off, external-I/O timing or deployment approval.
The measured 3,645/4,912 cycles are at the tested ideal 175/100 clocks with an
already-full next source; they do not establish lower-clock operation or
continuous canonical 15 MS/s / native 60 MS/s source capacity. No P1/K/M/C1 or
inverse-sealed variant is silently combined with this qualified runtime.
