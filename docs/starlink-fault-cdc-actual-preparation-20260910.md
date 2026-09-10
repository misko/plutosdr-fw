# Per-cause fault CDC: offline actual-run preparation

This checkpoint prepares, but does **not execute**, one R1/D1/S1/C1, extras1,
175 MHz, QUICK0 vendor-core run. The runtime is unchanged from the reviewed
CDC candidate `02de07cc7a6c241dd6cc8cf5b733037d89eac6bd`; no new synthesis,
route, CDC closure, radio, or release claim is made. The prior routed candidate
still fails timing and has the open CDC-10 finding.

Tested preparation source: FW `f5c488ddaf1317e776a80e4d2389f43ba5ed5abf`,
HDL `ae364af2e0a8600c38cbe0c5b2d524ad410ba2dd`.
Prepared directory:
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1`.
Its 48-member inventory SHA is
`9c81c43d9ed0bbc6cfba1d40074d11ec8cd94530fc9d7920de809bd6d68ce39c`.
The project directory is absent. Preparation handle44081 exited0.

## Exact admission and comparison scope

The historical source is the independently passing111 actual freeze
`extra-edge-combined-prepared-v1` (inventory `8e9251fe…`). Admission replays
its original terminal receipts, process completion, complete source inventories,
qualified-status accounting, and full main/extra CSV hashes. Main CSV remains
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`;
both complete extra CSVs must remain
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0`.
The old physical adapter is used only for its read-only historical admission
function, never to launch synthesis or select new physical settings.

The candidate is R1/D1/S1/C1; the internal independent reference remains
the frozen dec20 R1/D0/S0 design. It is **not replaced by111**. All original
healthy/fault/extra-edge stimulus, original assertions, numerical/latency/CSV
gates, original observers, and all seven reference modules are byte-identical.
The candidate wrapper alone has the already tested default-off CDC addition;
its strict inverse restores the historical wrapper, and the other six runtime
modules are unchanged.

The top adds only a C parameter, explicit DUT binding, an observation-only
include, and terminal task call. The Tcl adaptation adds explicit C option
inventory/readback and strict CDC receipts, plus the historical extra CSV hash
gate. The full old bench and runner are recovered by literal inverses. Omitted,
duplicated, malformed, case-changed, and incorrectly forwarded C settings fail;
the hierarchy checks forwarding at time0 and again at completion. C0 is
elaborated offline for attribution, but no C0 vendor rerun is proposed.

The new observer shifts actual `dut.fast_fault` through an independent scalar
two-stage model on the source clock, using exactly `dut.slow_running` reset.
It compares both actual aggregate destination stages on both source-clock
edges after2ps settlement, without delaying or driving existing signals.
Terminal receipt requires nonzero stage0, stage1, reset, and aggregate-current
fault observations and at least two final-index fault edges. These are sampled
edge counts, not distinct fault-event counts. `private_core_reset_samples` is
recorded even if zero; a positive quiescent-fixture count is not actual private
FFT-reset coverage. The original independent active/ownership/final-fault and
one-sided-reset checks still apply unchanged.

The existing qualified-status policy is unchanged: all216 other fields remain
unconditional, and all8 status-data bits compare whenever either valid is not
exactly zero. Invalid-only status differences retain separate accounting. A
future result must pass the original runner **and** the frozen
`verify_result` replay (original exact receipts + original status validator +
strict CDC receipt). This does not assert original raw217 equality.

## Executed offline evidence

- First attempt97287: **38PASS/2FAIL**, 11.36s. Icarus rejected X/Z `-P`
  overrides with an error diagnostic but returned0 and retained the default.
  The unexpected PASS witnesses are preserved; neither was credited as X/Z
  coverage. Literal fixture-source X/Z overrides now fail with the expected
  time0 option error, without broadening accepted rejection markers.
- Attempt62222: **61PASS**, 10.73s.
- Final55700: **101PASS**, 16.22s, terminal0: 61 new preparation/observer tests,
  37 unchanged runtime CDC tests, three unchanged combined-preparation tests.
  Ruff passed on both new Python files. No Vivado invocation occurred.

The new executed observer fixtures use the real runtime and an independent
frozen old runtime, but a **quiescent FFT stub** and explicit source-Q/event/index
snapshots. They cover aggregate recurrence, all4096 cause subsets, X/Z, clock
phases, resets, and checker/receipt/binding mutations; they are not active FFT
lifecycle or numerical proof. Actual top hierarchies are compiled with C0/C1
but their stub executables are never run. Parser replay uses the historical
actual log plus a plainly labeled synthetic CDC receipt; that is parser testing,
not evidence of a completed C1 actual run.

Archive: `hdl/library/starlink_pss_acquisition/evidence/fault-cdc-actual-offline-v1`.
It has1725 members (19,461,322 bytes), inventory SHA
`0e1d4b836d244a21790704ec0a88a55c690788eb2378cad487a7d00a11b588d2`.
The independent read-only Git-object verifier passed at HDL
`597a8ab65ce9d4ee68b4ca0fe4a98ab48604beb7`:1725 members,1726 tracked files.
Original audit17994 exited0; raw receipt is
`/tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-git-object-audit-v1.log`.
An initial invocation mistyped the full commit ID and correctly failed before
reading any archive; the corrected invocation used the actual `git rev-parse`
result. Neither invocation changed source or evidence.
It contains the complete prepared freeze, helper/observer/test dependencies,
all three terminal logs, first failed source snapshot, and bounded case inputs
and receipts. Large generated VVP executables and the derivative parser-only
copy of the historical log remain in the original temporary test directories;
the immutable historical actual log remains in its prior archive. No original
failure, WDB, CSV, or timing archive was changed or deleted.

## Proposed actual invocation — requires separate source-specific approval

Expected runtime is approximately ten minutes based on the prior111 run's
593.59s, not a timeout allowance or performance guarantee. Use the existing
absent project in the exact prepared directory, Vivado2022.2 and maxThreads2.
Before launch, verify the inventory identity above and run `sha256sum -c` into
`actual-before-source-verification.log`. The proposed single tool command is:

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
  /usr/bin/time -v -o /tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1/actual-time.txt \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch -notrace \
  -log /tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1/actual-vivado.log \
  -journal /tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1/actual-vivado.jou \
  -source /tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1/frozen_sources/simulate_exact_control_prepared.tcl \
  -tclargs /tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1 \
  > /tmp/starlink-completed-input.5EaJuD/fault-cdc-actual-prepared-v1/actual-launch.log 2>&1
```

Own the original process handle to terminal without timeout restart. Record
after-source integrity on **failure as well as success**, retaining original
process status separately. Replay the frozen `verify_result` using sanitized
Python (`env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH …/python -B`), and
retain exact CSV/receipt/count evidence. No synthesis/route follows automatically.
