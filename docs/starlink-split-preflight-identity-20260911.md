# Split preflight identity — DO NOT MERGE or deploy

## Outcome

Compare source/product metadata before selecting their one-bit equality result.
The actual FFT/buffer implementation passes behavioral tests and routing, and the
previous metadata-bit-34-to-fast-fault path improves **-1.322 to +0.052 ns**.
Its logic depth falls from eight to six levels. Overall fast-domain WNS improves
to -1.037 ns, but setup still fails. Global worst is an unqualified metadata CDC
path at -1.373 ns. This is progress toward closure, not a deployed receiver.

FW/HDL branch `codex/starlink-rx-only-do-not-merge-split-preflight-identity`.
Parent FW `212da887106bbebdf20eb08bfe80661dc3e2d46e`, HDL
`f0cedf13dfe0cbd6f0b4a5e309ad95d47b53d418` remain pinned.

## Exact scope

`SPLIT_PREFLIGHT_IDENTITY=0` retains the original expression. Opt-in mode requires
registered scheduling and compares each fixed bank against the held engine
descriptor using balanced small equalities. Phase selects only the comparison
result. The second engine-versus-expected-product comparison is unchanged.

X/Z selection does not distribute through equality: selecting between vectors
0 and 3 with expected 1 yields unknown, while selecting their equality results
would incorrectly yield false. Unknown phase therefore retains the exact
original merged-vector comparison. Default and four-state behavior are tested.

Only the top changes among 22 runtime modules. No register, latency, clock,
buffer, arithmetic, lease state, fault gate or public cancellation rule changes.
There is no stale certificate and no delayed current-fault observation.
Both actual simulation and synthesis enable the same option; route gates reject
missing or mismatched evidence. All prior opt-ins remain pinned to the parent.

## Verification

- 21 new component/source tests, including twelve 8578-case comparisons across
  default/registered/opt-in profiles and four seeds, every bit of all four
  metadata vectors, all phase values, random traffic, invalid modes, and four
  rejected unsafe comparators. The component/lint subset is 23 tests (1.92 s).
- **874 full regression tests pass**, 101.29 s. Ten new actual-evidence tests
  pass with seven overlapping archive tests (17 total, 2.16 s): **884 distinct**.
- Main actual FFT PASS, 206.461 s; auxiliary PASS, 181.339 s. All 64512 indexed
  numerical records and CSV bytes match the parent exactly. Service clocks
  remain `3663/3663/4929/11729/3663/3663` across six contexts.
- Main current-equality witness: 500645 checks, including 570 source and 622
  product preflight observations. Auxiliary: 435366 checks, including 368 source
  and 584 product observations. Existing corrupted metadata, admission, pending
  publication, reset, stopped-reader and fresh recovery tests stay passing.
- Synthesis PASS, 99.422 s; route execution PASS, 46.818 s; setup FAIL.

This is bounded simulation plus source-extracted combinational checks, not a
universal formal proof, native timing-accuracy measurement or continuous RX test.

## Physical results under unchanged constraints

| Metric | Private-offer parent | Split preflight |
| --- | ---: | ---: |
| Global WNS, ns | -1.322 | -1.373 |
| TNS, ns | -323.338 | -292.853 |
| Setup failing endpoints | 622 | 580 |
| Same-domain 175 MHz WNS, ns | -1.322 | -1.037 |
| LUT / FF | 2808 / 5796 | 2758 / 5793 |
| DSP / RAMB18 | 21 / 15 | 21 / 15 |

The earlier quiet-fence candidate remains -1.241 global WNS / -1.235 same-domain
WNS / 572 failing endpoints. Keep all three; there is no overall signoff winner.
The split candidate improves the fast-domain logic but does not qualify the CDC.

8457 routable nets fully route with zero routing errors. Hold +0.062 ns and
pulse 1.830 ns pass. The original 100/175 MHz OOC constraints and route recipe
are unchanged, without new false-path or multicycle exceptions.

Exact previous endpoint queries:

- `product_bank/metadata_out_hold_reg[34]/C` to `fast_fault_reg/D`: +0.052 ns,
  six levels, 5.607 ns data delay (4.271 ns routing), versus -1.322 ns previously.
- `fast_reset_fast_reg[1]/C` to `joiner/kernel_rom/output_valid_reg/D`:
  -0.760 ns, versus -1.318 ns previously.

Remaining worst fast-domain path is `fast_reset_fast_reg[1]/C` to
`output_bank/request_toggle_reg/D`: -1.037 ns, nine levels, 6.698 ns data delay
(5.126 ns routing). Global worst is held output metadata bit 6 crossing 175 to
100 MHz: -1.373 ns, zero logic levels, 1.076 ns data delay.

Reset structural checks still pass. CDC is **nine CDC-3 information items and
209 CDC-15 warnings**, up one warning. The added endpoint is the synthesized
`source_bank/metadata_out_hold_reg[6]_replica/D`; output metadata bit 5 also uses
the original source register rather than its prior replica. Both physical
implementations need bounded-data CDC qualification; the extra warning is not
silently dismissed. OOC ports remain unqualified: 114 inputs and 124 outputs.

## Next bounded implementation step

Inspect the reset barrier's outer-running conjunction. Hypothesis: within the
actual top's common epoch, the registered fast-release receipt already implies
outer-fast-running, and its slow synchronized receipt implies outer-slow-running.
Their reset synchronizers are monotonic while both raw resets stay released.
If established, a caller-specific opt-in could remove that redundant combinational
reset-readiness dependency without delaying reset assertion or adding latency.

Prove this first against the exact top/barrier with reset assertion, release,
stopped clocks, unknown reset values and all ownership states. Preserve raw
asynchronous cancellation and generic default behavior. Do not treat the
implication as valid for arbitrary external outer-running inputs. Then integrate,
rerun actual FFT and route before features. Separately qualify held metadata CDC
with ownership/ACK lifetimes and justified physical delay/skew bounds.

Deployment still requires native 60 MS/s fine search plus independent 2.5 MS/s
CI16 IIO inspection, full receiver timing/CDC/board clocks, actual 60 MS/s RX
calibration, continuous RX and sustained Ethernet/IIO, blind GLRT comparison,
120 ms dwells and 300 s scans; then pinned PPU firmware/rollback, .18 canary and
.17 Ethernet-only deployment. No radios (including .20/.21), PPU/main, primary
receiver HDL or TX functionality changed.

Prepared SHA256:
`1bf6ac30a6f5e3ee45b5cf489d1adecaeef08ab8ecc93495c6281fff035293c1`.
Synthesized DCP: `62acd2aee9b79e3eeca840282b00be84d7fb145ce39e3ec29c85ca04bf52f565`.
Routed DCP: `1f999a60e7f35e0ffddc8dd09ce7dcfb9c9213a733fb853bd3a983c9939865c5`.
CSV: `7bb1a5ce3270d8bff21ff0f0d24d9a83a759f263a871abab509b9d8276b6782d`.

Evidence is bound by `tools/record_split_preflight_evidence.py` and archived with
member-by-member read-back verification. Raw evidence remains under
`/dev/shm/starlink-split-preflight.2BQ3zjL5`.
