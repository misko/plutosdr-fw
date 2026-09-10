# Startup diagnostic identifies undriven completion control

## What the diagnostic proves

Parent42893 exits0 after3.39s, but the HDL simulation reproduces the original
fatal at cycle31/time174285723fs. XSim returns0 after `$fatal`; this is a
**successful failure reproduction, not a healthy simulation or qualification**.
There are zero accepted FFT jobs and zero commits.

The exact originally elaborated tb_behav snapshot was copied into a new owner
directory with xsim.ini and eight memory files. No compilation, IP regeneration,
runtime source change, assertion change, force or reset change occurred.
The reviewed additive Tcl logs66 explicitly named controls, resolves them by
literal equality against enumerated objects, and caps execution at250ns.
The original assertion stops it first. Only the copied xsimkernel.log changes
among copied inputs. A complete before/after inventory of the original attempt
matches; the live71-source frozen bundle also verifies before and after.

Original read-only WDB discovery had created a tool settings directory
`xsim.dir/tb_behav.wdb`, without changing that WDB. This settings directory is
not part of the executable snapshot copy. The new before/after original
inventory includes it as found; no claim is made that prior discovery created
no tool settings files.

## Recorded fault boundary

Parent77816 reads the new WDB without advancing simulation. The independent
audit examines5985 queried rows:2470 recorded and3515 explicitly unlogged.
The latter are not treated as X, zero, or evidence. All required fault-boundary
signals are recorded. Physical-time snapshots do not resolve same-time HDL
scheduler iterations.

| Observation | Recorded result |
| --- | --- |
| completion_accept and cutover.producer_closed | Z at all95 sampled times |
| fast_running release | 162857151fs |
| first enabled edge: cutover reason0 latches | 168571437fs |
| unchanged health assertion fires | 174285723fs |
| boundary known predicate | 1 |
| boundary job/config accepts, raw frame/output/status/vendor faults | 0 |

The source checks unknown producer_closed separately from the raw known
predicate and sets reason bit0. This directly explains the recorded startup
fault. The compiler's warning that completion_accept was implicitly declared
before its later initialized-wire declaration is the leading mechanism to
test, not yet an independently reproduced compiler root cause.

The completion_receipt register is Z at the final snapshot after sampling the
undriven control. It already has an explicit early declaration and reset; no
new receipt-state behavior is proposed. Observed payload_checks=2 and
forward_checks=61 are known integers. Earlier initializer warnings therefore
do not establish a counter-initialization failure in this diagnostic.

## Next correction and remaining gates

Approved narrow candidate change: declare `wire completion_accept;` before its
first use and change the later initialized declaration to a continuous
`assign completion_accept = ...`, preserving the entire RHS. Require an exact
two-edit inverse, unchanged reset/fault/numerical semantics, offline regression,
a new transparent source bundle and actual compilation/simulation. Keep both
previous failed bundles and this diagnostic unchanged.

No runtime correction has been qualified by this report. Full actual numerical
tests, physical setup/hold/CDC checks, complete60MS/s receiver calibration,
causal scanner/IIO comparison and PPU/radio deployment remain open.

## Evidence

Diagnostic Tcl SHA256:
`4365a58bc809b6a2049c47f2513c6275bd2481a30b8f888a7f46d0b5c080a7d6`.
Diagnostic WDB SHA256:
`709e3c030edb874d544a3ad66320bcd5488ff21b0145f5c8109338377191b088`.
Archive `20260910-retained-startup-diagnosis-parent.tgz`, SHA256
`d77af9a3add46ef54e0adc38a8c3c074dd3c87f82f09ebf207d9e791bc52171a`;
tar comparison exits0. It contains the copied executable inputs, original/
copied before-and-after hashes, source verification, command/process/terminal
receipts, Tcl/log/TSV/WDB and independent history audit. Only `.Xil` scratch is
excluded. Recovery: `retained-startup-replay-parent.XVR8fGg5` under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.

No radio or PPU operation; no production HDL gitlink change or main merge.
