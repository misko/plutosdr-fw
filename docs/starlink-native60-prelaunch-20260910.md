# Native60 standalone service probe: prepared, not measured

517 offline tests PASS in19.99s:261 new preparation/policy tests and the
unchanged256 numerical30/60 tests. The actual native60 public-wrapper top
compiles, but its service simulation has NOT been run. No actual FFT, PSMA,
PIL1, physical work, radio, profile admission, driver or deployment is included.
The only newly executed SV microtest contains a clock and X/Z predicates, no
native module or job. Synthetic parser specimens are not measured evidence.

## Frozen identity and source scope

Worktree `/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired`, branch
`codex/starlink-rx-only-do-not-merge-high-rate60-paired`. Pre-evaluation recipe
commit `d6408a2e59623c7ba9f0bd07e83bce23401e003f`, recipe source SHA256
`5f4bb5cefd59492f34d45e7b60e24fa00c0bd6b8950e1be71bfb6ab09b555423`.
HDL additive test-only commit `50880a4a57c8105c91097651a2dae8ea3ff8d366`, based on
`529dc8e8d33afc237c7b26f8969ec32fa97cdbdd`; exactly two new bench/include files.
No runtime RTL changed. Completed30 tree and its evidence remain untouched.

Prepared bundle: `build/native60-budget-prelaunch-v1`.
Bundle SHA256: `45e61eec6c2f40916af9f767631ca8281cef338bab06674732bcc5ee6af7ca1a`.
87-source signature: `d85c9db9e6f7d84217dc17b0d923f5ddcd9a37b5ecd1d3033a8f50a3244bd897`.
The bundle contains all69 unchanged numerical files, their original manifest,
the predeclared budget, and87 source snapshots. Its158 file receipts plus
`bundle.json` give159 files total. Each source receipt is tied to the actual
snapshot file hash, not merely a self-consistent source-signature dictionary.

Source closure is the original76 numerical-cohort sources, four additional
immutable files (common AXI/memory RTL, injection mux and unchanged public AXI
bench helper), and seven additive recipe/helper/test/CLI/doc/bench files.
All14 compiled native runtime sources are immutable, checked against original
cohort or literal original SHA pins. Local Python imports, including executing
package initializers, are recorded and checked inside the same closure.

The original numerical cohort remains
`build/high-rate60-offline-v2/cohort`, manifest SHA
`6de2f3645459f8649d8fee127e479991fb1cc55b75001a37c763223e716b4dfa`.
No source, waveform, kernel, native tuple, packet or other golden was regenerated
or overwritten for this probe.

## Intended measurement gates (not yet observed)

The independently readable state-to-budget derivation is in
`docs/starlink-native60-service-recipe-before-evaluation-20260910.md`.
It includes capture bridge transfer, sample-energy pass, all257 raw lags,
pipeline/flush/final/slide work, per-tuple DSP reducer backpressure and result
publication:78,360 derived cycles,84,000 publication/full-drain ceiling.
Two complete public packet reads,32-cycle retention,24-cycle release settle and
140 transactions each bounded24 cycles give87,416 <=88,000 post-capture cycles.
This assumes one healthy configured job, a free result store,100MHz control and
a dedicated bounded AXI master. It is not a measured Zynq service estimate.

The source starts low at time0; startup2.1ns precedes the first half-period.
First posedge10,433,333fs; first negedge18,766,666fs; each half-period8,333,333fs
and rising cadence16,666,666fs after simulator quantization. The bench asserts
these actual edge times within1fs and verifies every control period. Final
edge counts are independently reconciled to control-cycle coordinates.
`RATE_MSPS=60` is not substituted for an actual source-clock witness.

Exactly16,423 original CI16 samples, indexes/timestamps
`[34359735211,34359751634)`, are offered with uninterrupted strobe. No tail is
added. Command trigger34359738560; real sample-domain handshake must be in
closed[34359738560,34359738720], with signed lead[1535,1695] and <=256 control
cycles. Native center34359740384, capture[34359740256,34359740776),264 taps.
Public identity/rate/geometry/caps and coefficient generation/Eh are read back.
Native packet request60000520/generation60000001; visit60000052 remains external
fixture context, not a packet field. This is a static known-center experiment.

Every original source beat and every520 captured sample is compared and logged;
all257 raw tuples, exact96-bit powers, saturation counts, signed9 lag payloads,
241 qualification flags and both26-word public packet reads are compared.
The signed32 frozen lag memory must sign-extend correctly to its9-bit wire;
saturation memory's unused high3 bits must be known zero. Each stalled tuple
must hold its entire467-bit payload until acceptance and wait no more than16
cycles. All257 hold lengths are logged separately and checked by the parser.

The241st qualified tuple (lag120) may publish before the final eight raw lags
121..128. Publication, packet release and full257 drain/idle have separate
receipts/bounds; packet publication/release alone cannot end the experiment.
Idle requires correlator, DSP reducer, bridge state/descriptor/sample/start,
capture and raw/reduced valid paths to be idle. Source valid/enable stop after
the exact finite source, but the source clock continues while compute/CDC finish.
Configured post-source-off compute is observed separately from coefficient prep.
After source-off AND release AND all257 drain/idle, observe256 further control
cycles with no work, command, capture, tuple, IRQ or result. All configured
health/protocol checks fail on X/Z rather than silently skipping an unknown flag.

## Offline tests and retained attempts

From the worktree root, the exact final scope was:

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest -q \
 tests/test_starlink_native60_budget.py \
 tests/test_starlink_high_rate60_paired.py \
 tests/test_starlink_high_rate60_support.py \
 tests/test_starlink_high_rate_paired.py \
 --basetemp=build/native60-prep-tests-v2 \
 --junitxml=build/native60-prep-tests-v2.xml
```

Use a fresh explicit basetemp for independent repeats. Final log/XML and raw
fixtures are retained under `build/native60-prep-tests-v2*`; original handle56053
closed0. Earlier216-test attempt PASS3.61s, handle68640 closed0, retained under
`build/native60-prep-tests-v1*`. Initial lint complaints were formatting/type
comparison style/executable mode, not RTL failures. Final Ruff and diff checks
PASS. The first invalid apply-patch submission created no file; it was corrected
before any test. Neither attempt measured native60 service.

Mutation coverage includes every recipe field, bool/int/float aliases, source
packing/length/phase/clock/ABI controls, signed-lag/saturation padding, full-drain
versus early publication, per-tuple hold/stability, unknown health, missing or
duplicate receipts, mixed-case Fatal/Error/Warning, all26 packet words, complete
source/capture/raw/hold traces, source/import closure and independent bundle pin.
Stubbed compiler/service failures and timeout/integrity failures preserve original
errors and after-receipts; they never invoke real native service. Parser-only
healthy specimens carry `PARSER_ONLY.json` and no runner/terminal success receipt.
Content verification alone cannot establish simulator execution provenance.

Final frozen-CLI compile-only receipt: `build/native60-budget-compile-only-v1`.
Compile exit0, simulation exit null, mode compile-only, source and69-fixture
before/after equality, terminal `NATIVE60_COMPILE_ONLY`. The retained compile
log is exactly0 bytes on this attempt; compile exit0 alone is not a warning-free
claim. Runner always preserves diagnostic bytes and warning count. Host `gauss`,
Linux7.0.0-30 x86_64/glibc2.43, Python3.11.16; environment, compiler/vvp binary
hashes and complete command are retained. No hardware timing claim follows.

## Separate launch admission required

The frozen CLI defaults to compile-only. A future parent-authorized native-only
launch must use the exact external bundle SHA above, a new absent output path,
and explicit `--authorize-native-service`; no automatic retries or source/tail
extensions. The runner copies/freeze-checks all inputs before compile, retains
logs/status on failure, verifies source/fixture hashes after success OR failure,
and emits a success terminal only after complete numerical/lifecycle verification.
No service launch was authorized or performed during this preparation. Public
bank60 admission, a paired60 PSMA/PIL1 composition, causal handoff, live dwell
latency, physical timing and RF accuracy remain unqualified.
