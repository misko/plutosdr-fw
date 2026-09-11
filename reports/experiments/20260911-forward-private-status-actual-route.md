# Private forward-bank status: functional pass, timing regression

**Do not promote or deploy this candidate.** The simpler registered private
status interface passes its functional gates, but the actual FFT/buffer
subsystem still fails timing, worse than the balanced parent.

The bank exposes its existing sticky fault register to private readiness and
quarantine. Immediate local rejection and explicit product/output publication
vetoes remain. No logical storage is added; physical replication changes the
register count. All 31 parent runtime modules remain byte-identical.

## Evidence

- **1,497 tests pass**, including 46 new component/witness and 39 route-admission
  tests. The initial 21 component elaboration failures were a missing testbench
  port wire; both failed evidence and corrected passing evidence are retained.
- Both actual generated FFT campaigns match **64,512 numerical words** and
  **4,178 service clocks**, unchanged from the parent.
- All **54 fault/reset/delay cases** pass (43 inherited, 11 new). The new
  observer checks 88,545 healthy and 602,846 auxiliary cycles, including 38 new
  fault edges, two same-edge private completions and 11 delayed guard responses.
  It verifies current publication fencing, registered reuse quarantine and
  bounded global fault propagation. Each new case resets and recovers 512
  correct fresh reads with one real release. This is not formal proof.

An independent bank fault can delay the guard by one edge and global fault
until the third rising edge from the original event. Same-edge private
completion is permitted before the bank register updates; ownership publication
is not. Reader-held cancellation tests do not claim withdrawal of earlier reads.

## Same-recipe routing

| Metric | Balanced parent | Private status |
|---|---:|---:|
| WNS / TNS (ns) | -1.420 / -420.378 | **-1.608 / -640.951** |
| Setup failures | 939 / 14,505 | **1,344 / 14,519** |
| LUT / FF | 2,805 / 5,912 | 2,767 / 5,916 |
| RAMB18 / DSP | 16 / 21 | 16 / 21 |

All 8,663 nets route; hold +0.053 ns, pulse +1.830 ns, zero routing errors and
zero combinational/latch loops. Same-domain 175 MHz WNS is also -1.608 ns.
No clocks or exceptions changed. 114 inputs and 124 outputs are still
OOC-unqualified. CDC reports nine CDC-3 and 208 CDC-15, no CDC-10; scalar global
fault remains the direct synchronizer source. Physical replicas include reset
release and output descriptor bit 3. Full-board qualification remains open.

Worst path: reset/release replica to product identity certificate, through
current fault, first-word metadata selection and equality: 7.088 ns, 12 logic
levels (six CARRY4), 69.454% routing. The next path is input-guard fault to
product-stage occupancy (-1.355 ns). Fewer LUTs did not improve timing.

Next test parallel comparisons against held/retiring-first-word metadata, then
select the one-bit result, keeping same-edge refill and X/Z behavior exact.
Prove the algebra and cancellation behavior before another actual FFT and
route campaign. Current publication vetoes must remain. Reset/fault fanout and
held-metadata CDC need separate physical qualification; no blanket waivers.

## Retained branch and artifacts

Branch `codex/starlink-rx-only-do-not-merge-forward-private-status`:

- FW `2ed44622334899f3d0586a5e28e9ceac32fb2511`.
- HDL `d3cc39201923ea915922ee43ee3515882f355757`.
- Main inventory `8470f72fc4ac863b35ce398bf55d559d88394bb7a2934a3527eb30678d5cb2cd`.
- Auxiliary inventory `5d9309f68caf4793e7dc23f86f600de78b36936d414ff8e5b6df5484cfd497f5`.
- Routed DCP `3ff64b28ed9298c55c7752add0c784f95178b8dd1cd2e53ebc2e46e051206f7d`.
- [Verified archive](20260911-forward-private-status-evidence.tgz): 16,109,372
  bytes / 15,649 members; SHA256
  `2e20a856312d5eb36f8ae8e1550e19c39770062455d0aeccaafd5345f5ce73c3`.
- [Archive receipt](20260911-forward-private-status-evidence.json).

The archive includes prepared sources, actual numerical streams, checkpoints,
raw timing/CDC reports, tests and the implementation note. Historical duplicate
regression CSV/DCP payloads remain local with a hash inventory.

Primary HDL stays `0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. Native 60 MS/s fine
and independent 2.5 MS/s inspection remain required, not removed. Full receiver
timing/CDC/reset, RX calibration, continuous reception and IIO/Ethernet must pass
before reversible PPU deployment to `.18`, then Ethernet-only `.17`.
No radios or PPU/main were touched. `.14/.20/.21` remain excluded.
