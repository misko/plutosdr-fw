# Sealed-product primitive interface partition — offline only

Result: original34799 exited0, **1444 PASS in37.18s**:596 additive tests plus
the unchanged848 baseline. No top, guard, d9c, P1, vendor or physical edits/runs.
Tested HDL c4befff9a74bbf3743c3ce00eec2bbedbb09fd77 adds only two primitive
variants and their fixture/include. Original runtime remains unconnected.

## Change and exact scope

`starlink_pss_product_sealed_interface.v` separates state/GOOD/sticky-Q ACK
capacity from actual current-safe handoff. The fixture drives real guard
mailbox READY from capacity, but handoff must equal its exact reset-qualified
ACK-clear event, including current idle faults. `handoff_owned` persists after
ACK, never implies producer reuse, and remains health-qualified.

`starlink_pss_checked_product_read_interface.v` separately exports token verdict
(registered checker/tag/head/count evidence) and offered-bus diagnostics. Both
remain immediate at downstream ACK/read/release. All75 raw metadata bits,
ordinal/TLAST/lease and stalled observations remain checked; no raw-word check
or same-token GOOD requirement is removed. The canonical d9c bank is unchanged.

Raw product VALID remains ungated at the d9c observer. Its private take uses
the ACTUAL exported READY via input_offer_new. Finite forced READY0 at37
quarantines the unsupported active-return stall; final511 can hold4edges and
then complete. Closed/X/Z offers remain visible at READY0.

Qualified invalid admission/completion (D0/D1), and unknown qualified completion,
still reject the relevant private capture and latch the original detailed
issuer reason on that edge. Only reason Q feeds upstream acceptance/publication
logic: the bank summary propagates **one edge later** than the former direct
diagnostic summary. An owned reader does likewise. This is explicitly NOT
same-edge raw-fault equivalence for arbitrarily forged qualified pulses.
Real guard/product streams assert D0/D1 absent and completion before product
final retirement, including malformed early product TLAST. The forward phase,
known/header-valid admitted descriptor and reservation are required caller
preconditions; the standalone guard alone does not validate that job origin.

Issuer6 observes bank_valid and therefore no longer feeds the bank_live input
that produces bank_valid. It remains current at reader/ACK/release and in its
detailed sticky reason; bank summary follows reason Q. Independent raw product,
vendor/orphan, duplicate, overflow and source-visible causes remain immediate.
Named scalar causes avoid reconnecting the aggregate diagnostic bus upstream.

## Executed proof and retained failures

- All508 original composed cases run on the new primitive too, with real guard
  admission/completion ordering assertions; original848 tests are untouched.
- Current bad stalled-word3 verdict: capacity remains1, actual ACK is0 while
  sticky reasons are still0. Raw bank VALID X at ACK and VALID1/X at release
  remain current vetoes. All70 product and75 raw-read bit corruptions execute.
- Exact current ACK orphan and post-ACK receipt capture/consume cases retain
  output/status/frame/input reasons. A private actor may advance on the new
  fault edge; emitted start/reuse stay blocked. This is not the P1 controller.
- Five forged-qualified cases reject capture and check exact reason-edge versus
  summary-edge timing. Unknown completion is tested only while references exist.
- Full-body fixed inverse patches restore both original primitive modules and
  the complete original848 fixture. Unreviewed body additions are rejected.
  Default-off and invalid0/1/X/Z parameter tests execute. Late exit0 ERROR and
  missing-count receipts are rejected;8 admissions/8 completions are required.
  Disabled-mode inertness refers to ownership/transfer controls, not every new
  observation port: current diagnostic exports may report hostile inputs even
  while disabled. The new ports remain unconnected to P1.
- The complete graph includes3302 nodes/36 LS nodes and has no cycle. Six
  independently restored backedges each fail: D0→guard current, D1→completed
  current, issuer6→bank live, reader offer→bank live, consumer certificate→shared
  current, full guard current→shared current. Qualified-capacity restoration is
  tested as a capacity-independence failure, not falsely claimed to form a cycle.

The old848 graph proof was INCOMPLETE:3123 nodes omitted36 LS nodes;3159 complete
nodes expose a cycle. Its historical848 behavioral PASS remains intact, but its
acyclic/composition claim is superseded. Full-parser rechecks still exclude the
raw offered-metadata driver from the four old ancestor cones (678/657/904/810),
without turning that into a safe-composition or physical claim.

Retained attempts under the persistent recovery parent:

- product-interface-v1.LqlAtZom:23PASS, incomplete first scope.
- product-interface-v2.py71kICc, original27971:54PASS/1 complete-graph FAIL.
- product-interface-partition-v1.CqrtfIrb,57430:39PASS/1 graph FAIL; whole-vector
  aggregate part-select still returned diagnostic dependencies in the
  conservative parser. Scalar sources fixed it; no parser relaxation.
- product-interface-partition-v2.WpC0Q16y,77082:40PASS/15deselected, repaired base.
- product-interface-partition-v3.0sr6A2kX,28341:587PASS/1 expected-marker mismatch.
  Missing-verdict mutant was killed by the earlier same-edge capacity/verdict
  assertion, not the anticipated later assertion. Only expected marker changed.
- product-interface-frozen848-repeat.zo6kcFgf,80521:848PASS17.96s.
- product-interface-partition-final-v1.dcLV5gFr,34799:1444PASS37.18s.

Parent's separately retained20PASS/structuralFAIL and original actual-READY gap
probes remain integration-gap evidence. No failure was overwritten. Ruff check
of the final frozen Python files reports one I001 import-order finding; no lint
PASS claimed and no post-test source formatting was performed.

## Cost and limits

No primitive register declarations were added: issuer93 + reader350 + bank317
=760 logical bits, plus the original single512×36 RAM. This excludes the real
guard/product and future controller/epoch barrier. It is NOT mapped area.
Healthy8jobs retain final product→seal2/publication3, completion→publication6,
publication→ACK10, ACK→first core2, final core→release1, contiguous512 core beats
(span511/no holes), and actor admission→release1555 clocks. Final READY hold4
adds4 clocks. These are synthetic raw-FFT actors with real guard/arithmetic,
not vendor FFT, actual-controller service, CDC, route or receiver proof.

Final netlist SHA82ce88dbbdcf84c23036806c3421419a50dd61ec0db0adb51df1df9549061608;
raw-metadata-free ancestor counts publication227/ACK413/core635/release542.
Procedural state is a graph cut; this is elaboration connectivity, not Boolean
reachability, synthesis timing or board evidence. Logical D0/D1 preconditions
are not established for arbitrary forced inconsistent interfaces.

Still required before top integration: independently bind expected job metadata
and a forward-admitted lease to the checked head (not two issuer aliases), real
controller receipt/start handling, and a fresh common epoch/paused-slow purge
barrier. Finite2-bit lease safety assumes all references drain; no arbitrary
stale-token wrap claim. CHECK_INPUT_BLOCK_IDENTITY(0) exists only in the bounded
prototype consumer and conveys no production exemption.

## Reproduce the frozen source tests

From this FW commit (including its HDL gitlink), run the following with a NEW
nonexisting --basetemp. No vendor tool is called:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH PYTHONDONTWRITEBYTECODE=1 \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest \
  tests/starlink_oracle/test_product_sealed_interface.py \
  tests/starlink_oracle/test_checked_product_read.py \
  tests/starlink_oracle/test_product_sealed_adapter.py \
  -q --tb=short -p no:cacheprovider --basetemp NEW_DIRECTORY/cases \
  --junitxml NEW_DIRECTORY/results.xml
```

New dependencies are `product_interface_graph.py`,
`product_interface_inverse/{reader,issuer,bench}.patch`, and the two named HDL
variants plus `tb/tb_starlink_pss_product_sealed_interface.sv` and
`tb/product_sealed_interface_cases.svh`. Existing helpers and canonical RTL
are inherited unchanged in this commit; tests freeze actual compiled sources.
Final raw pytest.log SHA b6ddc0eb08d0fe812a75d26ac170d56cc58a1813890cf37ce47357075a477d0d;
JUnit SHA bba1839511211e3abf5384b7765306415c8bf49f220d79d60b19ab4d14c0ca78.
