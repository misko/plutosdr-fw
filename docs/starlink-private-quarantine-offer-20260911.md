# Private quarantine offer — DO NOT MERGE or deploy

## Decision

The opt-in private buffer offer is implemented, tested with the actual FFT and
buffers, and routed. It improves the targeted inverse-guard fault/commit path
from -1.235 to -0.292 ns, but the whole design regresses from -1.241 to -1.322 ns
WNS. Keep this as an experimental result, **not a promoted receiver candidate**.
The quiet-publication parent remains the better overall routed reference.

Both FW and HDL branch:
`codex/starlink-rx-only-do-not-merge-private-quarantine-offer`.
Parent FW `d146246cd01446b3dd30d1008e7b725b7f2edc80`, HDL
`587c2dd5302e991ac46e58e6cb2f765dd6cc3c32` remain pinned.

## Change and contract

The previous path traversed sticky guard fault reasons, masked active/return
validity, private output-bank framing and shared fault feedback before reaching
the guard's public commit. Only the inverse guard's **private write offer** now
uses reset plus raw active/return occupancy. Public valid, final commit, ACK,
fault reason accumulation, admission and state transitions stay literal.

Hidden occupancy may survive one cycle after a registered fault; this may cause
an extra write into an unpublished bank. It is never permission to publish.
The caller must use exclusively owned explicit-commit RAM, independently fence
publication with sticky/current faults, and purge the common epoch before reuse.
This output must not drive a publish-on-final legacy mailbox.

The option defaults off. Only the inverse guard opts in; the top-level profile
requires the tested quiet replay publication mode. Unknown/unsupported modes
are rejected. No new arithmetic, RAM, clocked state or latency is added. Two of
22 compiled runtime modules change. Forward guard and buffer implementations
remain unchanged. Default mode has an exact source inverse to the parent.

## Tests and actual behavior

- Eleven new component/source tests: exact source delta; full old/new guard
  comparison in both modes; 32 directed fault/recovery jobs plus randomized
  traffic (8644 checks/mode, 70 private differences in opt-in and zero in default);
  256 four-state combinations/mode; unsupported modes rejected; reset, occupancy
  and public-output mutants rejected. Public/reference comparison uses identical
  live inputs, not an independent full receiver with separate feedback.
- Thirteen focused component/lint tests pass in 0.34 s.
- Full regression V1: 837 pass, one historical source-inventory failure. Its
  comparison had not undone the new guard option; corrected using the separately
  tested exact source inverse. Fresh full V2: **843 pass in 92.50 s**.
- Ten new actual-evidence/configuration tests and seven existing archive tests
  pass in 1.83 s: **853 distinct regression/evidence tests**, not 860.
- Main actual FFT PASS in 201.190 s; auxiliary PASS in 187.135 s. All 64512
  numerical records and CSV bytes match the parent. Service clocks remain
  `3663/3663/4929/11729/3663/3663`.
- Actual private-offer monitor: main 500645 checks / one differing cycle;
  auxiliary 435366 checks / two differing cycles. Every difference occurs with
  known inverse sticky fault, no public valid, commit, replay acceptance, ACK
  or new admission. Existing fault/reset/recovery tests remain passing.
- The existing original-guard monitor still compares public and diagnostic
  outputs. Only the intentionally changed private valid moves to its dedicated
  monitor; no public field is removed. Main metadata live-write observations
  increase by one, as expected for the private-only faulted write.
- Synthesis PASS in 99.209 s; route execution PASS in 46.427 s. Setup still FAIL.

These are bounded simulation and extracted algebra checks, not a universal
formal proof. No actual radio reception or continuous RX qualification is claimed.

## Route under unchanged constraints

| Metric | Quiet-fence parent | Private-offer candidate |
| --- | ---: | ---: |
| WNS, ns | -1.241 | -1.322 |
| TNS, ns | -274.139 | -323.338 |
| Setup failing endpoints | 572 | 622 |
| LUT / FF | 2825 / 5796 | 2808 / 5796 |
| DSP / RAMB18 | 21 / 15 | 21 / 15 |

All 8460 routable nets route without errors. Hold +0.071 ns, zero failures;
pulse 1.830 ns, zero failures. Original 100/175 MHz OOC clocks and routing recipe
are unchanged, without new false-path or multicycle exceptions.

Read-only exact endpoint queries from inverse guard `fault_reasons_reg[3]/C`:

- Guard `commit_pulse_reg/D`: -0.292 ns (parent -1.235).
- `fast_fault_reg/D`: -0.444 ns (parent -1.228).
- Output-bank `request_toggle_reg/D`: -0.054 ns; no parent value claimed here.

The new worst is product-bank held metadata bit 34 through preflight identity
comparison into `fast_fault_reg/D`: -1.322 ns, eight logic levels, 6.984 ns data
delay, of which 5.536 ns is routing. Another near-critical path is reset readiness
to the kernel ROM output-valid register at -1.318 ns. Neither is solved by
removing TX or by waiving metadata CDC checks.

Reset structural checks retain clean synchronizer first-stage fanout and the
registered purge source. CDC inventory is unchanged: nine CDC-3 informational
items and 208 CDC-15 warnings. OOC inputs/outputs remain unqualified (114/124).

## Next decision and deployment gates

Keep both routed candidates. Before another RTL change, inspect the preflight
identity and reset-to-ROM-valid cones together; account for phase/lease ownership
and any old output still being read during next-job preflight. A stale identity
certificate or delayed current cancellation is not a valid timing fix. Test a
local held-lease certificate or private preflight stage against the exact current
admission/publication semantics before integrating and routing it.

The deployment goal is unchanged: native 60 MS/s fine search plus independent
2.5 MS/s CI16 IIO inspection, full receiver timing/CDC/reset and real board clocks,
actual 60 MS/s RX calibration, sustained Ethernet/IIO, blind host GLRT comparison,
120 ms dwells and 300 s scanning. Only after those gates: pinned PPU package with
rollback, .18 canary, then .17 PPU Ethernet-only deployment. No radios, PPU/main,
primary receiver HDL, clock constraints or TX functionality changed here.

Prepared SHA256:
`2f518556a5e04dc9e161aff35d3c079914a1ecb9d6d7ffb1c6d8064b5337fb25`.
Synthesized DCP: `f2da5f222b32158f67bb8ba19b079f42862da6aac7f902657c8af710e990da40`.
Routed DCP: `b31f03b331729ee00058e17169667ac8fffd84a161c62fe32848cb1d00aa7faf`.
CSV: `7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d`.

`tools/record_private_quarantine_evidence.py` binds exact sources, actual outputs,
test XML, synthesis/route and inspection receipts. The archive is read-back
verified member by member; raw evidence remains in
`/dev/shm/starlink-private-quarantine.tu8FkVR0`. Initial failed source-comparison
evidence is retained along with the successful fresh regression.
