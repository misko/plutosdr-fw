# Registered private abort — 2026-09-11

Branch `codex/starlink-rx-only-do-not-merge-registered-private-abort`.
DO NOT MERGE firmware/HDL into main. **Timing fails; do not deploy.**

## Change and contract

Derive one new top from the output-identity candidate. All 26 parent runtime
modules remain byte-identical. The only behavioral changes remove the direct
registered guard `result_fault` term from two private abort inputs: the forward
return bank and inverse-output identity stage. They still see the original
scalar registered `fast_fault`; the output stage also retains its local fault
checks. The exact three-site transform includes the module rename.

Current product/output publication vetoes, job/completion admission vetoes,
guard diagnostics, global fault capture, reset and the direct scalar fault CDC
source remain unchanged. A newly latched guard fault can permit one additional
edge of private work before global abort. This is intentionally not cycle-exact
private diagnostic equivalence. It must not permit a new public ownership
transfer, reuse or contaminated recovery.

Native 60 MS/s fine-search and independent 2.5 MS/s inspection receiver sources
are unchanged. This is the actual FFT/buffer subsystem, not receiver integration.

## Verification

**1,241 distinct tests pass:** 1,226 regression (1,200 inherited plus 26 exact
transform/witness checks), and 15 route-admission unit tests. The latter mock
older arithmetic/source-check machinery to isolate new evidence admission;
they are not another actual-FFT run or physical proof. They reject absent,
failed or mismatched abort receipts, differing runtime modules and incomplete
private-work/publication/recovery witnesses. Inherited component tests do not
constitute exhaustive fault coverage of this newly derived top.

Both actual generated FFT campaigns match **64,512 numerical words** against
the frozen original reference, with identical CSV hash to the output-identity
parent. All six healthy contexts retain **4,178 service clocks**, 23.874 us at
175 MHz, below 5,215 clocks / 29.8 us. Continuous RX is not established.

The main observer sees 88,545 fast cycles and no faults. Auxiliary sees 383,951
cycles and 1,768 guard-fault edges, including **one additional private forward
capture and two private output writes** before the registered global abort.
Each fault edge checks immediate publication/admission vetoes and next-edge
global fault plus unchanged product/output ownership toggles.

The auxiliary campaign retains the previous six forward faults, eight reset
boundaries, two delay cases and nine output-identity cancellation cases. Six
new cases force a guard's latched fault during forward capture, forward replay,
inverse output, final publication, forward completion and inverse completion.
All prevent new publications and recover with 512 fresh correct reads and one
actual reader release. Reader is held during cancellation. Previously published
good data can remain visible during existing fault CDC latency; that is not a
new publication, and the test explicitly distinguishes those conditions.

The inherited actual output identity observer checks 9,216 main / 29,997
auxiliary private bank writes, 18 / 55 finals and 18 / 61 first-word refills.

## Routing: small mixed change, not closure

Exact tested/synthesized source; unchanged Vivado 2022.2 / xc7z010clg400-1 /
100–175 MHz OOC recipe. No new timing exceptions or relaxed clocks.

| Metric | Output identity parent | Registered private abort |
|---|---:|---:|
| All-path WNS | -1.406 ns | -1.414 ns |
| All-path TNS | -324.725 ns | -321.485 ns |
| Setup failing endpoints | 763 / 14,471 | 653 / 14,439 |
| 175 MHz same-domain WNS | -1.406 ns | -1.357 ns |
| LUT / FF | 2,712 / 5,891 | 2,705 / 5,878 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

All 8,517 nets route, with zero routing errors. Hold +0.032 ns and pulse
+1.830 ns have zero failures. 114 inputs / 124 outputs remain OOC-unqualified.
CDC reports nine CDC-3 and 208 CDC-15 warnings, no CDC-10. The parent's two
extra replicated metadata destinations are absent; bundled-data qualification
is still required, not waived.

The all-path worst is output-bank metadata bit 27 crossing 175 to 100 MHz:
zero logic levels, 1.068 ns data delay, 0.002 ns inherited edge requirement.
It must be assessed using the actual mailbox ownership protocol and real clock
constraints, not treated as an ordinary combinational controller path or hidden
with a blanket exception.

The genuine same-domain worst is `epoch_barrier/fast_release_reg/C` to
`fast_fault_reg/D`, through input-check/current-fault and guard logic: eight
LUT levels, 7.018 ns data delay, 79.367% routing. Another reported path is the
forward descriptor into guard acknowledgment (-1.156 ns). Removing the two
private abort terms does not resolve those remaining control dependencies.

## Next engineering gate

Preserve both candidates; do not claim overall timing improvement from endpoint
count alone. Trace the reset/current-fault cone into the scalar global register.
Budget a local registered private-fault summary only if current public fault
vetoes, next-cycle cancellation, real completion/reader ACK and common reset can
be independently proved. Keep the scalar registered CDC source; do not recreate
the rejected combinational OR before its synchronizer. Separately qualify the
held-data mailbox crossing and all physical replicas with ownership assertions
and actual board clocks. Same-domain timing must pass regardless of CDC work.

Then repeat actual arithmetic/cancellation/service tests and unchanged route,
integrate the full receiver with native fine and inspection preserved, close
board timing/CDC/reset, verify 60 MS/s calibration, continuous RX and sustained
IIO/Ethernet, and only then use pinned reversible PPU deployment: `.18` canary,
then `.17` outdoors over Ethernet. No radio, PPU or main branch was touched;
`.14`, `.20`, `.21` remain excluded. Primary HDL pointer is not promoted.

## Source and artifact identities

Evidence root: `/dev/shm/starlink-registered-abort.CFsRfq40`.

- Main inventory: `23098219271638ad765ab8ebb5816baff0c5c62dd63d5c5cbffb3eb97d7c8d1e`.
- Auxiliary inventory: `7d76620275271e558b4e8483dc77e39a4178cd6b6f7834cd4f6ef454fa6e2281`.
- Actual CSV: `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
- Synthesized DCP: `c9fe4ee263b6163d065235d9915283ca1f9e9c0fa8dc117aceb1e94ce4fb4ff5`.
- Routed DCP: `1cc49e7bdbd7515778014840f29c48789d9d2622a9afa7b9f059ea70eb746559`.

Tools: `registered_abort_experiment.py`, `route_registered_abort.py`,
`audit_staged_fft_route.py`, `record_registered_abort_evidence.py`.
Retain prepared sources, actual streams/logs, generated FFT wrappers, both
checkpoints, raw routing reports and tests in a read-back verified archive.
