# Parallel kernel READY: integrated and tested, physical regression

DO NOT MERGE or deploy. FW/HDL branch:
`codex/starlink-rx-only-do-not-merge-parallel-kernel-ready`.
FW `11b374d18e7c6b64af2806fa45987b803c1970e5`;
HDL `36ce5b2f9feb10c37811a333430cf06ff031ec1d`. Both pushed.

## Implemented and verified

The arithmetic/operand modules export their current owning occupancy through
explicit ports. The top combines that with the private product slot's existing
capacity, fault and final-word conditions. An opt-in kernel READY calculation
uses the parallel result, while retaining reset/flush/protocol-fault fencing,
unknown-reset fallback and original output-stage enables. Defaults stay unchanged.
The guard remains connected to the authoritative kernel READY; no independent
fault summary replaces it. Numerical arithmetic, pipeline storage, publication
and guard wiring reconstruct exactly to the parent after removing the additions.

Five of 22 runtime modules change. The two additive arithmetic copies come from
the hash-locked baseline; the baseline itself is unchanged. Runtime uses no
hierarchical observation references.

**988 distinct tests pass:** 971 regression, six extra four-state tests and eleven
actual-evidence/profile checks. Original-ROM equivalence covers valid lookups,
malformed inputs, stalls and flush. False capacity and missing reset/fault/flush
fences are rejected. A first mutation harness ambiguously matched both branches;
only the test targeting was corrected, with both artifacts preserved.

Both actual generated-FFT campaigns pass. All 64,512 indexed numerical records
and CSV bytes match the parent. Service remains `3663/3663/4929/11729/3663/3663`
clocks. Port/selected-READY witnesses cover 503,564 main and 437,625 auxiliary
observations. All original direct-ready, forced-valid, summary-bit, cancellation,
publication and recovery tests remain unchanged and pass.

## Routed result — reject promotion

| Metric | Monotonic-reset parent | Parallel READY |
| --- | ---: | ---: |
| Global WNS, ns | -1.399 | -1.434 |
| Same 175 MHz domain WNS, ns | -1.324 | -1.434 |
| TNS, ns | -250.635 | -302.161 |
| Failing setup endpoints | 446 | 590 |
| LUT / FF | 2739 / 5787 | 2729 / 5788 |

The exact release-to-fast-fault cone improves to −0.774 ns, but the new worst
is release→kernel protocol-fault, −1.434 ns. It passes through product-bank
readiness, parallel capacity, kernel READY, the forward guard, and kernel
input-accept: twelve logic levels, 7.096 ns data delay, 5.090 ns routing (71.7%).
The running net in this path has 2160 fanout. This is not a timing-closure result.

Vivado replicated the release register. Queries from only the original register
find no paths to the old endpoints; replica-aware queries prove they remain:
fast-fault −0.774, ROM-valid −0.867 and output-request −0.616 ns. The old product
metadata bit 34 to fast-fault path passes at +0.352 ns. No path-removal claim is
made from the original-register-only queries.

All 8452 nets route without errors. Hold +0.071 ns and pulse +1.830 ns pass;
DSP/RAMB18 stay 21/15. Reset first-stage fanout and registered-purge checks pass.
CDC remains nine CDC-3 information items and 208 CDC-15 warnings, with no waivers.
The OOC 114 inputs and 124 outputs remain unqualified. Clocks and route recipe
are unchanged. Keep the parent and this candidate; do not promote this regression.

## Next step and deployment gates

First test removing the two newly added KEEP hints on parallel capacity and
input-room expressions. This changes no behavior and allows synthesis to absorb
the introduced logic boundaries. Whether it helps requires a new matched actual
FFT/synthesis/route result. If the long READY→guard→protocol-check path persists,
investigate that control boundary; do not remove fault/reset/publication safety
or more TX functionality as a substitute.

Native 60 MS/s fine search and independent 2.5 MS/s CI16 IIO inspection remain
required. Full receiver timing/CDC/real board clocks, actual 60 MS/s RX calibration,
continuous RX, sustained Ethernet/IIO, blind GLRT, 120 ms dwells and 300 s scans
remain gates. Only then qualify pinned PPU firmware/rollback on `.18`, followed
by `.17` Ethernet-only deployment and outdoor verification. No radios, PPU/main,
primary HDL, clocks, exceptions or TX were changed; `.20/.21` remain untouched.

## Evidence

[Read-back-verified archive](20260911-parallel-kernel-ready-evidence.tgz),
[receipt](20260911-parallel-kernel-ready-evidence.json):
33,415,829 bytes / 6301 members, SHA256
`70e06011a7dad8ef2a26acfcbb5420fda5087bc54ac27423c1e8e49e00810181`.
Includes source, actual FFT logs/CSV, synthesis and routed checkpoints, tests,
original and replica-aware path reports, CDC and parent evidence.
Raw evidence: `/dev/shm/starlink-parallel-ready.uE2Iyp1W`.
Prepared SHA: `5fb473217ce86afe71b36ae7ee879f314d54667c0909bcaa801dcf81364b3590`.
Routed DCP SHA: `4c9907e9b2f8993d6cb61ad4eb801d79d7b15d4a70643a66c0efb51bdc1304a9`.
Parent contract: [parallel-capacity shadow](20260911-forward-capacity-contract-actual.md).
