# Offline sealed-product lifetime prototype

Status: **848 PASS**, original final process3417 exit0,17.95s. Ruff passes.
Additive, default-inert, unconnected RTL. No vendor FFT, synthesis, route, top
integration, primary promotion, or source union. The earlier P1 timing failure
and its runtime remain unchanged. Design8358dc was pushed to the existing DNM
FW branch; this implementation is a separate local review checkpoint.

## Source and scope

HDL checkpoint1cbbab6b5 adds only:

- `starlink_pss_checked_product_read.v`: three-slot checked read queue.
- `starlink_pss_product_sealed_adapter.v`: held forward completion, producer,
  reader, handoff and lease-reference lifetime.
- `starlink_pss_epoch_sealed_bank.v`: exact d9c2382f dependency, unchanged.
- Matching `tb/` benches for the first two modules.

All paths are under `hdl/library/starlink_pss_acquisition`. FW tests are
`tests/starlink_oracle/test_checked_product_read.py` and
`tests/starlink_oracle/test_product_sealed_adapter.py`. Tests byte-compare all
eight existing P1 modules against c144694706b0582668606b6224462c0e8850148d;
removing the additive files restores the prior entire source tree.

The composed fixture instantiates the real unchanged result guard,18-bit
spectrum product, and input guard. It supplies synthetic raw FFT results and
input-completion actors, NOT a vendor FFT or actual controller. Its consumer
uses the explicit checked-token seam `CHECK_INPUT_BLOCK_IDENTITY=0`: every raw
75-bit word is independently checked before this guard sees a GOOD token.
Forward/source identity checks are not changed or exempted. No production
caller uses this seam. Kernel(-1,0) and doubled input amplitude preserve the
canonical product's frozen safety shift; real complex minimum operands exercise
real saturation overflow. This is not a new FFT numerical qualification.

## Implemented ownership contract

Product70 is encoded exactly `{5'b0,product70}` into the opaque75-bit bank.
Admission binds the current two-bit lease and start identity. Real qualified
forward final retirement binds exponent and a held completion certificate;
the certificate survives the normal drop of raw forward return-commit. Product
final take does not publish or release ownership. Exact d9c checks seal at n+2;
publication is earliest n+3 and requires the certificate and current raw health.

The reader checks all75 bits, position, TLAST and lease on EVERY offered word,
including full-queue stalls. Two-edge verdicts carry taken/non-taken status,
slot, position and lease; only matching taken verdicts mark payload slots GOOD.
Current faults and current completed bad verdicts veto actual core acceptance.
Malformed future words may be privately observed after a valid head handoff;
they cannot reuse prior GOOD or deliver their bad payload.

Handoff means three checked heads plus a retained reservation, **not all512
read checks completed**. The first implementation missed a bad non-taken
word3 verdict coincident with handoff. The corrected narrow
`validation_fault_now` fences handoff and release immediately. It includes
completed verdict/tag/head/credit/unknown/closed/admission faults, deliberately
excluding release-request validation to avoid a combinational feedback loop.
Full current cause bits and detailed registered reasons remain separate.

Final RAM prefetch/ACK is not lease release. Release requires actual final
core acceptance, the real input guard's delivered completion, empty queue,
empty observation pipeline and all producer/certificate references drained.
A separately declared certificate-delivery hold confirms that actual-final
alone is insufficient; it is not claimed to occur naturally in the old guard.
Common epoch reset owns all new state. Either local or peer reset closes
publication; rearm requires an explicit fixture-owned purge attestation.
Private consumer reset does not erase epoch poison. Paused-slow-domain purge
implementation/CDC safety is outside this fast-only fixture and still required
before integration. Two-bit ABA safety is conditional on drained finite refs.

## Evidence and measured cost

Final tree:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-sealed-adapter-final-v2.tVeiyFVH`.
`pytest.log`, `results.xml`, every compiled source/netlist, invocation/exit log,
mutant log and per-case receipt remain intact.

Coverage includes all75 read bits at0/37/511, every stalled offered bit, every
70 producer bit at0/37/511, producer position/TLAST, stale slot/verdict, queue
credit, real arithmetic overflow, real consumer duplicate start, eight current
causes at seal/publication/handoff/release, reset and default/X/Z parameters.
Directed onset cases distinguish completed before/current handoff verdicts from
later private verdicts. Release stale-verdict injection is explicitly an
inconsistent internal-state witness; natural drained release has observed=0.
Missing GOOD, metadata leaf, offered-stall observation, tag, current handoff
fence, actual-completion drain, raw identity and premature certificate mutants
are executed and rejected; a feedback mutant is rejected by the graph audit.

Eight healthy leases (including two-bit wrap), each512 exact nonzero products:

| Interval | Fast clocks |
| --- | ---: |
| Last product take → checked seal | 2 |
| Last product take → publication | 3 |
| Forward completion → publication | 6 |
| Publication → prefetched handoff | 10 |
| Handoff → first actual core take | 2 |
| First → last actual core take | 511, zero holes |
| Actual last core take → lease release | 1 |
| Fixture admission → release | 1555 |

The1555 fixture clocks exclude real FFT execution/control. The original+12
planning allowance is NOT an established receiver overhead bound: product
final→prefetched handoff alone is13 clocks here; some baseline mailbox latency
already overlaps this. Do not subtract/add these fixture numbers to old pair
timings. Actual controller admission/deadline tests remain required.

Logical declared state: d9c bank317 bits + reader350 + issuer93 =760 bits,
plus one512×36 payload RAM. This revises approximate334/90 reader/issuer
planning counts. It excludes real guards/product already present in the
fixture, external purge/CDC, and any future controller integration. No new
arithmetic, extra payload RAM or mapped-resource claim. LUTs, fanout, inferred
registers and actual placement cost remain unknown.

The executed Icarus continuous graph has3123 nodes, zero cycles. Q/procedural
input variables are cut points; the only combinational function calls are the
unchanged register-fed product rounders. All used netlist operations are
allowlisted. Raw offered product metadata is absent from the current
publication/handoff/core-valid/release cones. Counts132/304/59/367 are graph
nodes, NOT timing levels. The new narrow verdict cone uses registered
equal-groups/tags and local credit/position checks; it does not reintroduce a
current full75-bit comparator. Raw status/vendor/current causes still enter
directly. The feedback mutant intentionally adds release_valid into the new
verdict predicate and the graph rejects its cycle. This is not synthesis or
proof of arbitrary procedural logic; no top hookup is approved.

## Retained chronology

- Queue v1:325PASS/2FAIL. Final-stall actor accidentally resumed READY; corrected
  the actor. Initial missing-GOOD mutant survived a full queue, so a separate
  drained-head gap witness was added, not a weakened rejection rule.
- Queue v2:328PASS.
- Adapter v1:13FAIL. Fixture omitted the frozen safety shift and scalar corner
  did not overflow. Corrected stimulus only; adapter v2:13PASS.
- Adapter v3:407PASS/76FAIL:75 real poisoned-prefetch handoff witnesses and one
  duplicate-at0 actor firing before consumer admission. Corrected narrow fence
  and actor phase qualification respectively.
- Combined v4:810PASS/1FAIL: old tag-mutant textual anchor now occurred twice.
  Narrowed anchor to the original errors assignment; rejection unchanged.
- Combined v5:828PASS. v6:838PASS/2FAIL: Icarus CLI rejected X/Z defparams before
  RTL ran. Same literal overrides moved into the fixture source; v7:842PASS.
- Final v1:848PASS17.41s. Final v2:848PASS17.95s after import-order-only Ruff fix.

All failures and passing counterparts are retained, not overwritten. Final
review must precede any actual-core preparation/top integration or physical
trial. There is no claim that this fixes the independent remaining ROM CE cone
or composes automatically with inverse sealed-bank or scheduling alternatives.

Replay from this FW worktree with a fresh nonexisting base:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH PYTHONDONTWRITEBYTECODE=1 \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest \
  tests/starlink_oracle/test_checked_product_read.py \
  tests/starlink_oracle/test_product_sealed_adapter.py -q --tb=short \
  -p no:cacheprovider --basetemp /absolute/new/nonexisting/cases
```
