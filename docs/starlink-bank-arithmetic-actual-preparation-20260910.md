# Bank arithmetic: actual-FFT preparation, not an actual replay

Final offline preparation passes **180 tests in 21.62 s**: 79 new policy/reference
tests plus the unchanged 101-test arithmetic/control regression. Ruff passes.
No Vivado, generated-FFT simulation, synthesis, route, receiver or hardware run
was launched. The two v2 preparations below are ready for source-specific review,
not authorized to execute by this receipt.

## Exact source and comparison

This is additive to FW `5235285a60aa03b8f2946cf5c93dd66547284e51` /
HDL `41e539e768fde9f36dcb67aeedc7971de6e84d73`, retaining the original offline
freeze. Prepared HDL is `5e4c2ad291ac682308ea65b2a48758b2d445b75c`
(preparation `2b741a65479cb664208627c69a1cb6d436336647` plus receipt-order fix).
Original dec20 bank, product, guard, numerical vectors and actual-core bench
are unchanged. No runtime integration/promotion occurred.

The distinct actual bench derives from exact
`dec20d6371f2d77b6e09c4bcdda2f3d7f8715776`. A strict inverse restores every
original stimulus, wait, comparison, control/fault check, trace write and receipt.
Changes are its module identity, explicit R/B/O parameters, new probe binding,
two compatible shadow bindings, arithmetic-private hierarchy references, and an
additive observation include/final receipt. **R = REGISTERED_SCHEDULING,
B = BOUNDARY_ROUND_SAT, O = REGISTER_OPERANDS.**

Smallest proposed actual matrix, both at slow 100 / FFT 175 MHz:

- Baseline: R1/B0/O0, preserving the historical dec20 registered control path.
- Candidate: R1/B1/O1, changing only the reviewed arithmetic options.

Both prepared source sets contain 42 files; only `profile.tcl` differs. The
runner also admits these same two profiles at 200 MHz, but those would require
separate authorization. It rejects R0 and mixed B/O arms rather than silently
replacing the same-scheduling comparison with a smaller fault matrix.

## Latency and references

O0 binds the entire unchanged old payload shadow. O1 keeps the old independent
joiner/ROM/arithmetic and adds a separately typed reference token slot driven
only by old-join outputs, not DUT payload. Wrong-latency, dropped-token and
metadata mutants are rejected. The separate shadow-unit stimulus needs one extra
fill token for O1; **the actual-core stimulus and cycle bounds are not retimed**.

Measured real-arithmetic unit bounds distinguish output visibility at +2/+3
clocks from the accepting-bank edge at +3/+4 clocks. The actual bench will check
`3+O` for 32 nominal first-product acceptances. It keeps the original 1,500,000
fast-cycle watchdog, 25,000-cycle drain, 24-cycle fault observation, and 128–132
provisional-prefix bound. The original status-present/absent, current/late fault,
one-sided reset, private-before-publish, held-overflow and real ACK checks remain.

R1 baseline175 must match the **complete historical trace CSV** SHA256
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`
(35,655,334 bytes, independently rehashed at its original saved path). No shifted
candidate CSV equivalence is asserted. The nominal/stalled R1 core-job contract
stays config delta 3, input span 513, last-input→first-output 781, admission→commit
1810 clocks; the older R0 1809-cycle contract is not substituted.

## Numerical and launch contracts

All eight original source/kernel/forward/product/inverse/exponent/score files
are hash-pinned. Preparation independently recomputes 1,536 spectrum products
using integer complex multiplication and ties-even shift 18; it checks the three
source PSS controls, coefficient energy 1,073,742,825 and 1,341 inverse/source
scores with 66-sample energy, exponent scaling, 69-bit saturation and ties-even
normalization. No global C-model width is changed and no new goldens are fitted.

The future actual run records 19,456 ordered words per forward/product/inverse
stream over 32 nominal and six stalled blocks. Fast probes sample `fft_clk`;
slow inverse probes sample `clk`. Independent ordinal/start/TLAST/exponent/data
checks yield 16,986 per-sample score comparisons from captured inverse outputs.
**These scores are oracle-only: no scorer RTL, scheduler, energy-cache capacity,
continuous canonical-source, native-fine or pilot qualification is claimed.**
The original late partial-prefix quarantine remains a separate required check.

The source closure rejects a synthetic FFT module even under a renamed file.
The unchanged Vivado 2022.2 IP factory (SHA256
`0795ea7e6aa981d78080ac22fa4ba6355da59d6829ceb409dda07a54f7f9420d`)
retains all generated port/generic checks, including 512/18-bit BFP realtime
behavior. Its original target settings are unchanged. The new actual bench was
Icarus syntax-checked with the missing vendor module ignored, **not simulated**.

All ten imported repository Python modules plus the policy file are frozen.
Launch/postprocessing uses a frozen standalone helper, `-B`, and clears only
child PYTHONHOME/PYTHONPATH/LD_LIBRARY_PATH; the parent vendor environment stays
intact. New-project/restart checks precede launch. Success and failure both get
independent source/manifest integrity verification; original error/options and
after-integrity status survive in `run_outcome.txt`. `results.json` is published
only after both statuses are zero. Old-only/raw217 PASS, duplicate/incomplete
receipts, late failures, altered bounds and malformed events are rejected.

## Frozen artifacts and limitations

Under `hdl/library/starlink_pss_acquisition/build/`, the final directories are
`bank-arithmetic-actual-baseline175-prepared-v2` and
`bank-arithmetic-actual-candidate175-prepared-v2`. Neither has a project or launch
receipt. Their manifest SHA256 values are respectively
`c0366928757d83ec61e8e772e01e498a5aa8c680ce8ef8e375d59d8c72ad445b` and
`df31efc303aee3bf3fb2b065839b672d70e9d8d7f454ff7e3602a77b0f10ad52`.

Final archive `reports/experiments/20260910-bank-arithmetic-actual-preparation-evidence-v2.tgz`
is 18,102,861 bytes / 3,775 safe unique regular files, SHA256
`d8ebb01d798fd8bcc4ce0cf15eda588a5f2f857210d0046a66a5ae84415b7ce8`.
The adjacent `...-results-v2.json` contains every member/source hash and manifest.
All hashes were rechecked. Installed third-party binaries are not archived.

The superseded v1 archive preserves attempts v1–v6 and v1 preparations unchanged:
84,191,062 bytes / 13,004 files, SHA256
`8ceb83c3b3e63dbb55f428e2556e8291261e98bc382e0970b4bc5364d17db670`.
Do not launch that superseded runner: its result JSON preceded after-integrity.
Initial v1 tests had 50 passes/one failure from a test branch misclassifying
"latency" as "late…"; the corrected and expanded attempts passed. Mocked policy
cases deliberately retain errors, source mutations and mock launch/result files;
none are actual FFT runs. A specific early-publication mutant reproduces the
forbidden stale JSON and is negative evidence, not a passing replay.

The next action is review and explicit authorization for the two final 175 MHz
profiles. Actual FFT behavior, bank timing/resources, full score composition,
source 15/30/60/native fine/pilot concurrency, .18-before-.17 deployment and
eight-target 120 ms/300 s operation remain separate gates.
