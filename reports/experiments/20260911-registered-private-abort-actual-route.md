# Registered private abort: actual FFT and routed result

**Timing still fails. No deployment or primary HDL promotion.**
No radios or PPU were accessed; `.14`, `.20`, `.21` remain excluded.

The separately derived top removes direct `result_fault` from two private abort
inputs, retaining the scalar registered global abort and immediate current
publication/admission vetoes. All 26 parent runtime modules are unchanged.
Any extra private work on the intervening edge must remain unpublished.

## Verified evidence

1,241 distinct tests pass: 1,226 regression (1,200 inherited + 26 new
transform/witness cases), plus 15 route-admission unit tests. Those admission
tests isolate receipt/source matching; they are not actual arithmetic tests.

Both actual generated FFT campaigns match 64,512 numerical words across seven
streams. Service remains 4,178 clocks / 23.874 us at 175 MHz, below 5,215 clocks.
This is subsystem service evidence, not continuous native RX proof.

Auxiliary tests retain all 25 previous fault/reset/delay cases and add six
direct guard-fault boundaries: forward capture/replay, inverse output, final
publication and both completions. The monitor observes one additional private
capture and two private bank writes, with no new publication or reuse, and
512 correct fresh reads / one real reader release after each recovery. It
checks immediate publication vetoes and next-edge global fault/ownership on
1,768 fault edges. Existing published data during fault CDC propagation is
distinguished from a new publication; the reader is held during cancellation.

## Route comparison

Same source-matched Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe;
no new exceptions or relaxed clocks.

| Metric | Output identity parent | Registered private abort |
|---|---:|---:|
| WNS / TNS | -1.406 / -324.725 ns | -1.414 / -321.485 ns |
| Setup failures | 763 / 14,471 | 653 / 14,439 |
| 175 MHz same-domain WNS | -1.406 ns | -1.357 ns |
| LUT / FF | 2,712 / 5,891 | 2,705 / 5,878 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

All 8,517 nets route; hold +0.032 ns and pulse +1.830 ns have no failures.
114 inputs and 124 outputs remain OOC-unqualified. CDC reports nine CDC-3 and
208 CDC-15 warnings, with no CDC-10. The scalar fault register remains the
direct source of its two-stage synchronizer. Full CDC signoff remains open.

Worst overall is held output metadata crossing 175 to 100 MHz: zero logic,
1.068 ns data delay and 0.002 ns inherited edge requirement. It needs actual
mailbox ownership/constraint qualification, not a blanket exception.
The genuine same-clock failure is reset release into the global fault register,
through input/current-fault and guard logic: eight LUT levels, 7.018 ns data
delay (79.367% routing). Forward descriptor into guard ACK also fails -1.156 ns.

Next trace and budget a registered private-fault summary while preserving
immediate public vetoes, common reset and the scalar CDC source. Separately
qualify held-data crossings and physical replicas. Both timing areas must be
resolved; endpoint-count reduction alone is not timing closure.

## Pinned branch and archive

Branch `codex/starlink-rx-only-do-not-merge-registered-private-abort`:

- FW `a069a0ccb6ae6d2d4908933fdd079bf8c03823a6`.
- HDL `338dbec0e61f46934f68d25f499d18bc77b0b1ee`.
- Main source inventory `23098219271638ad765ab8ebb5816baff0c5c62dd63d5c5cbffb3eb97d7c8d1e`.
- Auxiliary inventory `7d76620275271e558b4e8483dc77e39a4178cd6b6f7834cd4f6ef454fa6e2281`.
- Actual CSV `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
- Routed DCP `1cc49e7bdbd7515778014840f29c48789d9d2622a9afa7b9f059ea70eb746559`.
- [Read-back verified archive](20260911-registered-private-abort-evidence.tgz):
  15,501,538 bytes, 7,731 members, SHA256
  `d1f6e0aff23e6962df0aa98283b56d5ea8e35996dbbb0cb4b6f35d2dffd9dab9`.
- [Archive receipt](20260911-registered-private-abort-evidence.json).

Archive includes prepared sources, complete current actual streams/logs,
generated FFT wrappers, both checkpoints, raw reports and tests. Historical
regression CSV/DCP duplicates remain local with a SHA inventory.
Primary HDL stays `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`.
Full receiver integration must preserve native 60 MS/s fine and independent
2.5 MS/s inspection; real clock/CDC/reset signoff, 60 MS/s calibration,
continuous RX and IIO/Ethernet are required before pinned reversible PPU
deployment to `.18` canary, then `.17` over Ethernet.
