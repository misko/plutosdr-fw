# Offered-summary physical result: timing FAIL

The source-matched actual FFT evaluation passed, and synthesis and diagnostic
routing completed, but the routed design does **not** meet timing. This package
does not qualify CDC, board clocks, external I/O, continuous acquisition, or the
full receiver. No RTL, constraints, or vendor run was changed by this publication.

## Frozen authority and original processes

- Firmware preparation: unbound `0f2714d6097086019b7c106eebb02e805ba0f62d`,
  bound `f372dfa856ff8a47416653a97563fff424a6e070`.
- Prepared 133-file inventory SHA-256:
  `1760f6d51c2438bd22ff12dfeccb18aa83a528b54ac0b71992efa27c32160a2b`.
- Original actual owner `84113`: exit 0, 59.0914 seconds, seven contexts,
  77,953 CSV rows. All prior complete results match the accepted control after
  removing only the new `offer_summary` field. Its manifest is
  `b5d112562b7db31164dc4a6ff92404de8e7d7d5d96b1c1b23e1a7dbac9d2c368`.
- Original synthesis owner `98534`: exit 0, 185.7805 seconds, source/copied-source
  checks 0, no timeout. Original route owner `26806`: exit 0, 64.7586 seconds,
  no timeout. Root exclusively owned both vendor processes; neither was retried.
- Own bound offline suite `30459`: 77 PASS in 1.21 seconds. Root independently
  repeated 77 PASS in 1.20 seconds (`72340`), with all 24 source pins unchanged.
  Earlier mock-only attempts remain included: 45 PASS/3 FAIL (bad mock kernel
  path), then 59 PASS, then 60 PASS. These are not vendor executions.

The exact previous helper/Tcl inverses, source-specific actual admission checks,
and settings are described in `starlink-retained-summary-physical-binding-20260910.md`.
The frozen recipe uses 16 runtime files, R/B/O/L=1, all three retained options=1,
one FFT, 100/175 MHz OOC clocks, xc7z010clg400-1, Vivado 2022.2, two threads,
AreaOptimized_high, threshold 4, and unchanged routing directives. No timing
exception was added.

## Measured result

| Metric | Synthesis | Routed |
|---|---:|---:|
| LUT | 2,248 | 2,344 |
| FF | 4,759 | 4,766 |
| DSP | 21 | 21 |
| RAMB18 | 15 | 15 |

Synthesis changes only +6 LUT against the previous retained-control synthesis;
FF, DSP, and RAM counts are unchanged. Routing reports 66 control sets and all
7,253 nets fully routed, with zero routing errors.

Routed setup WNS is **−2.504 ns**, TNS **−829.822 ns**, with **679 failing
endpoints out of 11,060**. Hold slack is +0.049 ns with zero failing endpoints;
pulse-width slack is +1.830 ns with zero failures.

| Clock pair | Setup slack, ns | Hold slack, ns |
|---|---:|---:|
| 100 → 100 | +2.512 | +0.100 |
| 100 → 175 | −0.546 | +0.162 |
| 175 → 100 | −1.236 | +0.074 |
| 175 → 175 | −2.504 | +0.049 |

The first reported path is `epoch_barrier/fast_release_reg` to
`cutover/owner_inverse_reg`, with 10 LUT levels and 8.163 ns data delay. This
records the mapped report, not a source-level fix or proof that another path
has been eliminated.

CDC remains **5 critical / 139 warning / 3 informational** findings. There are
114 unconstrained input and 124 unconstrained output ports. The independent,
rounded OOC primary clocks do not establish a board-derived 175 MHz clock.
Internal timing coverage is not external-interface or CDC signoff.

Synthesis DCP SHA-256:
`2348ac8205738a178e11d3f51c8d5b46199ab8548a57573bae0edd785f3f5eb5`.
Routed DCP SHA-256:
`83d268fff699dae1ca3fca8bd1debddd04562590a284f982e05844bdb1059d38`.
Both original checkpoints and all prepared sources were unchanged by routing
and packaging. All reports, constraints, generated IP, commands, journals,
owner receipts, and audit sources are retained.

## Failures retained, not reclassified

Root's first route collector (`audit-first.py`, tool chunk `197c83`, exit 1)
rejected two identical `Slice Registers` totals of 4,766. The report includes
that total in both Slice Logic and Slice Logic Distribution. The corrected
collector requires exactly two equal register totals and exactly one occurrence
of each other selected label. Both collectors and the failure JSON are archived;
no measured report or timing predicate changed.

Own first packaging process `70376` exited 1 with `Errno 122: Disk quota
exceeded` while writing a new archive in `/tmp`. Its source and traceback are
archived. The incomplete archive remains preserved in recovery with SHA-256
`e9dacce05967cba33023c0f2d76626e29ba86403a9ad199b2e44af54696db1c6`;
it is not a valid replacement for the complete archive. The complete package
was built outside `/tmp` by original `29459`, exit 0. No raw input was removed.

## Portable evidence and publication scope

`reports/experiments/20260910-retained-summary-physical-evidence.tgz` contains
**7,598 unique safe regular files**, **30,913,549 bytes**, SHA-256
`559d2fe553db424fee5b8748008799479bab1d2855e57061734d2f63943f4303`.
The adjacent JSON records every member's original path, byte count, and hash.
All original regular files were rehashed after packaging and matched. The 77
symlink aliases are recorded separately and were neither followed nor included
as archive members. No duplicate actual WDB is included: selected actual owner,
source-manifest, generated-IP, CSV, result, and raw-log authority is retained.

The archive was copied into a dedicated detached recovery worktree based on
`f372dfa856ff8a47416653a97563fff424a6e070`, without initializing submodules.
The original `/tmp` worktree's committed head remains that exact pin; the HDL
gitlink remains `b26f56dd32106c8e91290d075255ac4a6b9ff72d`. The publication
commit adds only this report, archive, inventory, and packaging verifier.

Verify all committed Git blobs, including every archived member, with:

```sh
env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH -u PYTHONOPTIMIZE \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
  tools/archive_retained_summary_physical.py --verify-git HEAD
```

Only the existing `codex/starlink-rx-only-do-not-merge-bank-arithmetic` firmware
remote branch is in publication scope. No primary/main, HDL, radio, or runtime
promotion is implied by a successful Git verification or push.
