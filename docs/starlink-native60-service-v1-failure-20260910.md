# Native60 v1: retained pre-command failure, no service qualification

The one parent-authorized native60 standalone launch failed before command
submission. Original process returned directly (no live session handle), exec
chunk `e3a218`, launcher exit1 after0.1725s. Compiler exit0, zero diagnostic
bytes; simulator exit1. No retry, source edit, changed bound or numerical
regeneration followed. FW launch pin `6fb7944aff1230652ba952c824f22902a5b0aa7e`,
HDL `50880a4a57c8105c91097651a2dae8ea3ff8d366`.

Original output: `/tmp/starlink-bank-route.I50MDJ/main-native60-service-v1`.
Full241 files/6,292,185 bytes remain in place, including compiled native.vvp,
all inputs, complete source/logs and before/after receipts. Archive:
`reports/experiments/20260910-native60-service-v1-failed.tgz`,1,709,940 bytes,
SHA256 `200ec173c89f24dea9ca50d3633d8e1c7e74a3b5060d701702660794cc9bfaa0`.
Archive contains241 regular files and16 directories, no other entry types;
`tar --compare` against the original run tree succeeded. No generated project
or evidence was deleted. Source and69-fixture before/after comparisons pass;
runner integrity_error is null and no terminal.json success receipt exists.

Exact invocation from the isolated high-rate60 worktree:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH \
 /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
 build/native60-budget-prelaunch-v1/source_snapshot/tools/prepare_starlink_native60_budget.py \
 run build/native60-budget-prelaunch-v1 \
 /tmp/starlink-bank-route.I50MDJ/main-native60-service-v1 \
 --expected-bundle-sha 45e61eec6c2f40916af9f767631ca8281cef338bab06674732bcc5ee6af7ca1a \
 --authorize-native-service
```

## Observed result

Configuration receipt at control cycle2700 passed public ID/ABI/rate60/geometry
0f8c1108/caps1d, generation60000001 and Eh1073758594. Failure at cycle8295,
source count3357, simulated time82,950ns:

```text
NATIVE60_FAIL native60 public current-index snapshot outside admission window cycles=8295 source=3357
```

Exactly3357 source rows were checked/logged; last raw index34359738567
(`00000008000000c7`). Capture, raw tuple and hold logs contain zero rows;
there is no command-admission receipt or packet. This does not establish native
capture/correlation arithmetic, all257 drainage, post-source-off service or
84,000/88,000 completion limits. The failing assertion did not print the public
current-index value, so that value is not an observation in v1 evidence.

## Read-only source diagnosis

`axi_starlink_pss_tracker/README.md:49` explicitly describes low-then-high
readback as a coherent Gray-CDC snapshot that may lag the live stream.
Runtime `axi_starlink_pss_tracker.v:235` registers the accepted source index as
Gray, then passes it through two control-clock synchronizers. Lines627–628
return synchronized low and retained snapshot high; line944 captures both
halves on the low-register request. No runtime change is proposed.

The new bench currently imposes the actual-handshake interval's lower bound
34359738560 on that deliberately delayed software snapshot, as well as on the
real scheduler handshake. Those are different clocks/observations. The actual
handshake closed[34359738560,34359738720], lead[1535,1695] and <=256-cycle command
deadline must remain unchanged. The snapshot failure is consistent with a
bench precondition error, but the absent value prevents confirming it directly.

Independent ideal-RTL timing derivation (not a substitute for a diagnostic):

- The source index is offered on a falling edge and accepted on the next
  rising edge,8.333333ns later. The trigger can therefore name an offered beat
  that has not yet entered the Gray register.
- An accepted index reaches the decoded two-stage synchronizer after the next
  two control edges,10–20ns later under these noncoincident ideal clocks.
- At a control-edge low-register capture, nonblocking assignment semantics
  expose the OLD synchronizer2. This is the Gray register sampled two control
  edges earlier; its corresponding accepted source sample is20–36.666666ns
  old at that capture, assuming continuous source cadence.
- The wrapper's registered read banks and up_axi acknowledgement/data registers
  add read-return latency; completing the high read does not refresh the
  low-read snapshot. Its age at final readback is larger still.

Using the already observed configure completion at27,000ns and the declared
oscillator phase, first raw offer is predicted at27,002.098920ns; the fixed
trigger offer at82,818.763354ns. With the unchanged free direct AXI master,
request/capture edges are predicted at82,825/82,835ns, and the old synchronizer
at capture corresponds to the accepted beat at82,810.430021ns: index34359738559
(trigger minus one). Low-read completion is predicted at82,880ns and high-read
completion at82,950ns, the latter matching the observed failure time. These
specific index/read coordinates are an inference from scheduling and RTL,
not recorded values; the proposed print-only diagnostic must confirm or refute
them with no moved acceptance condition.

## Proposed print-only diagnostic, NOT applied or launched

Proposed new output (currently absent):
`/tmp/starlink-bank-route.I50MDJ/main-native60-service-diag-v1`.
Minimal include delta below splits the existing same-line sequential reads and
adds only zero-delay displays. All clocks, source samples, admission checks,
budgets, read/write operations and original failure assertion remain unchanged.
At after_lo the automatic current_index upper half is still unassigned; log the
full retained hardware snapshot separately to make that expected X explicit.
No unknown field is accepted as a valid completed64-bit public readback.

```diff
--- a/library/starlink_pss_acquisition/tb/native60_budget_checks.svh
+++ b/library/starlink_pss_acquisition/tb/native60_budget_checks.svh
@@
-    read_reg(2, 8'h18, current_index[31:0]); read_reg(2, 8'h1c, current_index[63:32]);
+    read_reg(2, 8'h18, current_index[31:0]);
+    $display("NATIVE60_CURRENT_INDEX stage=after_lo cycle=%0d time_ns=%0.6f current_index=%016x sample_index=%016x synchronized=%016x captured_snapshot=%016x trigger_cycle=%0d",
+      cycles, $realtime, current_index, sample_index, native.current_sample_index,
+      native.current_index_snapshot, native_trigger_cycle);
+    read_reg(2, 8'h1c, current_index[63:32]);
+    $display("NATIVE60_CURRENT_INDEX stage=after_hi cycle=%0d time_ns=%0.6f current_index=%016x sample_index=%016x synchronized=%016x captured_snapshot=%016x trigger_cycle=%0d",
+      cycles, $realtime, current_index, sample_index, native.current_sample_index,
+      native.current_index_snapshot, native_trigger_cycle);
```

This needs separately reviewed source freeze and launch authorization. It is
expected to stop at the same original assertion; it is not a corrected service
qualification run. Do not widen the real command window, extend source or tail,
or remove the failed assertion to make this diagnostic progress. Public bank60,
PSMA/PIL1/FFT composition, physical timing and RF accuracy remain outside scope.
