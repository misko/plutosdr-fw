# PSMA1.8 Stage A60 — isolated module admission and public-contract evidence

The default-off source60/upper bank+STOP module contract is implemented and
offline tested. This is **not** a paired60 FFT/native/PIL1 run, a packaged
receiver option, a live profile switch, or deployment qualification.

Tested source pins: FW `6e561ee50b299d32991f636932eeccc467159303`,
HDL `f16dc564c541df614a7c2b27c489aece5320dc43`. Base FW
`3c949b445b0208d6b1f5f72571fc5da1eeb0f2eb`, HDL
`706ffb7b5b842409d8a8714c056203d8b5555034`. Worktree/branch remain the
isolated `high-rate60-paired` / `codex/starlink-rx-only-do-not-merge-high-rate60-paired`.
This depends on the previously accepted but unpromoted StageA30 public
contract. No primary tree, remote, PPU, radio or physical work was changed.

## Runtime delta and exact identity

Only two runtime files change: `axi_starlink_pss_acquisition.v` and
`axi_starlink_pss_phase_map_sync.v`, **40 additions / 4 deletions** total.
`ENABLE_BANK60_PAIRED=0` is appended to each public parameter list, preserving
all earlier positional arguments. Setting it to1 requires exactly source60,
bank/shared/realtime/pilot/STOP all1 and conditioned energy1073765335.
The selector rejects −1/2/X/Z, and case-inequality guards reject unknown
required fields. These are initial/elaboration checks, not runtime tuning.

| Contract | Default-off branch | Explicit new mode |
|---|---|---|
| Bank source | Existing30 only | 60 upper only |
| PSMA ABI / capabilities | Existing1.7 / 0x7ff | 1.8 / 0x7ff |
| DDC configuration / raw delay | Existing30 0x000f0203 / 7 | 0x020f0403 / 21 |
| Conditioned coefficient energy | Existing1073744004 | 1073765335 |
| Discontinuity observation | All historical semantics unchanged | Saturating sum of both x2 stage counters |

The existing60 kernel is `upper_edge_pss60_x4_ddc_kernel_q17.mem`, SHA256
`7b006bac23a3c58f614728dbfdb17d28bd77defb3d6d0d24aaa76255669c0c67`.
The existing filter contract remains
`8e807d15d5372b0a9669d1190d899697e7c2911a73ddfb23095806c2a31de5b2`.
No sample/score/FFT/DDC arithmetic, memory port, native core, kernel, golden,
map geometry, register address, STOP record length, packaged IP, BD, clock
constraint, build profile or driver changes.

The new discontinuity value counts **stage events**, not unique raw gaps.
One propagated gap can count twice. Addition uses33 bits and clamps at
0xffffffff; it never wraps. A first-stage event remains visible even if
disable/flush prevents subsequent second-stage propagation. Legacy source60
continues exposing only its historical second-stage count.

DDC counters survive conditioner/map disable, flush and source-only reset;
only the common upstream AXI reset clears both producers. No software clear
or per-visit baseline subtraction was introduced. The existing conditioned
STOP mask0x77ff and explicit nonzero discontinuity veto remain unchanged.
Late faults change terminal health but never retroactively undo accepted
scores or completed map data. Retained maps remain readable/releasable.
DDC high/low/high retry and held AXI response semantics remain intact; these
are individual coherent counter reads, not atomic accepted/emitted pairs.

## Test composition and limits

- Real public wrapper + real source CDC + both unchanged integer x2 stages,
  with an explicitly inactive acquisition-core interface. A first marker
  gives stage counts1/0; stopping before FIR propagation must retain this
  new-mode fault. A64-sample zero burst gives1/1 and5 canonical outputs.
  Disable/flush/source-only-reset retain counts; common reset clears them.
  Two disabled prime beats followed by64 raw samples give6 clean canonical
  outputs. Both new and legacy60 modes are tested. These are finite digital
  control/zero-arithmetic witnesses, not a signal-quality or throughput test.
- Nine synthetic **stage-output interface** specimens per mode exercise
  first-only, second-only, both, exact0xffffffff and overflowing sums. They
  pass values through public source/CDC into explicit DDC substitutes; no
  hierarchy writes or forced real counter state. These prove wrapper
  aggregation boundaries, not real DDC event generation at enormous counts.
- Four PSMA/controller + actual8-bin/4-frame map + real AXI lifecycle runs
  cover both summary flags. Their **single real x2 fault producer** drives
  the controller's public counter boundary; it is not called a60 cascade.
  Actual clipping/gap stimuli cover rejected admission, pending partial
  abort, retained publication before STOP and late failed terminal after
  healthy STOP, exact32 admissions/eight map words, release, reset/replay.
  Public synthetic carry values separately test high/low/high retry and
  four stalled AXI responses. No carry stimulus is represented as real DDC
  work. Source CDC is covered by the separate wrapper test.
- Initial admission, old positional/default identities, every new required
  field's X/Z cases, invalid combinations/energy, wrong kernel/identity,
  sum wrap/omitted-stage/default-mode mutations are checked. Behavioral
  guard mutants run without identity assertions: weakening !== to != or
  deleting admission demonstrably admits the forbidden specimen and is
  rejected by the negative-test checker.

Old30 benches/tests are unchanged. The lifecycle source is an exact,
reversible adaptation of the SHA-pinned complete old bench, changing only
explicit60 identity/admission and labels; every old assertion remains.
`psma18_projection.py` checks full before/after SHA256 and exact-position
hunks before restoring both StageA30 runtime bodies. A four-line adapter
then invokes the original StageA17 inverse for older regressions. A separate
test restores the entire original projection helper by SHA. Changed-hunk,
deleted-guard and unrelated-body mutations cannot disappear through a
permissive projection. Legacy cycle-trace tests still execute the live RTL.

## Results and reproduction

The exact12-file scope is the `TESTS` list in
`tools/freeze_starlink_psma18_stage_a.py`; run with
`/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest`, `-q`,
and unique `--basetemp` / `--junitxml` paths. This is660 tests. Parent repeated
the same frozen source independently: **660 PASS,25.11s**, original90816,
`/tmp/starlink-psma18-parent.EdANJN`. Local retained attempts:

- `build/psma18-stage-a-v1`: first140 new cases PASS2.74s, original77345.
- `build/psma18-stage-a-v2`: full660 PASS25.77s, original54110.
- `build/psma18-stage-a-v3`: unchanged660 PASS26.07s, original44671.
- `build/psma18-stage-a-v4`: unchanged660 PASS25.08s, original99418, terminal0.
- `build/psma18-stage-a-v5`: final660 PASS25.21s, original74096, terminal0.

Final660 =155 new StageA60 + unchanged340 StageA30/legacy/numerical scope
+165 existing60 cohort/support cases. All109 source snapshots and live
source hashes matched before/after the final run. Source signature:
`27aff0c356977ea1597256488c76b8dbcdb6cb36e9d22d66b5e8f494399b983f`.
Receipts: `build/psma18-stage-a-source-freeze-v4/{sources-before.json,sources-after.json,environment.json}`.
Runtime wrapper SHA256 is
`a54a51018bedc2141896411e289bd45a13534132163760a96025fea3e07a6e2a`;
controller SHA256 is
`e63cd0e218cb388f11e8c0f76fbf51eee3284379d96ed941dce65b2c6f9b9f77`.
No runtime/test source changed after the first full660 pass or parent review.
The collector is separate archive tooling included in source receipts, not
code executed or qualified by pytest. Its packaging-only revisions do not
invalidate or change the earlier frozen6e/f16 numerical/contract evidence.

Portable source/log/numerical proof:
`reports/experiments/20260910-psma18-stage-a60.tgz`, with per-member SHA256
inventory in the adjacent `.json`. It contains the original69 numeric files,
their original76 sources, final109 sources, six complete historical bodies,
all retained test logs/XML and simulated source specimens, plus failed
partial collector snapshots and final legacy public traces. Earlier repeated
passing public traces stay in their original raw runs, with explicit SHA/size
receipts in `earlier-public-traces-retained.json`. Portable proof also omits
compiler executables and duplicate generated numerical mutants.

The installed toolchain/host are recorded separately; runtimes are this
x86_64 host's measurements, not ARM/Zynq performance. Expected negative
specimens contain fatal messages. Elaboration warnings, including dangling
ports in deliberately inactive admission probes, are retained (final run:
264 compile logs,9301 warning lines); successful
compilation is **not** described as warning-free.

The unchanged frozen60 snapshot CLI rederived all69 numerical files:

```
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B build/high-rate60-offline-v2/cohort/source_snapshot/tools/generate_starlink_high_rate60_paired.py /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/build/high-rate60-offline-v2/cohort --verify
```

Result: `HIGH_RATE60_OFFLINE_VERIFIED`, original32e8a1 terminal0,69 files,
16423 raw/4096 canonical/3129 scores/257 raw and241 qualified native tuples/
512 pilot outputs. No old source or numerical file is regenerated in place.

Final source/evidence receipts are frozen by the additive artifact collector,
which never launches a simulator. Two collection-only environment failures
are retained in `build/psma18-collection-attempts.json`: the Python path was
a symlink, then its resolved21.74MB binary exceeded the text-source limit.
The final collector hashes executables through a separate bounded64MB
streaming path without copying them; source/evidence limits remain unchanged.
Neither failure was an RTL/numerical failure or a claimed successful freeze.
A first package selection also rejected55.99MB against its predeclared48MB
cap before creating an archive. Keeping only final trace contents, with
earlier repeated-trace receipts, preserves the same48MB/6000-file limits.
All three collector failures and raw inputs are retained.

## Remaining admission gates

Host/kernel readers still require explicit ABI1.8/source60/0x7ff admission,
all existing60 filter/kernel identity checks, conditioned0x77ff health plus
live stage-event veto, high-word retry, and STOP/retained-map cleanup/reset
handling. Existing readers must not be loosened to accept unknown versions.
No host/kernel edits were made. Packager/build/profile and physical bank
implementation remain separate gates.

A later reviewed healthy447x2 common-source harness may use two separately
accounted disabled CDC-prime beats plus the unchanged16423 cohort, **zero
tail**. It must check independent conditioned prefixes and512 PIL1 outputs,
all visible actual FFT work, native520/264/all257/241/52 packet reads, source
off before eventual native/map releases, unchanged lead/deadlines and final
drain. This module admission alone proves none of those combined behaviors;
the fixed known center also remains non-causal and is not RF truth.
