# Inverse-only sealed bank: original 21014 and separate post-hoc assessment

The one authorized R1/B1/O1/L1/E1, 175 MHz actual-vendor evaluation completed
its HDL suite but **original automation failed**. A narrowly corrected offline
collector subsequently verified the complete functional receipts. No simulation
was restarted; no RTL, stimulus, vector, constraint or original result was edited.
This is not receiver, physical, scorer-RTL, RF or deployment qualification.

## Original execution and preserved failure

- Original owner handle: `21014`, exit **1**, start
  `2026-09-10T15:53:57.717387Z`, end `15:58:17.111528Z`, elapsed 259.394 s.
- Tested FW `50a3030a364de12c16fa2a03e1269fd7838c9f95`, HDL
  `b26f56dd32106c8e91290d075255ac4a6b9ff72d`.
- Manifest `2c1bf9badc769aeae54fe1848d8ce8a3f1cda810e096a541ea5b5840618feb8a`;
  64 frozen inputs, 10 runtime modules, 21 compiled sources, 8 immutable vectors.
- Owner `c77a1a119df74e7e3a93281e59f03a0050bb9e29f03354253618152a6ab1d96f`;
  runner `23e9e9b989e35f013113bd6356288952bf05d58c57d7803c8baa1d74b8239972`.
- `run_outcome.txt` remains `run_status=1`, `after_status=0`. The owner reports
  source unchanged, no launch exception and no after-integrity error.
  Original `results.json` remains absent.

The first collector rejection was trace cycle **146691**, epoch 1, profile 1,
running 1, WAIT_BANK (state 2), core reset asserted, inverse 0, result busy 0,
output reusable 1, no source/product data and no core events; fault was **0**.
The next row, cycle 146692, has running 0. There is exactly one healthy-running
profile mismatch and no healthy-running fault row.

The immutable bench sets `profile = 1` after `await_results(32)` and then calls
`reset_epoch`, which waits for the next slow-clock falling edge before asserting
reset. The parser incorrectly required the old profile throughout that drained
interval. This is not evidence of an arithmetic/guard fault and not a generic
license to ignore mismatched profiles.

## Bounded offline correction

Source FW `fb186470204f314681a37c7fe2962d024e876e04`; HDL unchanged. Only the
trace parser and an additive test file changed; the original 65-test file stayed
byte-identical. Parser SHA
`09061c6d56fab3460536cca74733f2da764ea6f2a2e508a11d4f4d60482f17c6`.

An allowed transition requires the exact complete 64- or 12-job epoch inventory,
all 512 input/raw words and complete configuration/status/commit phases,
fully drained WAIT_BANK, no current event/fault/source/product ownership, and
the next declared profile. At most two 175-MHz rows are allowed before the
adjacent, same-epoch reset row; reset contents are checked, not silently skipped.
Active, incomplete, unknown, faulted, repeated-admission and unbounded cases fail.
Full event data/metadata/count/order and dual-clock timing checks still follow.

Original offline handle `34846` exited 0: **111 tests passed in 64.22 s**
(46 new + 65 unchanged), Ruff passed. Retained log SHA
`5e646135e9ce51caf03375a5bb0bac9ae002ddca960e067ba740445b89e89c06`;
XML SHA `77af26d1f1952472da6903a91244ae1c6c5d2ce4a3cb6e1f0dfdea5b5a348a36`.
The test includes the frozen original parser's exact rejection; it does not
claim the original automation succeeded.

Parent independently repeated all 111 tests: original `64617`, exit 0, 63.83 s,
with all three parser/new-test/old-policy hashes stable. Parent also independently
executed the byte-identical assessment script (`79053`, exit 0), reproduced its
exact assessment SHA below and rechecked all 211 original files unchanged.

## Separate post-hoc assessment

Original offline handle `3463` exited 0. Assessment SHA
`97eccd325d9c70411b692d0cc0103b09e100491dd66e6f6589126b8d3f824169`.
It executes the exact frozen results function with one explicitly audited
dependency binding: the corrected timing parser. AST inverse checking proves
all other timing functions/constants unchanged. The exact original failed
outcome, manifest and owner receipt are pinned. All **211 original files** match
their pre-assessment archive hashes both before and after; no original success
artifact is created.

- All 13 HDL terminal markers and all original fault/reset checks are present.
- All 76 healthy core jobs retain configuration +3, input +5/+7…+517,
  raw output +1298…+1809, and status +1300 (third raw word).
- Forward commit +1810; inverse qualification/take +1810, certificate +1811,
  seal +1812, publication +1813. All 38 lifetimes and 19,760 tagged protocol
  events match; ACK-to-release is one fast edge, reuse the following edge.
- Exact 19,456 ordered words in each forward/product/inverse stream; 16,986
  output-derived sample scores are **oracle-only**, not scorer-RTL evidence.
- Nominal pair intervals: **4554–4555** fast clocks (maximum 26.029 us), within
  the predeclared 4557 nominal limit. Stalled intervals:
  **4827, 4827, 4835, 4827, 4828** (maximum 27.629 us).
  Both retain the absolute **5215 clocks / 29.8 us** budget. The stalled result
  does not satisfy a blanket +8 delta against history, which was never its gate.
- Existing 8192 guard, 25000 drain, 1500000 whole-bench, 24 fault-observation
  and 128–132 provisional-prefix limits remain unchanged; observed prefix 130.
- All 64 frozen sources and generated-IP before/after/live identities pass.
  The original arithmetic, guard and new ownership WDB signal inventories are
  present. **Recorded WDB histories have not yet been queried for this run.**

The 38-block nominal/stalled service measurement is not continuous canonical
source, energy/scorer integration, native fine/pilot concurrency or a physical
clock qualification. No C/K/M/ROM/product-branch union is represented here.

## Portable evidence

The failed original is preserved as 213 safe unique regular archive members,
all hashes verified, 140,853,340 bytes, whole SHA
`07485ace45c94c72bf084de4e0cfbf1529ac6f30b2ae58ac36b72404052b4b63`.
Four ordered parts, each <=40 MiB, reconstruct exactly using the adjacent
`20260910-inverse-sealed-actual-original21014-failed-v1.parts.json` and the
existing `tools/starlink_reconstruct_archive_parts.py`. The original monolith
remains outside `/tmp`; no oversized Git blob is committed.

The separate `20260910-inverse-sealed-transition-posthoc-v1.tgz` contains all
111-test artifacts, frozen correction sources, assessment script/audit and
portable reconstruction receipt: 1513 safe unique regular members, 26,121,894
bytes, SHA `3a4cc394d8c3a267c56a97018881fe92c4c269e95b0be5f331f303ed08eef36a`.
All archive member hashes were independently reread and verified before commit.

Raw roots under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`:

- `inverse-actual-prepared-v1.sUupdgsv`: unchanged original owner/project/sources.
- `inverse-actual-original-archive-v1.Z7yIZFDF`: original archive and reconstruction.
- `inverse-transition-tests-v1.4TAXl7kY`: sole new offline test attempt.
- `inverse-transition-assessment-v1.6ATb1tN5`: assessment script, result and audit.
- `inverse-transition-archive-v1.WpaEeHkI`: separate offline evidence archive.

No live handles, additional vendor run, synthesis, route, radio or promotion is
part of this handoff. Future actual/physical work requires separate review.
