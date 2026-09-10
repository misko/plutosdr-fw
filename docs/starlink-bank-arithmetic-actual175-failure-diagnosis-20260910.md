# Bank arithmetic actual175 pair: failures and force-boundary diagnosis

Both authorized actual-FFT runs **failed** at the first deliberate product
overflow injection. Neither has a success receipt or completed fault suite.
No actual retry, runtime change, physical run, receiver integration, or radio
operation was performed during diagnosis.

## Original source and terminal receipts

Frozen FW `4e7103d67d8372628d0162b0e196050ab20ea4d6`, HDL
`5e4c2ad291ac682308ea65b2a48758b2d445b75c`; runner
`33ba72515e0198fae920ef0b0e477a6c07b6c95f3552f3d5671078c2bef90ae9`.
R means REGISTERED_SCHEDULING, B means BOUNDARY_ROUND_SAT, and O means
REGISTER_OPERANDS. Both used the immutable actual generated 18-bit FFT at175MHz.

| Original run | R/B/O | Handle | Terminal | Fatal time |
|---|---|---|---|---|
| baseline175-prepared-v2 | 1/0/0 | 44608 | EXIT1,08:42:49UTC | 1261662920227fs |
| candidate175-prepared-v2 | 1/1/1 | 34776 | EXIT1,08:42:50UTC | 1261765777375fs |

Both reported `PAYLOAD_PRODUCT_OUTPUT_MISMATCH` in `forward_chain_shadow`,
epoch14/test_kind0. Baseline failed in the unchanged reference at line72;
candidate failed in the elastic reference at line124. Before/after integrity
passed; all42 frozen inputs per arm and generated-IP bytes remained unchanged.
Both `results.json` files are absent. The original handles are terminal and were
not restarted.

Before the fault, each saved event stream exactly checked19,456 ordered
forward/product/inverse words and16,986 output-derived scores. These scores are
**oracle-only**, not scorer-RTL evidence. Baseline's220,792-line truncated CSV
matches the same-length historical R1 prefix; the full589,950-line historical
CSV was not completed. These are pre-failure numerical/stall diagnostics, not
an overall pass, capacity result, or full baseline equivalence.

## What the diagnosis actually observed

Read-only queries of both original WDBs recovered top-level epoch14/test_kind0
at the fatal times. Original `add_wave /` did not record the relevant internal
histories: monitor vectors, reference fields, and arithmetic output registers
return `<Blank>`. Their hierarchy names alone do not establish recorded values.
Original WDB hashes remained unchanged. Therefore **the full actual-bank
compared vectors cannot be recovered from these saved waveforms**.

The separately authorized tiny standalone Xsim reproduction used exact frozen
golden-product/arithmetic/wrapper source bytes, no FFT, IP, project, or bank
scheduler. Original handles4397/O0 and90953/O1 both completed EXIT0. For each
option it printed the complete comparison vectors and underlying fields before,
during, and after external overflow/position/start force+release.

Both options showed the same Xsim behavior. The pre-force119-bit vector was
`62a787fd0640280000000800380000`:

| External force | Original direct-reg monitor XOR | Wrapper-port monitor XOR | Inner arithmetic payload XOR |
|---|---|---|---|
| overflow0→1 | 0 | `2` (bit1) | 0 |
| position64→19 | 0 | `53 << 72` | 0 |
| start`2000e0000`→`deadbeef` | 0 | `(2000e0000 XOR deadbeef) << 2` | 0 |

During overflow force the external wire and wrapper output port were1, while
the direct old output register and wrapped arithmetic output register were0.
All vectors restored on release. Thus Xsim demonstrates an observation-boundary
change: the derived monitor observes the deliberately corrupted wrapper wire,
whereas the old direct-core monitor observes the underlying unforced register.
This is a demonstrated standalone mechanism and a source-based explanation for
the matching actual failures—not a recovered actual-bank vector or completed
fault qualification.

The first Icarus hypothesis assertion failed and is retained. A later
observational check, including the **identical final Xsim bench and four HDL
source bytes** under Icarus, showed force propagation into both direct and inner
register observations. All three deltas then appeared in all three vectors.
The simulator difference is measured, not assumed. Neither simulator's result
is generalized to physical hardware force behavior.

## Evidence and preserved failed attempts

The original failure archive and receipt are
`reports/experiments/20260910-bank-arithmetic-actual175-failures-v1.{tgz,json}`:
93,784,281bytes,336 safe unique files, SHA256
`22cdaa34c00226790ed1759a459eab4a28425111d53e169bfab93c73fb514b8e`.
It contains both complete original saved projects/WDBs, frozen sources,
logs/journals, CSVs, and failed run outcomes. Parent independently verified every
archive member. It was created before diagnosis and was not rewritten.

The additive diagnosis archive and machine-readable receipt are
`reports/experiments/20260910-bank-arithmetic-force-diagnosis-v1.{tgz,json}`.
The receipt records its SHA256, all member hashes, original-source/WDB integrity,
exact standalone source hashes/commands, all six Xsim and six identical-source
Icarus observations, and terminal outcomes. Every archive member was reread and
hash-verified. Diagnostic paths are under
`hdl/library/starlink_pss_acquisition/build/bank-arithmetic-force-diagnosis.AbVRjg`
and `bank-arithmetic-force-xsim-v1.x51G4v`.

Preserved unsuccessful diagnostic attempts include the original Icarus
hypothesis failure, an unsupported WDB close command, a live-only current-time
query, and a Tcl argument-order error. None advanced or restarted an actual
simulation. These failures are not relabeled as passes.

## Next authorized preparation, not implemented by this evidence commit

Parent authorized offline preparation only: rebind exactly the three affected
monitor fields—overflow, position, start—to matching inner arithmetic output
registers, preserving the119-bit checker predicate, old shadow body, wrapper
input_ready, every other wrapper field, external injections, and real fault
veto checks. No epoch mask or field removal is acceptable. Required tests must
show genuine arithmetic corruption still fails and the transport still sees
the external corruption, with strict inverse and wrapper-wiring consistency
checks. Any actual retry needs separate source-specific review and permission.

No full-receiver, timing, RF, accuracy, source15/30/60 native-fine/pilot, or
deployment qualification follows from this failed isolated slice. The complete
continuous canonical15MS/s coarse/native fine/2.5MS/s pilot objective remains.
