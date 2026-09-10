# Pipelined coarse processing and native fine handoff: current boundaries

This review accompanies the second isolated parallel studies. No radio was
accessed, configured, transmitted from or flashed. No PPU source was changed.
The goal remains source15/30/60 fine search with independent2.5MS/s evidence,
followed by the eight-target120ms/300s scanner, not a substitute detector.

## Bank-owned prototype review

The FFT-island worktree now contains an experimental three-bank slice: actual
slow-to-fast source bank, private fast-domain product bank, and fast-to-slow
inverse-output bank. Checked forward results feed the product path directly;
inverse admission waits for forward validation and complete product ownership.
The original FFT, input checker, result checker and exact product arithmetic
remain. This is not integrated into the receiver or physically qualified.

Root review identified a potential forward handshake mismatch: the joiner could
accept a qualified held-final word while product-bank readiness prevented guard
retirement. The agent added matching acceptance gating. A nonfinal readiness
loss alone is insufficient as a regression witness because the original guard
can already suppress that beat through its slot fault. The stronger requested
test holds the qualified final return with an empty/ready join pipeline and
unavailable product bank, then requires exact recovery after readiness returns.
Mutating away the extra gate must fail acceptance equality on that witness.

A second requested invariant covers capture of N+1 while N computes: after
input completion, the N input epoch must accept no further core word even if
the source bank presents the complete next block. Original sample identities
must travel with the bank; elapsed processing time is never a timestamp offset.

The first200MHz run is retained as failed evidence in the agent worktree under
`hdl/library/starlink_pss_acquisition/build/fft-bank-owned-200-v1/`. It failed
at epoch20 with `unqualified guard commit` during the postcommit fault test
(00:38:21UTC). Review confirmed that its bench incorrectly forbade the healthy
inverse commit preceding a deliberately later fault. The test correction permits
that commit only in the late-fault scenario; every commit still requires all512
input/output words, exactly one status/frame event, and the original final fence.
The failed run is not counted as passing evidence.

Fresh `fft-bank-owned-{200,175,150}-v3` actual-core runs completed successfully
at00:49:20–00:49:25UTC. Root inspected all three terminal simulation logs and
the bench. Each run verifies44 healthy blocks,22528 healthy inverse words plus
130 exact provisional words from a deliberately faulted block, four reset/purge
cases, ten fault cases, and37 capture/compute overlaps. The accepted prefix is
not retractable across clock domains: no completed block or queued next job
escapes quarantine. Held-final readiness and closed-input-prefetch witnesses
pass; the separate join-gate mutation is rejected by its acceptance witness.

| Simulated fast clock | Maximum nominal forward interval | Maximum tested stalled interval | Compared with29.8us coarse arrival |
| --- | --- | --- | --- |
| 200MHz | 4668clocks /23.340us | 4986clocks /24.930us | Both tested profiles fit |
| 175MHz | 4540clocks /25.943us | 4820clocks /27.543us | Both tested profiles fit |
| 150MHz | 4410clocks /29.400us | 4650clocks /31.000us | Repeated stalls exceed arrival budget |

These are complete bank-slice admission intervals including the real serialized
100MHz output read/ACK, not a sustained continuous-source/scoring qualification
or a physical clock result. Repeated independent fixture blocks do not exercise
the overlap scheduler, energy cache, score backlog or source-rate fine capture.
The100MHz costs explain why simply scaling200MHz cycle counts is incorrect.

The complete three-bank slice's synthesis-v2 inventory is1834LUT,4375FF,
21DSP and7.5BRAM tiles, with no black boxes. This includes actual generated FFT,
kernel/product and all three banks; it excludes scheduler, energy, normalization,
maps, native fine and pilot/DMA. No receiver area saving can be established by
subtracting these synthesis numbers from a differently optimized routed design.
Its resource-probe constraints leave114 inputs and124 outputs without external
delays. Neither that inventory nor a diagnostic isolated route qualifies CDC,
board I/O, a physical receiver clock or deployment.

Root's subsequent diagnostic route of the frozen synthesis checkpoint finds
same-domain175MHz WNS-2.557ns along product-bank metadata -> input/result guard
validity -> kernel-memory enable. See
`experiments/20260910-bank-owned-route-diagnostic.md` for complete reports and
limitations. The internal control path still needs refactoring; no full receiver
build is justified from the slice's simulation service margin alone.

## Current PPU transport contract rechecked

PPU main remains `4bc2ca6a50dd8dd3c925522acfff5466385fbfd5`. The six suites
below ran again with its existing virtual environment:848 tests passed in11.38s.

```
.venv/bin/python -m pytest -q --tb=short \
  tests/test_paired_capture.py tests/test_fine_schedule.py \
  tests/test_source_support.py tests/test_pss_control.py \
  tests/test_pss_stop.py tests/test_pss_stop_control.py
```

These are public-client tests over simulated native IIO bindings. Their source
counters are fixture coordinates, not measured wall-clock rates. They exercise
concurrent pilot/map/fine recording, exact raw-packet/Q32.32 schedule accounting,
source-support joins, boundary-stop/drain reconciliation, incomplete/error
retention and joined cleanup. They prove no DMA, Ethernet, calibration or RF
behavior and do not supply CFO seeds or frame-lock evidence.

Read source identities:

| Module | SHA256 |
| --- | --- |
| paired_capture.py | `00f084bdc288bb78868a0a626d02a5aad959233088d85fc9363f9152c0c1b2da` |
| fine_schedule.py | `37b9461844fcc92d24c2908a8e7846544bd564672dc5ee7ceb9a957d58deb0fa` |
| source_support.py | `8d0195d4c0dcc6ef37a390147bf5f3cba775f9ef6f16d369a294ab58f24f2826` |
| pss_control.py | `495267dc0ac332bdcb0c2858f2e6dbef0c45d0a2074f6cf49aa718da2db204ff` |
| pss_stop.py | `132ebe5b8548e321f3186151a9ad7723025bd7639fc0a75c2f5a930efa391ed9` |
| pss_stop_control.py | `3c259ab80b950365421ea6c4c364d722102e44554125dca782308effc1c23e8f` |

The unrelated four-file working diff remains unchanged at SHA256
`eb87e8049367ba2a2f8fccf89123b6c2bb58518175e79dba3f41cddabd07848d`.

## Important remaining handoff work

The current paired recorder explicitly admits only the shared15 boundary-stop
profile. It records a two-second pilot envelope and requires at least one
second of finite fine-anchor separation, with count divisible by16. Its fine
phase/cadence is caller-supplied diagnostic data relative to the first pilot
center, not automatic coarse acquisition. Fine manifests also deliberately
reject30/60 profiles. These restrictions are valid for fixed-frequency canary
qualification and must not be described as the120ms hopping implementation.

Future live handoff needs a separately qualified visit-tagged timing/CFO policy,
fresh source-counter and uncertainty/lead bounds, exact full native capture
support before visit end, coefficient identity, expiry and terminal receipts.
The old live-fine qualification script and its three-map trigger do not supply
that policy. No historical or later GLRT winner may silently seed an allegedly
independent comparison. A later answer may retain accurate source coordinates,
but lateness can still invalidate a future capture deadline.

The completed direct feeder/history alternative passes72543 accepted inputs and
71047 exact results, but its corrected isolated route fails setup(-3.161ns) and
hold(-.742ns). Its2354LUT/2814FF/18DSP/4BRAM inventory omits normalization; the
earlier direct-vs-FFT numerical incompatibility remains. It is not selected.

The completed narrow study retains two causal CFO aliases, and both pass later
one-map exploratory PSS gates. The stronger minority alias is closer to blind
GLRT, but no predeclared rule uniquely identifies it. Two sequential85.333ms
maps already require170.667ms at the existing single-hypothesis service rate;
the production three-map rule requires256ms for one branch. Neither fits a
120ms visit by assertion. The next scanner policy must explicitly qualify
shorter integration or lawful cross-visit evidence and pay for alias multiplicity.
One-map exploratory thresholds are not a production lock or an established
equal-false-alarm policy. All alternative promotion gates remain.
