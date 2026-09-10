# Healthy30-upper bank/native/PIL1 prelaunch gate

Implementation and offline preparation are complete. **No actual FFT/paired
simulation has been launched.** This is an additive test gate, not runtime,
driver, receiver, physical, RF, causal-handoff or production-map qualification.

The isolated branch is `codex/starlink-rx-only-do-not-merge-high-rate-paired`.
Base FW is `6d2252552a0125885509216a89d2d465098b3976`; base HDL is
`e2a8773bb8cd24540b0b8d2ab96a7724667ff4ba` (accepted StageA).
New HDL commit is `446a8617adbabcce5122705e528dc997ff06d263`:
eight additive test/include/runner files, **zero runtime changes**. Old15
helpers, bench, goldens, public defaults and StageA strict inverse are unchanged.
All runtime inputs are byte-compared with the exact StageA HDL commit at freeze.

## Frozen review inputs

Bundle: `build/high-rate-harness-prelaunch-v1` (95 source files;358 inventoried
files plus `bundle.json`). The original71-source cohort is retained separately
from the current StageA/test source closure, not silently updated in place.

- Simulation source signature:
  `413f9cd065da934d258750b30075d5e9c75ff16efd9484a51222ca0b3043cb31`.
- Bundle receipt SHA256:
  `2d410bc8a7984425751a527725e8f43c8406596b23f610e904199d1524863da5`.
- New vectors receipt SHA256:
  `0ff5b89f9a4d4cba26f9c546bd8507f2568a7445f490e611bc7b5ee2f42e0980`.
- Continuation CI16 SHA256:
  `6aab7ee741d28dd65d74e852168586ce9fc74d25d1edc1097a682e1d57b90ebb`.
- Original51 cohort receipt SHA256 remains
  `ba3046d56a6eb1cf2792070cf63f8d7ffb44958f0ef9f4999907b2b2a49bdb4d`.

`tools/prepare_starlink_high_rate_harness.py` verifies the exact original51,
adds only12 fixture files (63 total), rejects overwrite, ties source signatures
to each actual frozen-file hash, and freezes the original budget evidence.
The standalone packaging utility/report are packaging metadata, not changes to
the reviewed95-file simulation source signature.

## Exact source and public contract

The actual top is `hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_30_bank_native_paired.sv`.
Its public wrapper parameters are source30, pilot1, shared1, realtime1,
bank1, STOP1. Public identities must be PSMA1.7/caps0x7ff,
DDC0x000f0203/delay7/Eh1073744004; native1.3/rate30/geometry0x0bca0884/
caps0x1d,132 taps; PIL1 declares30MHz source,2.5MHz output,12 raw-index step,
upper edge,269 canonical delay and538 canonical history. Only actual map and
control child geometry is overridden to447x2, preserving15-bit outer indices.
No rate guard or bank selector is bypassed by a child defparam.

Let K=8589934576 and P=K−768=8589933808. Half-open coordinates:

| Region | Raw support | Contract |
|---|---|---|
| Disabled prime | [17179867607,17179867609) | two real CDC beats, values1/2, zero canonical outputs |
| Original cohort | [17179867609,17179875814) |8205 immutable CI16 Q16:I16 samples |
| Preroll | first1549 original raw |768 canonical outputs [P,K), then explicit drained configuration pause |
| Selected map FFT support | [17179869145,17179871076) |959 canonical samples [K,K+959),894 admitted scores |
| Native capture | [17179870128,17179870388) |260 ORIGINAL raw samples,132-tap template,center17179870192 |
|512 selected pilot support | [17179867617,17179874840) |newest canonical8589934350 through8589937416 |
| Frozen continuation | [17179875814,17179879910) |4096 source-only beats; xorshift13/17/5 seed0x30b17552 |

The real conditioner issues on odd newest raw index after15 contiguous inputs:
canonical=(newest−7)/2, center=2*canonical, raw support center±7 inclusive.
First post-preroll raw is2K+6;2K+7 emits K. The native command uses public
telemetry and staged command words with request0x30000520, generation0x30000001,
center/timestamp17179870192. Actual scheduler admission must occur by raw
17179869408 with lead>=128; actual lead is checked against capture_start−index−1.
The center is **known statically**, not derived causally from the later map.

Coarse arithmetic uses the independently conditioned30 kernel, not the15
template. Its original kernel SHA256 is
`23996c80f79f112ea7739049050ad8cb2c85a8067792889bf2a774886ac2ce24`.
All51 original goldens, including all7 blocks/3584 words per transform stage,
3129 scores and every normalized numerator/denominator, remain unchanged.
Native Eh=1073746351; all129 raw lags−64..64 and121 qualified lags−60..60
are checked, including full signed48-bit wire tuples, index/timestamp, request,
generation, Ex/Eh, saturation and independently squared96-bit power.
The26-word public packet is read twice and explicitly released.

## Budget established before tail freezing

At100MHz, the declared healthy single-job bound is:
capture bridge3*260+64=844; sample energy260+16=276;
129*(132+16 pipeline/control+16 reducer wait)=21156; publication128.
Derived22404 cycles is covered by a24000-cycle publication deadline.
At most140 native AXI transactions of<=24 cycles plus640 cycles margin gives
28000 post-capture cycles through two packet reads and release. The public
masters are independent bench ports, not a measured ARM/interconnect driver.
This is a bounded healthy/free-result-store test contract, not a proof under
unbounded reducer or bus backpressure.

After the last capture sample,5426 original raw samples plus4096 tail provide
31740 engine cycles at100/30MHz:3740 cycles headroom above28000. The length
was selected before any paired evaluation and is never extended on failure.
The tail is Q16:I16 deterministic nonperiodic low-amplitude data, not a new
PSS or FFT fixture. Conditioner-disabled and capture-complete are asserted
before its first beat. Source enable is removed only after all12303 prime+
original+tail beats; the independent CDC ledger must drain every one.

Before generating the tail, actual native-only probes passed on original8205
raw samples and on an explicit3179-sample prefix. Both turn source enable off
after capture while the real correlator is busy: neither aborts post-capture
compute. They observed19911 publication cycles and20700 through public release,
max AXI7. The original8205 case continues compute2622 clocks after source-off;
the3179 case continues19375 clocks. This is not an assumption that disabling
the native source flushes an already captured engine.

## Lifecycle and every-prefix checks

The harness primes the real CDC while DDC is disabled, checks empty STOP
ticket1, retains PIL1 through1549-raw preroll, then enables coarse without
flushing pilot history. Ticket2 is requested after200 observed scores.
Exactly894 scores enter one447-word map. At most1341 visible scores are
permitted as a predeclared one-block provisional-tail bound; every visible
score/index/phase remains numerically checked and no tail enters the map.
Every observed forward input/output, product, inverse input/output and BFP
exponent is checked against its original block identity on its own clock.
No claim is made that all7 stored blocks run or drain.

PIL1 automatically closes at512 admitted outputs. The conditioner can then
disable while native work continues. An independent input/history/five-edge
issue ledger predicts the enabled canonical prefix and cancelled unpromised
pipeline. It does not borrow the DUT's filter_issue/history/emitted count.
Every visible canonical and pilot mixed/halfband/final prefix remains exact.
After coarse STOP, source/PIL1/native lifetimes are independent. The complete
map is retained through full public map read, native publication/two packet
reads/native release; only then is the map publicly released. Source continues.
Native-capture/actual175-clock FFT-consumption overlap, native compute while
coarse+pilot active, compute after STOP, and>=32 fast bank-quiescent clocks
must all be positive witnesses. No stale score/inverse is allowed after local
teardown. The shared reset is never used to manufacture healthy STOP cleanup.

New health assertions require known zero with case inequality; X/Z are not
silently accepted. Gap, saturation, malformed identity, lost strobe, exhausted
source, missing candidate/result, any wrong word and any deadline failure end
the healthy test as failure. This gate supplies no343/negative-epoch or recovery
qualification. No hierarchy force is used in the actual harness or numeric
module probes. The unknown-health test directly drives a copied assertion's
observation boundary and is explicitly not live hardware-fault evidence.

## Offline evidence

Final `build/high-rate-harness-regression-v1/pytest.log`: **490 PASS,22.81s**,
exit0.340 StageA/legacy/cohort tests,59 unchanged old15 paired-helper cases,
91 new harness/budget cases. Strict whole-body StageA inverse and mutation
guards remain enforced. Ruff passes. Host:gauss,x86_64,Intel Core Ultra9 285K;
these runtimes do not describe Zynq/ARM or actual FFT simulation capacity.

The actual **non-FFT module** probe (real native30+CDC+x2DDC+PIL1, no PSMA or
bank instantiated) matched12303 raw/CDC beats,7250 enabledraw,3618 canonical,
3617 accepted/mixed pilot,1808 halfband,602 all pilot outputs (90 unsupported,
512 selected),2048 binary bytes,260 native captures/all129 tuples/two packet
reads. It also observed the same19911/20700-cycle native completion. These
prefix counts validate the ledger, not a promise that the full paired run has
identical phase-dependent counts. The full paired top only **elaborated**
against an inert fail-fast FFT interface; it did not execute a transform.
One existing elaboration warning is the unchanged result-guard dangling
idle_mailbox_fault_now input; it is not silently fixed or physical signoff.

Native raw tuples are exposed as nine-field lines in each actual probe's
`native30_actual_raw_tuples.txt`, and all52 public packet words are logged.
Tests independently compare those logs to the original JSON rows. Source
pre/post and fixture pre/post receipts accompany final probes. All simulator
FAIL/FATAL/ERROR evidence is rejected by the healthy postprocessor, regardless
of a PASS line. Parser-only specimens are explicitly labeled and test every
missing/duplicate receipt, source/support/clock/count/deadline/coordinate,
native tuple/packet and pilot log/binary/snapshot mutation.

The runner is new and healthy30/175/447x2-only; no alternate CLI profile.
It sets maxThreads2, refuses overwrite, copies the reviewed bundle, sanitizes
only independent Python subprocess environments, and checks frozen integrity
after success or error while preserving the original Tcl error. Successful
terminal receipt is withheld if post-integrity fails. Stubbed create_project/
launch tests validate these paths without calling Vivado or producing FFT
evidence. Source-list/signature mismatch and self-consistent altered entry
script are rejected before project creation.

Retained attempts:offline-v1 missing pytest parent (2PASS/21 setup errors);
v2 two compile failures (invalid mixed wire initializer declaration and missing
AXI-lite source),21PASS;v3 fixed compilation/real-module23PASS;v4 parser/health
coverage78PASS;v5 freeze/runner/environment coverage91PASS; final490PASS.
No RTL/golden was changed to resolve a test failure. The original51 snapshot
producer rederived all goldens unchanged; see `original51-rederive.log`.

Exact490-file invocation is recorded in the parent handoff and uses:
`test_psma17_contract`, `test_psma_boundary_stop`, `test_stop_health_integration`,
`test_health_stop_summary`, `test_shared_xfft_integration`, `test_starlink_high_rate_paired`,
`test_ddc`, `test_pilot_ddc`, `test_starlink_pss_tracker_coefficients`,
`test_starlink_bank_native_paired`, `test_starlink_high_rate_harness`,
`test_starlink_native30_budget`; create a new basetemp parent and retain logs.

## Proposed next invocation — NOT EXECUTED

After separate parent review/authorization, from this HDL acquisition directory:

```sh
vivado -mode batch -source simulate_high_rate_bank_native_paired.tcl -tclargs \
  /tmp/starlink-bank-route.I50MDJ/main-high-rate30-bank175-447-v1 \
  /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired/build/high-rate-harness-prelaunch-v1 \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python
```

That run's1ms watchdog and bounded input do not qualify production duration,
high-rate receiver rollout, causally generated native commands, native timing
accuracy, RF agreement, driver STOP handling, true bus latency, MMCM/physical
closure,60MS/s or lower-edge operation. Those remain separate gates.
