# Inverse sealed v2: bounded recorded-WDB history

The one approved read-only loader **35055 exited 0**, followed by successful
offline interpretation. No simulation was advanced/restarted, no values were
forced, and no RTL or original run file changed. This is recorded functional
history evidence, not synthesis, timing closure, receiver or RF qualification.

## Exact execution

- Start `2026-09-10T16:33:18.071525Z`, end `16:33:25.870132Z`; 7.798 s.
- Owner `5f68f5292349cf52c58dfce44b4151870b9e4b94276a75b2cdb2c4803c591329`;
  Tcl `e4db9fd25f16322dbfa04a9c886d5f73bbda55b806bdc02949b2a166addaed17`;
  plan `4aaeaa9d7a20a2a9da4f3721dea5189909467ee9c7726666f38f69cb1ae4a605`.
- Vivado 2022.2/SuSE, two threads; `open_wave_database` and
  `get_value_database` only. The owner used explicit sanitized Python `-B`,
  exclusive output/TMPDIR, original process outcome and unconditional post-hash
  receipts, without timeout restart.
- Original v2 WDB: 133,627,003 bytes, SHA
  `96418352ac9d6b2b9849bcad5a6d0dd3829ede343b0625dccb5d5bb86592171c`.
  The loader opened a hash-identical **copy**, not the original project WDB.
- All 215 inventoried inputs, including all 208 original v2 files and the copied
  WDB, were byte-identical before/after/live. Original file names were unchanged.
  The only incidental `xsimSettings.ini` appeared beside the copied WDB under
  `inputs/xsim.dir/`; it is retained, not hidden or attributed to the original.
- Original outer log SHA
  `c008f94833dafd436af5e2088647d5ea03d568fc26bc1e12de76a66aff6888fb`.

## Observed values and independent interpretation

All **148 exact paths** (115 arithmetic, 14 guard, 19 ownership) returned recorded
values at all **64 predeclared timestamps**, totaling **9,472 values**. Coverage
is startup/first physical edge; two complete lease-0/lease-1 inverse lifetimes
at ADMIT, first TAKE, QUALIFY, CERT, SEAL, PUB, ACK, REL and REUSE, sampled just
before/on/+1 ps after each edge; and the final counter/finish boundary.

- All 64 unconditional actual/original/default **155-bit vectors** were equal,
  including the identical mixed-X startup snapshot.
- Both old **119-bit arithmetic tuples** matched at all 58 original
  reset/flush-qualified timestamps: **116 comparisons**. The complete tuple,
  including invalid-public payload fields, was compared; no data-valid mask was
  added. Startup/reset snapshots remain recorded but are not arithmetic-qualified.
- Eighteen post-edge observations checked the two complete ownership lifetimes:
  admitted full source identity and independent lease tag, once-only token counts,
  qualification/publication/ACK/release counters and reusable ownership closure.
  Expected pre-edge TAKE/CERT/SEAL/PUB/ACK/REL signals were also present.

| Physical-time snapshot | Pre count | Post count |
|---|---:|---:|
| Startup 0 fs | 1 | 0 |
| Startup +1 ps | 1 | 1 |
| First physical edge | 2 | 1 |
| First edge +1 ps | 2 | 2 |
| Final edge −1 fs | 1,180,857 | 1,180,857 |
| Final edge / original finish | 1,180,858 | 1,180,857 |

These are recorded **physical timestamp** values. They do not expose individual
Active/Inactive/NBA iterations at the same timestamp or retroactively diagnose
old failed14041 startup behavior. The complete actual assertions and prior
offline scheduling tests remain separate evidence. These bounded snapshots do
not replace the full 19,760-event actual protocol/numerical/fault suite.

Interpreter SHA `a395e899ce20acbe320deee11c51b4b0c8b8789fb88c4f4887b55c756081b5e0`;
result SHA `e7eea11977c44c60a2b663010e2eb1174363d4446222ef8560d609ad07311d6a`.
Parent independently repeated the interpreter with only three path substitutions
and a whole-source inverse, reproduced that exact result SHA and all counts.
Preparation also retained two Tcl mocks: complete enumeration exit0 and missing
history exit1 with after-hash checks; neither mock invoked the vendor loader.

## Portable preservation

Raw query root:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/inverse-wdb-prepared-v1.0elVwpXY`.
The archive includes the plan, generator, original qualified reference scripts,
frozen query/owner, all query receipts/logs, the copy-only settings sidecar,
offline checks, interpreter and interpretation; **26 safe unique regular
members**, all hashes reread and verified. Archive size **162,070 bytes**, SHA
`5caf98ae3ccd9fa84b1bb59bed84c6aa5477f34fb4eb30554b1b5c2e5d084dc6`.

The duplicate WDB payload is deliberately not stored again. The inventory gives
its exact bytes/hash and member reference in the already committed actual archive
at FW `27ca617027c7ffb0ce19998d75e048f26b92f334`, whole archive SHA
`236cedcd7f2c7fb29fb3f17e4f3e974b375335e13b6849380d3b6b5dc96ce11e`.
All original and copied WDB files remain locally preserved. No live handles or
new vendor/physical/radio authority is implied by this handoff.
