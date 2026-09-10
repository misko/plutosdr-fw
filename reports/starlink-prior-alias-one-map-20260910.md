# Prior aliases tested against equal-support canonical PSS

Both earlier pilot CFO aliases remain viable after one exact 64-frame PSS map.
The previously retained minority alias produces substantially stronger PSS
evidence and closer timing agreement with blind GLRT, but the primary alias
also passes the exploratory scalar thresholds. The result is **competing alias
candidates**, not resolved frequency identity or an authorized automatic handoff.
One map does not meet the production three-map integration rule.

This extends `starlink-narrow-coarse-feasibility-20260910.md`. No radio, PPU,
deployment, HDL change, full-receiver build, remote operation or merge occurred.

## Frozen inputs, hypotheses and interpretation

`tools/starlink_alias_pss_study.py` writes a plan before evaluation and validates
its source/IQ/prefix hashes again before running. It accepts no later PSS or GLRT
value when choosing CFO branches. Earlier 36.00/36.10/36.20 s blind pilot probes
contain only three candidates above the unchanged 0.025 prior margin gate:
+286139.20454545174, +285744.384304375 and +512585.3848550797 Hz. Their <=10 kHz
complete-link clusters freeze these branches:

| Branch | Applied offline canonical correction | Prior support |
| --- | --- | --- |
| Zero baseline | 0 Hz | Diagnostic uncorrected reference |
| Prior alias 0 | +285941.79442491336 Hz | Median of two earlier probes |
| Prior alias 1 | +512585.3848550797 Hz | Retained one-probe minority |

All prior candidate rows, clusters and minority status remain in the plan. The
earlier negative episode has no admitted aliases; its later negative windows
retain abstention and baseline only. Applying the positive episode's future
prior to those earlier negative windows would not be causal, so all three
branches instead also run on a separately seeded, known white-noise control.

Every PSS branch in a case receives identical original input support. It uses
the existing upper-edge 18-bit Q17, 512-point vendor BFP arithmetic, frozen
kernel, normalized eight-bit scores and 64-frame/one-sample-bin phase-map
reduction. No floating approximation, coefficient regeneration or RTL change
is substituted. Baseline and primary-alias score prefixes are checked against
their frozen earlier replay bytes: all six available prefixes match exactly.
All eleven branches have zero reported arithmetic overflow or derotation
saturation. This is the vendor arithmetic oracle, not executed FPGA protocol.

One-map candidate interpretation uses z>=6 and peak/median>=1.15. Applying those
existing numbers to **one** map is exploratory; it does not preserve production
qualification or prove the same false-alarm behavior. The predeclared alias
consistency rule requires exactly one passing prior branch and no passing
scrambled controls. Even that would only be consistency evidence, not RF truth.
Both real positive cases retain two passing branches. All production handoff
statuses remain `insufficient_integration` (one map available, three required).

## Measured one-map results

| Later source interval start | Zero baseline z | +285942 Hz z / ratio | +512585 Hz z / ratio | Alias result |
| --- | --- | --- | --- | --- |
| 1.00 s | 5.1711, fail | Prior abstained | Prior abstained | No prior aliases |
| 1.50 s | 4.1696, fail | Prior abstained | Prior abstained | No prior aliases |
| 36.50 s | 4.8681, fail | 9.7495 / 2.2471, pass | 34.8976 / 5.6667, pass | Competing candidates |
| 37.00 s | 4.2522, fail | 9.0750 / 2.1608, pass | 38.2993 / 6.1216, pass | Competing candidates |
| Known noise | 5.1936, fail | 4.2397 / 1.5366, fail | 4.8901 / 1.5918, fail | No alias candidate |

All eleven frame-scrambled controls fail the exploratory gate. One primary
control is close at z=5.9741; the threshold remains unchanged. These few
controls do not establish a false-alarm rate, particularly after adding alias
search trials. The noise fixture is one seed, not a sensitivity campaign.

Each case also runs independently blind GLRT without any PSS epoch/CFO or
applied prior correction. Five bounded 20 ms probes cover the same nominal
85.333 ms center interval, with offsets 0, 20, 40, 60 and 65.333 ms. The final
two overlap; these are not five independent replicate observations. Every
retained GLRT candidate and no-candidate result is saved.

- All ten positive probes exceed 0.025: margins 0.4157–0.5491.
- All ten historical negative probes remain below the gate: margins
  0.00403–0.01354, classified with unknown RF observability, not known absence.
- All five probes on the explicitly known-noise case remain below the gate:
  margins 0.00476–0.01071.
- Positive best CFOs switch between approximately +282–285 kHz and +509–512 kHz
  across adjacent probes. The narrow passband is not independently calibrated,
  and final GLRT CFOs can exceed the configured acquisition search domain.

## Timing evidence and native fine aperture

| Start | +285942 Hz PSS phase | +512585 Hz PSS phase | Blind GLRT phase range |
| --- | --- | --- | --- |
| 36.50 s | 398.8667 us | 400.4667 us | 400.3333–400.4667 us |
| 37.00 s | 400.8667 us | 401.4000 us | 401.2667–401.6667 us |

Phases are modulo the 750 Hz frame. The first case's primary/minority difference
is 1.6 us, equivalent to 96 original60 samples; the second is 0.5333 us, or
32 original60 samples. Those offsets matter to the current +/-2 us native fine
aperture. The minority phase is closer to blind pilot timing, but pilot timing
is not fine/RF truth, and their effective weighting within the common interval
differs. The primary is not rejected by the predeclared PSS scalar gates.
No post-hoc GLRT/PSS phase-tolerance rule selects a winning alias.

A proposed future handoff must retain both frequency-and-phase branches or
abstain. It needs known-origin fine timing, an alias rejection policy, period
and correction-age confidence, and observed command/visit deadlines. A stronger
coarse peak or 16.7 ns native sample spacing does not establish timing accuracy.

## Source support, compute and alias multiplicity

There are 1,280,000 nominal candidate-score centers: 85.333333 ms. Whole 512-word
BFP input blocks require 1,280,273 canonical samples. Including the preceding
25->15 centered FIR gives **85.35788 ms** of original source dependency for PSS.
The shared bounded read includes the real pilot halos too: 1,281,200 canonical
samples, with **85.41968 ms** of original25 dependency. All branches use that
same envelope, below the 120 ms offline exposure limit.

For the first positive case the shared original interval is
`[912498920, 914634412)` at 25 MS/s, or
`[36.4999568, 36.58537648)` seconds. The prior's conservative full source envelope
ends at 36.3202 s. The corresponding gap is 179.7568 ms; the second case's gap
is 679.7568 ms. The read begins 43.2 us before the nominal map center interval.
That is real continuous same-frequency history, not a tested hop/reset guard.
No zero padding or invented filter history is used.

Offline PSS calculation took 3.709–3.835 seconds **per branch** for this 85 ms
observation on the x86 host `gauss`; total experiment time was 43.494 seconds.
The 25 independent-search calls took 25.86–47.14 ms each, separately from Python
DDC filtering. No ARM, FPGA service-rate, command or transport capacity follows
from these host timings. The source envelope fitting 120 ms does not demonstrate
that any calculation or command fits a live 120 ms deadline.

Alias multiplicity must be paid for in any proposed implementation. Two full
85.333 ms PSS maps evaluated sequentially at the current 15 MS/s service rate
take at least **170.667 ms**, excluding filtering and command time. Processing
the same interval concurrently requires twice the coarse hypothesis throughput
and appropriate storage/control; the existing single 15 MS/s engine does not
supply that. The diagnostic zero baseline would be a third branch if retained
online. Buffering the canonical interval for replay alone needs about 5.12 MB
of CI16, far beyond available BRAM; it is not introduced here. A faster engine,
parallel resources, retained external memory or a different hypothesis schedule
requires implementation and full-design qualification.

All corrections here are offline CI16 rotations before canonical PSS oracles.
They are not deployed RF retunes, a hardware NCO, or a newly added CFO operation
in the fine tracker. The production three-map rule still needs 256 ms even for
one frequency branch. Neither the alias problem nor short-dwell lock policy is
solved by this experiment.

## Reproduction and retained artifacts

Run `tools/starlink_alias_pss_study.py plan` with `--evidence-root`, `--leo-root`
and a new `--output` directory, then `run --plan PATH/plan.json`, using the Leo
Python 3.13 environment shown in the preceding narrow study. Artifacts must be
inside the assigned firmware worktree. Output is never overwritten. Every
branch receipt, map and scrambled map is retained, along with all GLRT rows.
The temporary vendor model is under ignored `build/`; no IQ recordings or
vendor binaries are committed.

Evidence directory: `reports/prior-alias-one-map-20260910-v1/` (1,790,184 bytes).

- Plan SHA256:
  `817c9e759dc455af035e1fe3516d575ff51d92600c9168167c6b48ddf3328a9a`
- Result SHA256:
  `f88e4dc8a723e8095e0c21239083f5209b7a91f4ce3ab92b0abb37a98ef659f4`
- All eleven exact PSS branches and 25 blind GLRT probes completed. All six
  available frozen baseline/primary score prefixes were identical.
- Eleven new tests cover prior-only branching, minority retention, missing
  aliases, source halos, input identity, overlapping support, and preservation
  of unresolved/insufficient-integration outcomes. Together with the prior
  narrow/causal/DDC tests: **80 passed**. Ruff passes on both new Python files.

This is evidence for retaining and testing the minority branch. It is not
evidence that either branch has been uniquely identified, that native fine
timing is qualified, or that a two-alias live pipeline meets 120 ms.
