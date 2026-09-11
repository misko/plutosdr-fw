# Parallel product identity reference — DO NOT MERGE

This is an isolated actual-FFT/buffer timing experiment, not a deployed receiver.
Native 60 MS/s fine search and the independent 2.5 MS/s inspection stream remain
required and their receiver sources are unchanged.

## Change and contract

The product stage receives the held reference, retiring first-word reference and
first-word load selector separately. Two kept equality outputs are computed in
parallel; only their one-bit result is selected. The final `=== 1'b1` retains
known-only certification. This moves the late selector after equality without
adding a register, latency or a refill pause. The output stage is unchanged.
All 33 parent runtime modules remain byte-identical; two derived modules are
added. Current publication/fault checks, bank ownership, reset and scalar global
fault CDC are unchanged from the private-status parent.

The parent stage's header describes the old combined reference interface. In
this derived interface, the held reference is no longer externally multiplexed:
`retiring_metadata` and `reference_select` implement first-word write-through
inside the certificate expression. Neither reference grants publication.

## Verification

1,565 regression tests pass, including 21 new component/witness and 47 new
route-admission tests. The separate 12-test component rerun is a subset.
The new equality check compares the actual RTL expression with the old
wide-mux expression on 39,744 vectors: all 16,384 two-bit four-state combinations,
every physical bit with each selector and X/Z value, and 20,000 seeded random
vectors. Three deliberately broken expressions are rejected. The exhaustive
claim is limited to two-bit operands; full-width coverage is directed/random.

The real mailbox bench passes 12 good blocks / 6,144 reads, 420 bad metadata
cases, six bad framing cases and eight resets, with continuous first-word refill
and held-final-word checks. Five broken contract variants are rejected.
The first adapter run had six setup assertion failures because it looked for
an inline expression where the existing bench used a named reference wire.
The adapter and its nonfinal-capacity wiring were corrected; RTL was unchanged.
Both runs are retained.

The actual observer compares the new combinational certificate against the old
reference-mux expression every live fast-clock edge, and checks that certificate
is captured with each accepted word. Existing numerical, publication, private
status, reset and recovery observers remain enabled. No formal state-space or
RF accuracy proof is claimed.

Both actual generated FFT campaigns pass all 64,512 numerical-word comparisons
and retain 4,178 service clocks (23.874 us at 175 MHz, below 5,215 clocks).
All 54 inherited fault/reset/delay cases pass. The new actual observer checks
88,545 healthy cycles / 9,216 captures / 18 first-word refills, and 602,846
auxiliary cycles / 53,323 captures / 109 first-word refills. The complete CSV
hash is unchanged: `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
Synthesis passes with DCP `f8a2d0bcf4cecd5ddc5922af5fe3590ee4534fef982d4a23ba29daecfaa0ff3b`.

## Routed result and remaining work

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no timing
exceptions or clock relaxation. All 8,564 nets route without errors.

| Metric | Private-status parent | Parallel reference |
|---|---:|---:|
| WNS / TNS (ns) | -1.608 / -640.951 | -1.435 / -635.472 |
| Same-domain 175 MHz WNS | -1.608 ns | -1.255 ns |
| Failing setup endpoints | 1,344 / 14,519 | 1,175 / 14,505 |
| LUT / FF | 2,767 / 5,916 | 2,748 / 5,913 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Hold +0.043 ns and pulse +1.830 ns pass; there are no combinational/latch loops.
114 inputs and 124 outputs remain OOC-unqualified. CDC reports nine CDC-3 and
208 CDC-15, no CDC-10. The scalar fault register remains the direct synchronizer
source; the reset-release CDC uses a physical replica. This does not qualify
board clocks, metadata CDC or I/O.

Overall worst is output descriptor bit 1 crossing to slow metadata: -1.435 ns.
The worst 175 MHz path now runs from reset/release to product-stage occupancy,
through current guard/publication control: nine LUT levels, 6.966 ns delay,
77.433% routing. The second is engine metadata to output-stage occupancy
(-1.253 ns). Timing improves against the direct parent but is still failing;
this candidate is not promoted or deployable.

The corrected physical audit verifies two distinct kept comparison drivers,
each directly connected to the final LUT6 driving the certificate register.
Both equality cones retain carry cells; the late selector no longer precedes
those comparisons. The worst setup path to the actual certificate D pin is now
**+0.729 ns**, versus -1.608 ns in the parent, with 4.930 ns data delay. This is
a verified local endpoint improvement, not whole-subsystem timing closure.

Next investigate separating private held-final-word retirement from same-edge
public publication permission. Actual bank publication must retain every current
fault veto; private slot retirement can potentially consume a registered actual
publication receipt. Prove no duplicate final write/publication, premature slot
reuse, stalled nonfinal refill, stale reset data or service-budget regression.
Fault injection must stay aligned to actual bank publication, not a delayed
private retirement. Do not merely delay the public fault gate. The separate
metadata CDC and full receiver qualification gates remain open.

Routed DCP: `1983f6e9ddffc7348e886917c0b397fdf6ffd384b01673e577dbbfd545f2ad5f`.
Actual main/auxiliary runs took 53.266 / 235.636 s; synthesis 102.347 s and
routing 50.749 s. These are experiment runtimes, not a deployment ETA.

## Reproduction

Branch `codex/starlink-rx-only-do-not-merge-parallel-product-identity`.
Use `parallel_product_identity_experiment.py` for prepared source inventories,
actual FFT and synthesis, `route_parallel_product_identity.py` for source-matched
route admission, and `audit_staged_fft_route.py` for checkpoint/report auditing.
The separate `inspect_parallel_product_identity_v4.py` observes both kept
comparisons and the actual certificate endpoint without modifying constraints
or the routed checkpoint. Earlier observational queries are retained unchanged:
v1 could not follow hierarchical net drivers; v2/v3 incorrectly required the
old aggregate selector net to remain on a timed path after optimization. v3
revealed that both comparisons feed the final LUT directly while selector terms
are factored into that LUT. v4 verifies this connectivity and measures all paths
to the real certificate register, not an absent logical alias. The recording
helper archives failed observations as well as the corrected physical audit.

- Main source inventory: `d6aecbc1f27dc064cfcc5a97f80748938a2aa73579afdafd8c1d07312a725d80`.
- Auxiliary source inventory: `af96be709e0b3001d2d3177c42fa5fc622ba8fc97237476df10526e6eb4a31bc`.

Primary HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. No radios or PPU/main
are changed. Full receiver timing/CDC/reset, actual 60 MS/s calibration,
continuous RX and IIO/Ethernet remain release gates before reversible PPU
deployment to `.18`, then Ethernet-only `.17`. `.14/.20/.21` stay excluded.
