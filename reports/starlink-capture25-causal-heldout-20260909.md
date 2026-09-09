# Earlier-pilot frequency assistance on held-out capture25 windows

Status: completed offline numerical study; no radio access, fine timing lock,
online latency qualification, or native 25 MS/s hardware claim.

The predeclared plan used only the already-retained blind pilot observations
from 36.00–36.32 s to choose a provisional +285941.79442491336 Hz correction.
Two of its three probes formed a supported <=10 kHz complete-link cluster;
the third, approximately +512.585 kHz, remains an unresolved minority alias.
Multiple supported clusters would abstain. No later PSS or GLRT result chose
the correction, and no same-window saved GLRT was used in these later tests.

| Held-out source interval | Baseline combined robust z | Prior-assisted combined robust z |
| --- | --- | --- |
| 1.00–1.32 s | 4.9699, fail | Not attempted: earlier negative prior abstained |
| 1.50–1.82 s | 5.1829, fail | Not attempted: earlier negative prior abstained |
| 36.50–36.82 s | 4.9809, fail | 8.4744, pass |
| 37.00–37.32 s | 4.7214, fail | 8.0766, pass |

All six variants passed numerical qualification and all six combined scrambled
controls failed the detection gates. All six assisted individual positive maps
passed; all six negative baseline maps failed. One individual baseline map in
the first positive window passed, although its combined gate failed. Retain
that distinction rather than calling every baseline map negative.

Both assisted combined results selected the interior -3.125 ppm hypothesis,
not a fitted sample-clock slope or a fine timing lock. The episodes were chosen
using historical activity evidence; positive/negative labels are not newly
independent RF ground truth. No new held-out pilot/GLRT validation ran here.
The older frozen study already includes a matched-CFO negative control; this
new study does not replace it or establish a false-alarm rate.

Real filter halos and source gaps were checked. The first/second later positive
input envelopes begin 0.1796/0.6796 seconds after the prior's complete input
envelope. That proves sample ordering, not online command deadlines. Prior
GLRT processing latency was not measured. The 15.92/15.72/29.56/29.46-second
case processing durations are offline C-model timings, not a radio throughput
measurement. Total study execution was 90.715 seconds, exit 0.

## Immutable evidence

Directory: `hdl/library/starlink_pss_acquisition/build/capture25-causal-heldout-v1`.
Its per-case reports retain raw input provenance, output hashes, individual
maps, combined hypotheses, numerical evidence and scrambled controls.

- Frozen plan SHA256:
  `91d2b6bf04478c42232cf63d53e6a6c842f5f19ca7dfa3fa62111bd49e6c8ad7`
- Completed study-result SHA256:
  `bbfd2284f7684f6b9d21de7c76835fcbaa79d0213b6ca6a446ba7a2bd238f73c`
- New runner SHA256:
  `37de4fa769b903dbf5f18e42479f0368d5d8e714bf8c7e156571365c719d46d8`
- New test SHA256:
  `72e58ee7e4030856f5bb46e6f3b788b3e817ddce0a88611b1fb7fcd4cf686d84`

The original capture, frozen conditioner/replay/coefficient files, and earlier
reports were not modified. The new private replay adapter changes only its
explicit window table. Full-plan regeneration checks all source/prior pins;
future edits require a new predeclared study rather than overwriting this one.

Next algorithm gates remain actual prior-estimation/command latency, frequency
coverage and alias policy, automatic coarse-to-fine handoff, held-out fine
timing and independent live paired GLRT/PSS evidence.
