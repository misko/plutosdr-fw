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

The first200MHz run is retained as provisional evidence in the agent worktree
under `hdl/library/starlink_pss_acquisition/build/fft-bank-owned-200-v1/`.
Observed forward-admission intervals are4668clocks=23.34us, but the complete
fault suite and updated witness are still pending at this review. This is not
a sustained source15 qualification, final service bound or placed clock result.
The actual serialized100MHz final read/ACK must be charged when measuring
150/175MHz; scaling every cycle by the new fast clock would be incorrect.

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

The direct alternative is independently adding actual history/source-acceptance
logic and its resource cost. The narrow alternative is independently testing
all earlier retained CFO aliases against equal-support later PSS evidence.
One-map exploratory thresholds are not the production three-map lock rule or
an established equal-false-alarm policy. All alternative promotion gates remain.
