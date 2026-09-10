# Paired60 expected-expiry case: offline preparation only

The additive late60 preparation passed **681 offline tests in 13.90 s**: 370 new
tests plus the unchanged 311-test healthy60 harness suite. Full composition
elaboration passed with an inert, fail-fast FFT declaration; neither `vvp`, native
service, Vivado, nor vendor FFT simulation was executed. This report does not
authorize a future actual run.

## Frozen identities

| Item | Exact identity |
| --- | --- |
| Tested FW | `ba2f8ca59b76a07f0fcbac84371dd2e8a8010056` |
| Tested HDL | `813f9eb17c8c1680ef160f202756e25c6a2878b2` |
| Pre-evaluation recipe commit | `cddf9d8f8` |
| Bundle | `build/high-rate60-late-prelaunch-v1` |
| External bundle SHA256 | `b31f0b1612d18ca926eb9698e5beab5c06c4839f49a7cf2da85934e65a46c7f0` |
| 118-source signature | `8989b0a7d5353fe657173c64576b8f0b057246e3541750e2c7b890ca4675b997` |
| Derived runner SHA256 | `1ca8c38a649bcfc299afb608977ac6487acb68eb16fe0a00d0a4324591e67e2c` |
| Late SV include SHA256 | `b3a059c7f397eba2354eefc366bd6a799e3b1228cac8e9af2429f7e242bfbda1` |

The final external bundle byte-matches the final pytest-generated bundle at
`/tmp/starlink-highrate60-late-offline-v3/late60_bundle0/bundle`. It contains 375
hashed payload files, 7,655,188 bytes, plus `bundle.json`. All 118 live/snapshot
sources and the 40-node imported Python closure are frozen. The original healthy
bundle is nested unchanged, retaining all 108 original healthy source identities
and all 69 numerical files. Its external SHA remains
`b5f7d48a96217691d7a034634d3bdc7006e489066e571d93b00ce2ed5f741714`.
The standalone frozen verification CLI also passed when invoked from `/`.

No runtime HDL, native arithmetic, public profile, driver, healthy60 source,
golden, original30 test or old receipt changed. The only HDL addition is the
186-line `tb/bank_native60_late_logic.svh`. Firmware adds the frozen recipe,
adapter, negative verifier, bundle helper, CLI, three tests and documentation.
The ABI1.8 public admission depends on the previously reviewed experimental
StageA30/60 branch; it is not deployed host/kernel ABI support.

## Frozen negative and independent healthy contracts

The original 264-tap center is 34359740384; a normal 520-sample capture would start
at 34359740256. This case deliberately triggers at start + 32 = 34359740288.
Require an actual enabled, consecutive sample-domain command handshake in
[34359740288,34359740448], with exact request `60000520`, generation `60000001`,
center/timestamp and signed lead −193 through −33. All eight public AXI
transactions are bounded at 24 controls: 8×24 + 8 entry + 32 queue/CDC = 232 ≤ 256
controls. 256 controls span 153.6 true60 periods, bounded by the 160-slot window.
The trigger alone is not evidence of actual scheduling or expiry.

Require exactly one public submit, wrapper handshake, FIFO acceptance and actual
sample handshake. The accepting sample edge must physically produce rejected=1
and late=1, with no admission, duplicate, overlap, pending or capture. Local
same-edge rejection visibility is distinct from later public snapshot CDC.
The unchanged readback observer witnesses the actual low-register capture and
exact coherent 64-bit public pair, with independent 2/31-sample lag and 48-control
pair bounds. It does not incorrectly require the public snapshot to be current.

Coefficient-energy preparation is explicitly separated from a native job. Before
ready, only the actual coefficient preparation states may be busy, while source
enable/strobe are zero. After exact 264-tap ready, engine/bridge/reducer must stay
idle and all native capture/raw/qualified/packet/result/IRQ activity must stay
zero on every monitored source/control edge, throughout the complete source,
both audits, coarse map release and final quiet interval. Unknown protocol,
state or health fields fail. There is no broad busy or late-health mask.

Two independent public audits use generations 1 and 2 and read the same 31
counter/status registers: exactly 62 reads, not packet reads. Both retain exact
request context, rejected=late=1 and every non-rejection job/result counter zero.
No 0x54 result-word read or 0x58 native result release is allowed. The first audit
follows physical rejection; the second follows complete source-off and coarse
STOP while the complete map remains owned. Each snapshot generation is bounded
at 512 controls, and the remaining 34 transactions give 512+34×24=1328 controls
per audit. Final negative observation must finish within 2048 controls after
source-off. The unchanged final no-stale interval is 256 controls after all public
reads and map release; the global watchdog remains 160,000 controls.

The two disabled CDC prime beats remain separate from the unchanged 16,423 raw
samples, with no tail. The 3111-sample preroll and startup pause are preserved;
all 13,312 post-preroll original samples remain uninterrupted at the exact true60
clock/index relation. Source clock continues after valid stops. Both independent
DDC enabled-prefix ledgers and every visible FFT stage/score remain exact, with
894 admitted scores, 447 read map words and all 512 independent PIL1 CI16 words.
The original full-source/STOP/PIL1 lifetimes and pilot-enabled cancellation of
unpromised final DDC pipeline slots are not reinterpreted.

No FFT-at-rejection claim is made: the fixed trigger precedes the first FFT input.
Instead require actual own-FFT-clock forward transfers and actual pilot accepts
after physical rejection, while native remains empty. Positive native capture,
compute, result-release or full257-drain receipts are forbidden here, not forged.

## Exact reuse and offline coverage

Four complete healthy source files are adapted by explicit counted context
edits, each with before/after SHA and a strict complete-source inverse:

| Adapted file | Edits | What changes |
| --- | ---: | --- |
| Paired top | 22 | Native negative lifetime/receipts; all coarse/source/PIL checks retained |
| Native include | 2 | Replace positive monitors/command; preserve whole public264 configuration and actual tracker |
| Outer result verifier | 13 | Negative native component/ownership fields; unchanged coarse/PIL numerical checks |
| Actual Tcl runner | 12 | Fixed case paths/entry/name; same real FFT helper, two threads and terminal/integrity policy |

`case/inverse.json` restores every original byte, not just selected declarations.
The old result verifier is never given rewritten logs or fabricated healthy
native receipts. The new verifier rejects missing/duplicate markers, every one
of 62 corrupted audit words, identity/lead/stale-readback/unknown-flag mutations,
any native work, missing empty log files, wrong source/clock/support/pilot data,
and mixed-case failures or shutdown errors. The expected inventory is 521 outer
paired markers plus 74 negative-native markers, never a healthy-native terminal.

Bundle tests reject changed source/kernel/cohort/goldens, self-consistent but
unapproved manifests, changed source closure, mutable derived contexts, symlinks,
overwrite attempts, wrong external SHA, alternative rates and runner mismatch.
Tcl command stubs verify failure-before-project and launch-failure handling,
preserved original errors, post-failure source verification and no false terminal.
Contaminated-environment tests verify sanitization affects only the Python child.
These stubs are not Vivado or simulated service evidence.

Compile warnings are retained: the inert FFT declaration inherits a timescale,
and the unchanged bank result guard has the legacy optional floating
`idle_mailbox_fault_now` input with default-off selector. Compilation exit0 is
not a warning-free or actual FFT claim. Full before/after compile input hashes
match. Generated parser specimens carry `PARSER_ONLY.json` and are never saved
as measured service or vendor terminal evidence.

## Attempts and exact repeat

| Attempt | Original handle / result | Retained location |
| --- | --- | --- |
| v1 | 98015, exit1; 291 pass / 4 mutation-test failures | `/tmp/starlink-highrate60-late-offline-v1`; `build/high-rate60-late-offline-v1.xml` |
| v2 | 60886, exit0; 295 pass, 7.32 s | `/tmp/starlink-highrate60-late-offline-v2`; `build/high-rate60-late-offline-v2.{log,xml}` |
| v3 final | 40085, exit0; 681 pass, 13.90 s | `/tmp/starlink-highrate60-late-offline-v3`; `build/high-rate60-late-offline-v3.{log,xml}` |

v1 exposed token-presence policy that missed a mutation when another identical
guard token survived. The checker now requires exact repeated-token counts;
no bench, numerical, recipe or rejection bound changed. v2 passed; v3 added
per-register corruption, unknown-handshake and missing-empty-log tests and the
unchanged healthy311 scope. Earlier bounded adapter-construction errors were
incorrect expected replacement counts (7 versus actual6, and 2 versus actual1)
before any compile/service; only those construction counts were corrected.
Ruff passed on all new Python files.

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest -q \
  tests/test_starlink_high_rate60_late.py \
  tests/test_starlink_high_rate60_late_result.py \
  tests/test_starlink_high_rate60_late_bundle.py \
  tests/test_starlink_high_rate60_harness.py \
  tests/test_starlink_high_rate60_harness_result.py \
  tests/test_starlink_high_rate60_bundle.py \
  --basetemp=NEW_UNIQUE_ABSENT_PATH --junitxml=NEW_UNIQUE_JUNIT_PATH
```

## Proposed one actual launch, not executed or authorized here

All of the prospective run directory, owner directory and two external logs must
be checked absent immediately before any separately authorized execution. Keep
the original process handle to terminal; preserve any failure, never retry or
extend source/tail/budget after observing it. The parent Vivado SuSE library path
is required; only child Python is sanitized by the frozen runner.

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/build/high-rate60-late-prelaunch-v1/case/simulate_high_rate60_bank_native_late.tcl \
  -log /tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-late447-v1.vivado.log \
  -journal /tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-late447-v1.vivado.jou \
  -tclargs /tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-late447-v1 \
  /tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired/build/high-rate60-late-prelaunch-v1 \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python \
  b31f0b1612d18ca926eb9698e5beab5c06c4839f49a7cf2da85934e65a46c7f0
```

Use a separate exclusive working owner directory
`/tmp/starlink-bank-route.I50MDJ/main-high-rate60-bank175-late447-v1-owner`.
No environment-corrected retry is preauthorized. Generated IP and original/copied
bundle hashes must be recorded before/after, including failure paths.

This remains one proposed ideal-clock, reduced447x2, deliberately expired static
request. It does not qualify causal acquisition, RF sensitivity/timing accuracy,
750 Hz or full production maps, host ABI/IIO delivery, physical60 timing, radios,
or the whole original15/30/60 paired scanner.
