# Product retirement receipt: local timing closes, release still fails

The product occupancy endpoint improves from **-1.255 ns to +1.551 ns** at
175 MHz; product identity also passes at **+1.222 ns**. The actual FFT and
buffers retain exact arithmetic and service time. **Whole-subsystem timing
still fails; no promotion or deployment.**

## Implemented contract and tests

The existing registered bank request/ACK state authorizes private final-slot
retirement one healthy edge after actual publication. No register or bank/stage
RTL is added. Current bank authorization, framing and fault checks remain
unchanged; the old public eligibility expression still anchors fault injection.
Unknown ownership values do not authorize retirement. Nonfinal refill is
unchanged. Unpublished final RAM rewrites remain allowed while authority is
withheld; post-publication writes and duplicate publication are not.

All 35 parent runtime modules remain byte-identical, with one derived top added.
**1,646 tests pass**, including 26 new component/witness and 55 route-admission
tests. Coverage includes 1,024 four-state readiness/ownership combinations and
mutants. The real mailbox comparison passes 12 good blocks / 6,144 reads, 420
bad metadata cases, six framing cases and eight resets. This is not formal proof.

Both actual generated FFT campaigns match **64,512 numerical words** and retain
**4,178 service clocks / 23.874 us**, below 5,215 clocks at 175 MHz. The main
observer verifies 88,545 cycles, 18 bank publications and 18 receipt retirements.
All **59 fault/reset/delay cases** pass: 54 unchanged plus publication delay,
both resets during the extra hold, late fault and rejected final certificate.
The auxiliary observer checks 646,240 cycles, 100 publications / extra holds
and 98 retirements; the two pending-reset cases clear the other private holds.
Each new boundary recovers 512 correct fresh reads and one real release.

## Physical result

Same Vivado 2022.2 / xc7z010clg400-1 / 100–175 MHz OOC recipe, no exceptions
or clock relaxation. All 8,597 nets route without errors.

| Metric | Parallel-reference parent | Retirement receipt |
|---|---:|---:|
| WNS / TNS (ns) | -1.435 / -635.472 | -1.426 / -446.926 |
| Same-domain 175 MHz WNS | -1.255 ns | -1.348 ns |
| Failing setup endpoints | 1,175 / 14,505 | 839 / 14,510 |
| LUT / FF | 2,748 / 5,913 | 2,748 / 5,913 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

Independent endpoint inspection verifies the actual product occupancy D pin at
**+1.551 ns**, four LUT levels / 4.110 ns delay, and identity D pin at +1.222 ns.
The source/checkpoint-pinned probe measures existing paths and adds no waivers.

Overall worst is output-bank metadata bit 6 crossing into slow metadata.
The worst 175 MHz path now runs from engine metadata bit 45 through the forward
buffer's descriptor comparison/current fault into descriptor bit 42's clock
enable: six LUT levels, 6.809 ns, 79.528% routing. Aggregate timing improves,
but same-domain worst slack regresses. Local closure is not subsystem closure.

Hold +0.062 ns and pulse +1.830 ns pass; no combinational/latch loops. 114 inputs
and 124 outputs remain unqualified. CDC reports nine CDC-3 and 208 CDC-15,
no CDC-10. A physical replica of the scalar fault register directly drives its
synchronizer; it is not a post-register distributed OR. Full-board CDC remains
unqualified, including that replica and all held-metadata paths.

Next investigate separating private descriptor capture from current-fault logic
on its load enable. Preserve same-edge state/fault/publication behavior, and
prove any descriptor changed on a quarantining reservation edge stays unusable
until fresh reset. Test simultaneous reserve/fault and X/Z, current controls,
valid payload and actual reset/recovery before another route.

## Retained checkpoint

Branch `codex/starlink-rx-only-do-not-merge-product-retirement-receipt`:

- FW `1be34b17b339b5c3d136fe778ddda23be2e30a0f`.
- HDL `32a267dcc1ab5c16782fb59f5d310f2a5b6a9525`.
- Main inventory `40dbfcc7a30e1d66f0c4e1319a4d5ac5dd1dd9b29f0b3e14e2c64bc570d74e48`.
- Auxiliary inventory `654205f6ad1a1b321e451fb5339c743de5b00f7e2737f775764b0f715f7b1622`.
- Routed DCP `74f86e9edbaaf1ec864c27f5454493712ce75633bd4898489f07717860e873b8`.
- [Verified archive](20260911-product-retirement-receipt-evidence.tgz): 16,588,807
  bytes / 25,136 members; SHA256
  `2fcb784b3670eb5e16c7c06470859f88af8c7430190b3b3faf3e6528b30e8b77`.
- [Archive receipt](20260911-product-retirement-receipt-evidence.json).

Primary HDL remains `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Native 60 MS/s
fine search and independent 2.5 MS/s inspection remain required and unchanged.
Full receiver timing/CDC/reset, actual calibration, continuous RX and real
IIO/Ethernet must pass before reversible PPU deployment to `.18`, then
Ethernet-only `.17`. No radios or PPU/main were touched; `.14/.20/.21` stay excluded.
