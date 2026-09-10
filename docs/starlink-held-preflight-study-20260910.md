# Held preflight tuple/two equalities: tested, no physical measurement

Tested source: FW `28cd6e5fa576e22c1ac84421182ec713d6a64769`, HDL
`7ee87258be4cde11a6092d22ad76a085cfaecc76`. The prior −1.596ns physical
failure remains immutable at FW `5e6424a4b` / HDL `6fb16e4b`; it does not
measure this new source. No synthesis/route was run in this step.

Registered preflight now selects valid/data/ordinal/TLAST/metadata/lease by
held_phase directly. Default uses next_inverse. Discovery/ownership/read muxes
remain unchanged. While preparing (VERIFY/ARM), the old state-selected phase
equals held_phase, so the entire preparing tuple is identical. Both70-bit
equalities use24kept leaves/four groups/final AND only in registered mode:
bank metadata versus engine descriptor, and engine versus expected-product
descriptor. Phase bit69 and forward low5-zero checks remain; expected-product
identity remains ignored in forward mode. No registers or logical cycles added.

A strict entire-wrapper inverse adapter restores exactly these additions and
requires the result to equal `447183b8`. In particular,
`descriptor_certified <= preparation_valid && !any_fast_fault` and all current
active/input/result/publication/ACK/epoch/quarantine logic are unchanged.
The only allowed internal value difference is unused preparation_valid outside
preparing; no current fault/cause/reason equivalence exemption was added.

## Two distinct proof scopes

The fast bench extracts the literal live RTL predicate region and compares it
with the same region from frozen447183b8. It is **not an FFT model or numerical
receiver test**. Each default/registered mode passes2,520bit/header rows:
three corruption families, every70bits, both transform phases, three boundary
labels and destination ready low/high. Families separately test bank mismatch,
expected-product-cache mismatch and coherent bank/engine changes that isolate
phase/low5 requirements. Forward cache-only mismatches remain ignored.

Each mode also passes396cause/TLAST rows (all64six-cause combinations plus
early TLAST) and36idle/reset rows. Twelve registered unused idle predicate
differences are explicitly counted; default has zero. The two ARM labels have
the same combinational predicate; only the actual-core tests establish distinct
capture/consume timing. Omitting bit69 from either comparator is rejected at
its first qualified witness: bank/forward or cache/inverse, VERIFY, ready low,
with candidate cause`10` versus frozen`18`. Both expected failures are retained.

Fresh actual Vivado2022.2 simulations at100/175MHz pass in both modes. The
actual bench independently reconstructs the OLD preflight tuple/full equalities,
checks all preparing tuple bits including lease, compares six current causes
globally, and accumulates expected epoch reasons from OLD causes. Its result
shadow now consumes the OLD preflight fault, not the DUT's new predicate.
All earlier active input, terminal publication, reason, handoff/ACK, reset and
ownership witnesses remain, including12real-bank active corruption cases.

The registered84boundary rows now corrupt raw source/product metadata, valid,
ordinal and destination-ready signals. Lease faults corrupt held_lease, leaving
actual consume-generation counters untouched for the no-reuse assertions.
Core ready low/high and same/next-edge status are exercised. An additional12
actual cases cover expected-cache bit69 at VERIFY/admission-capture/receipt-
consume, both core-ready values and both phases: six forward cases complete
healthy results; six inverse cases retain the cause and veto start/read/config/
publication without consuming the owned product bank.

## Receipts and one explicit stimulus difference

Registered:1,179,896global cause checks,1,850preparing tuple/lease checks,
12cache cases,84raw-bank boundary rows and1,172,593legacy input-guard checks.
Default:651,496global cause checks, no preparing/cache/boundary cases, and
649,219input-guard checks. The complete default control CSV byte-matches the
preceding balanced-default run.

The84-row private counters are now **44ready differences /8invalid private
admissions /60masked-start samples**, versus prior60/12/60. This is a declared
injector difference: actual product/output-ready withdrawal also lowers the
result guard's existing mailbox_input_ready admission prerequisite. The old
destination_reserved-only force left that raw prerequisite high. Four formerly
possible private admissions therefore disappear; this is not a changed RTL
fault or public contract. Independent old-predicate/current/reason comparisons
pass under the new raw inputs. No whole registered trace equality is claimed
against the differently injected prior run, which also lacked the12new cases.

Original numerical receipts remain44healthy blocks/10faults,24,064forward/
product words and22,658inverse words including130provisional prefix words,
exactly against frozen arithmetic/metadata goldens. Nominal intervals remain
4,540default/4,548registered clocks. No score normalizer or whole receiver was
integrated. Full regression: **264passed, eight unchanged explicit physical
skips**. All six new tests and both omission witnesses pass; Ruff/diff checks
pass. Both actual runs passed first attempt, with no RTL correction.

## Frozen evidence and scope

Archive: `hdl/library/starlink_pss_acquisition/evidence/held-preflight-v1/`, with
verified SHA256SUMS over frozen source/vector/script sets, scopes, actual and
unit logs, live-extracted/frozen predicates and omission stimuli. All seven
design RTL files and the actual bench byte-match the tested pin. Scope git
fields record the pre-commit base; source hashes are the actual run identity.

Original runs are `/tmp/starlink-completed-input.5EaJuD/held-preflight-actual-v1`
and `held-preflight-default-v1`; sessions44291/96103 exited zero at03:32:53 /
03:31:23UTC. Raw receipts reside under
`project/fft_bank_owned_slice.sim/sim_1/behav/xsim/simulate.log`.

| Artifact | SHA256 |
| --- | --- |
| Wrapper | `d6491e46caa7419679e50f72a9d7f568a9f2f6ce567a94ddfdff02894c74df60` |
| Registered raw receipt | `16d4f9ca70a5e7428f767d98e4854106ff502940e31dd6796f6435b6b357ad1e` |
| Default raw receipt | `19531f41fee7a3d0235e2f42ef933bc97d27a1cfe124f959fb11f8a93ba7b2dd` |
| Registered original CSV | `25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122` |
| Default original CSV | `b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d` |

Current mapping, area, timing and replacement eligibility remain unproven.
No constraint/clock change, physical trial, production BD, full receiver,
deployment, radio or remote write. Stop for source/evidence review before
requesting any new physical measurement.
