# Retained actual causal-frame preparation

Outcome: **251 offline tests passed in 45.50 s**, original process 20261,
terminal 0. This is not a vendor execution or a runtime change. The v4 actual
failure at cycle 942 remains a failure and its bundle/evidence remain intact.

Tested FW: `e1fa85a290e60c40bc16cc13608f48f1239e7ab2`.
Tested HDL: `28a822025a3ba5e47608b8875ff252baf73e8f42`.
Branch: `codex/starlink-rx-only-do-not-merge-high-rate60-paired`.

## Contract and source delta

The pre-evaluation contract is in
`docs/starlink-retained-causal-frame-contract-20260910.md`.
The script's first-input frame convention is no longer imposed on vendor
behavior. Every one of 40 jobs, including the two aborted forward prefixes,
requires its own admitted/configured reset epoch, one known pulse after at least
one accepted physical input, a known-zero next sample, and frame strictly before
first raw output. No universal +3-cycle or third-word rule is asserted.

The source-bound `RACT_FRAME` record contains context, global job, phase, fixture,
start, admission, actual sampled reset release, actual configuration handshake,
event/closing cycles, and physical input counts before/on/after the event.
The result checker independently joins these counts to numerical input rows.
Each reset release is now uniquely joined to its admission (+2) and configuration
(+3), including aborted jobs. All previous numerical, clock, service, status,
ownership, raw-input and shadow checks remain unchanged.

Relative to v4: **70 of 77 source files unchanged, seven changed, three added**.
The only HDL change is the test witness (30 additions, two removals). Runtime,
all eight vector files, compiled list, profile, original script and vendor runner
are byte-identical. The new manifest kind is `retained-output-actual-v2-causal-frame`.

The complete witness and expanded bench invert exactly to v4 hashes
`cdf025b2d72cf57a6d7ad9b78314d4eee316447ff859297a15d46efa1eb7da1b`
and `6d498ee2f8ba788e775e711753f13f85657e0c500f75ad5ffa3a6ae8cdc1575f`.
The insertion-only result-checker delta inverts to v4
`d88ad9a86de506972a3c0a50176e09525dec4e41483ce0b7e425768e407269d4`.
That legacy parser is reconstructed only inside the historical logger regression
tests. The live verifier has no legacy mode and cannot supply missing frame data.

## Offline evidence

Initial bounded frame-only gate: 67 passed, 23.21 s, original 3870 terminal 0,
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-causal-frame-v1.cGzaFDPo`.
Final source adds explicit rejection of frame-less legacy logs and legacy manifest
kind. Final 251 gate:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-causal-frame-final.g0YTjp8z`.

The 68 final frame tests cover complete strict inverses, all 40 owners, idle-gap
events, later-input events, post-input and immediately pre-raw events, eight
malformed scripted producer cases, all 13 frame fields in both mutation directions,
missing/duplicate/stale/reset/coherence cases and physical-input timing forgery.
These event placements are directed scripted controls, not measured vendor timing.
All healthy directed placements preserve the complete 77,953-row numerical CSV
SHA `07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
The historical v3/v4 logger proof still checks complete CSV and log equality with
only its previously approved unique `$finish` provenance substitution.

Final pytest log SHA: `32e7186a5d53e6cc55d8f1a5394b999fb4f2660528ee40ad19b92c20a7381b65`.
Final XML SHA: `764b377e15fa0a17624aa765cbe38afdd573b5c904adb0f8e232ef43fd2ff43e`.
Ruff F/E9 passed. No source was changed during the final run.

Replay from the isolated FW tree (choose a new recovery directory for `R`):

```sh
env -u PYTHONHOME -u PYTHONPATH -u PYTHONOPTIMIZE -u LD_LIBRARY_PATH TMPDIR="$R" \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest -p no:cacheprovider \
  tests/test_starlink_retained_output_actual.py \
  tests/test_starlink_retained_output_actual_bundle.py \
  tests/test_starlink_retained_completion_declaration.py \
  tests/test_starlink_retained_logger_repro.py \
  tests/test_starlink_retained_logger_calls.py \
  tests/test_starlink_retained_frame_contract.py \
  --basetemp "$R/pytest" --junitxml "$R/results.xml" -q
```

## Frozen bundle and next gate

Bundle:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-output-actual-prelaunch-frame-v5`.
External manifest SHA:
`c3936f7e8552d7d377ca1e6fc5ba220d0667b68d00a24e24f524de33e75cbae8`.
80-source signature:
`9c7996e6d61a559ddfe99543b80c62063b3a5fed2cd43f7aa7a43b1f664af4f7`.
There are 83 file receipts plus the manifest. Frozen standalone base-Python CLI
verification from `/` with `--live` passed before/after final tests and after commits.
The untouched v4 frozen CLI separately verifies original `eef29e37...` bundle
without comparing its historical sources to the newly edited live test files.

Parent source review, independent regression and explicit one-run ownership are
required before another vendor invocation. No vendor, physical, radio, PPU,
primary merge or clock change occurred in this increment. This remains the seven
fixed retained-output contexts, not continuous 15/60 MS/s capacity, causal
acquisition, lower-clock closure or RF qualification.

Separately authorized v4 logging-only publication completed HDL first then FW,
with terminal-zero pushes and exact remote checks at HDL `b94909a6...` and FW
`1deba77a...`, DNM branch only. The new causal-frame source is not pushed here.
