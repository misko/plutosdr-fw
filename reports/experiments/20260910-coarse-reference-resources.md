# Complete reference receiver resource inventory

Read-only Vivado 2022.2 audit of the final `18c96bb9` receiver checkpoint,
SHA256 `c7939197da381b66600aac228abdd87e20050e71d13903dbcd7abed36cec75b2`.
The audit finished successfully at2026-09-10T00:11:13Z and rechecked that the
input checkpoint was unchanged. The original receiver still fails200MHz timing;
this audit does not qualify it, alter constraints or implement a new design.

`20260910-coarse-reference-resources.tgz` retains the exact read-only script,
scope, complete hierarchy and six selected-subtree reports. No DCP or firmware
is in the archive. Original evidence directory:
`/tmp/starlink-idle-mailbox.N0l1fN/baseline-resource-audit-v1`.
Archive SHA256:
`fe7a8e01bc2bb64f3434e744f57157faf6b68d8a19fa0977dda33a0c7c0fb930`.
Scope SHA256:
`f9da204e44cc31d7bb37c91d95c9808f8aac3432b0c59d36b9b8a5b7f37703bb`.

## Measured coarse-engine costs

Values below are Vivado's hierarchical combined-LUT counts, not the larger raw
primitive counts in `scope.txt`. BRAM tiles count RAMB18 as one half.

| Subtree | LUTs | Registers | DSPs | BRAM tiles |
| --- | ---: | ---: | ---: | ---: |
| Entire IQ-to-score pipeline | 3674 | 6329 | 27 | 15.5 |
| Shared transform service, included above | 1490 | 3571 | 17 | 6.5 |
| FFT core, included in service | 1171 | 2988 | 17 | 5.5 |
| Input overlap scheduler | 190 | 404 | 0 | 2 |
| Template join/ROM | 49 | 224 | 0 | 0.5 |
| Spectrum multiplication | 104 | 277 | 4 | 0 |
| Intermediate transform FIFO | 107 | 83 | 0 | 2 |
| Window energy/cache | 371 | 427 | 2 | 2.5 |
| Candidate scoring/normalization | 1366 | 1198 | 4 | 2 |

Nested rows overlap. Cross-hierarchy LUT combining also means separate child
counts need not sum to the parent. Do not estimate exact replacement LUT/slice
savings by subtraction or add an isolated prototype to these counts and claim
the result will fit or route.

The coarse phase maps, outside IQ-to-score, use705LUT/740FF/20BRAM tiles.
The complete acquisition IP also includes sample CDC and AXI/stop controls.
The native fine tracker is separately13DSP/11BRAM tiles; pilot capture14DSP/4.5
BRAM tiles; pilot DMA1BRAM tile. Those required products remain in every full
receiver candidate.

## Implication for the parallel studies

FFT wrapper/control logic is relatively small in LUT count but is on critical
timing paths. Removing that complexity may improve timing without providing
a large area reduction. Conversely, normalization and map storage remain
material costs after replacing the FFT arithmetic. A direct correlator must
include its real history storage, sample acceptance, coefficient access,
normalizer and result/visit metadata before it can be compared with the whole
pipeline. A consolidated island must charge its outer CDC and all retained
local copies/ACKs. The canonical15 budget still requires one447-result block
every29.8us; short observed intervals are not worst-case guarantees.
