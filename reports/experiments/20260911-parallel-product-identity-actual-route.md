# Parallel product reference: targeted timing path closes, release still fails

The product identity certificate endpoint improves from **-1.608 ns to
+0.729 ns** at 175 MHz. Physical inspection verifies two kept comparisons
feeding one final selection LUT directly. **The subsystem still fails timing;
no full-receiver promotion or deployment.**

The old 70-bit reference mux followed by equality is replaced with two parallel
comparisons and a one-bit selection, retaining known-only certification. No
register, service cycle or refill pause is added. Both unmuxed references and
the actual first-word load selector feed the derived product stage; the output
stage is unchanged. All 33 parent runtime modules remain byte-identical.
Current fault/publication gates, bank ownership and reset are unchanged.

## Functional and physical evidence

**1,565 distinct tests pass**, including 21 new component/witness and 47
route-admission tests. The 39,744-vector algebra campaign covers all 16,384
two-bit four-state combinations, every physical bit with each selector/X/Z and
20,000 seeded random vectors. Three broken expressions are rejected. Full-width
coverage is directed/random, not exhaustive formal proof.

The real mailbox bench verifies 12 good blocks / 6,144 reads, 420 bad metadata
cases, six bad framing cases and eight resets. Five unsafe variants are rejected.
An initial six-case adapter setup failure was corrected without changing RTL;
failed and passing evidence are both retained.

Both actual generated FFT campaigns match **64,512 numerical words**, unchanged
CSV SHA `df33d4b05c4ae65191af85f9e6748a484773d0a659051a5fad7112b8a717d8c8`.
Service remains **4,178 clocks / 23.874 us** at 175 MHz, below 5,215 clocks.
All **54 inherited fault/reset/delay cases** pass. The new actual observer checks
88,545 healthy cycles / 9,216 captures / 18 first-word refills and 602,846
auxiliary cycles / 53,323 captures / 109 first-word refills.

The corrected netlist audit follows hierarchical net segments, verifies two
distinct comparison drivers directly feeding the final LUT6 and measures all
paths to the real certificate D pin: worst setup **+0.729 ns**, data delay
4.930 ns. Equality carry chains remain, but the late selector no longer precedes
them. The optimizer factored selector terms into the final LUT, so earlier
queries requiring the original aggregate selector net on a path were rejected.
All three rejected observations and the corrected fourth audit are preserved;
no checkpoint or constraint was changed to obtain the result.

## Whole-subsystem result

| Metric | Private-status parent | Parallel reference |
|---|---:|---:|
| WNS / TNS (ns) | -1.608 / -640.951 | -1.435 / -635.472 |
| Same-domain 175 MHz WNS | -1.608 ns | -1.255 ns |
| Failing setup endpoints | 1,344 / 14,519 | 1,175 / 14,505 |
| LUT / FF | 2,767 / 5,916 | 2,748 / 5,913 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Same 100/175 MHz OOC recipe; all 8,564 nets route. Hold +0.043 ns and pulse
+1.830 ns pass, with zero routing errors and no combinational/latch loops.
114 inputs and 124 outputs remain unqualified. CDC reports nine CDC-3 and
208 CDC-15, no CDC-10; scalar global fault remains the direct synchronizer
source, while reset release uses a physical replica. Full-board signoff is open.

Overall worst is descriptor bit 1 crossing to slow metadata (-1.435 ns).
The worst same-domain path is reset/release through current guard/publication
control into product-stage occupancy: nine LUT levels, 6.966 ns, 77.433% routing.
Next is engine metadata into output-stage occupancy (-1.253 ns).

Next investigate retiring a private held-final slot from a registered actual
publication receipt, while retaining every same-edge public fault veto. Prove
no duplicate final write/publication, premature reuse, nonfinal refill stall,
reset leakage or service-budget regression. Inject faults at actual bank
publication, not delayed private retirement. Separate metadata CDC and full
receiver physical qualification remain required; no blanket timing waivers.

## Retained checkpoint

Branch `codex/starlink-rx-only-do-not-merge-parallel-product-identity`:

- FW `25d6ec8a7e08fa54b85c926a19d9a7412025265e`.
- HDL `d41ed450e22e22d82c711429c1fe015b49bb84f0`.
- Main inventory `d6aecbc1f27dc064cfcc5a97f80748938a2aa73579afdafd8c1d07312a725d80`.
- Auxiliary inventory `af96be709e0b3001d2d3177c42fa5fc622ba8fc97237476df10526e6eb4a31bc`.
- Routed DCP `1983f6e9ddffc7348e886917c0b397fdf6ffd384b01673e577dbbfd545f2ad5f`.
- [Verified archive](20260911-parallel-product-identity-evidence.tgz): 16,328,542
  bytes / 19,912 members; SHA256
  `7ff04eab43aa912f131c93ae82b4eda401994ddb3eba4354c07b684b90e9e613`.
- [Archive receipt](20260911-parallel-product-identity-evidence.json).

Primary HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Native 60 MS/s fine
search and independent 2.5 MS/s inspection remain required and unchanged. Full
receiver timing/CDC/reset, RX calibration, continuous reception and IIO/Ethernet
must pass before reversible PPU deployment to `.18`, then Ethernet-only `.17`.
No radios or PPU/main were touched; `.14/.20/.21` remain excluded.
