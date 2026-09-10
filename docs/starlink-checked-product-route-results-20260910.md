# Checked-product diagnostic route: physically held

The checked-product candidate passed the source-specific actual FFT functional gate, but its first diagnostic route failed timing. This lane is **held**: no physical qualification, deployment, receiver/radio authorization, or default promotion follows. The parent's retained next-cone lane proceeds separately; it is not a composition with this candidate.

## Original terminal result

Root owned original route handle `91981` through terminal exit 0 in 67.59263178694528 seconds at `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/checked-route-parent.3lJAqEWe`. Process completion is not timing closure. There was no timeout, interruption, retry, constraint change, or subsequent vendor run for this package.

| Evidence | Result |
| --- | --- |
| Global setup WNS / TNS | -8.324 ns / -7913.583 ns |
| Failing setup endpoints | 2309 of 12037 |
| Hold slack / failing hold endpoints | +0.039 ns / 0 |
| Fully routed nets / routing errors | 7597 / 0 |
| Routed resources | 2592 LUT, 5103 FF, 21 DSP, 15 RAMB18 |
| Routed CDC | 1 critical, 139 warning, 17 info |
| Unconstrained external IO budgets | 114 inputs, 124 outputs |

The original synthesis counts remain separate: 2507 LUT, 5099 FF, 21 DSP, 15 RAMB18; synthesis CDC was 13 critical, 139 warning, 5 info. Neither CDC snapshot is a waiver or full-receiver qualification.

The worst same-domain path starts at `registered_scheduling.expected_product_metadata_reg[0]/C` and ends at `checked_product_bank.origin_valid_reg/D`: 26 logic levels, 13.941 ns data delay (4.034 ns logic, 9.907 ns routing). It contains 6 CARRY4, 2 LUT4, 7 LUT5 and 11 LUT6 levels. The independent controller-origin binding remains physically expensive; the checked raw-token stages do not establish closure for this separate path.

| Path group | Setup | Hold |
| --- | ---: | ---: |
| source_100 → source_100 | +1.758 ns | +0.102 ns |
| island_175 → island_175 | -8.324 ns | +0.039 ns |
| source_100 → island_175 | -0.504 ns | +0.145 ns |
| island_175 → source_100 | -1.426 ns | +0.073 ns |

## Exact source and flow

The input DCP came from accepted root synthesis `63808`, itself admitted by the unchanged actual-v2 result and drain gates. All 14 checked-product runtime modules and explicit enabled options are unchanged. The route reused the exact original route Tcl, inherited source_100 period 10.000 ns and island_175 period 5.714 ns, Vivado 2022.2/SuSE, two threads, and the unchanged opt/place/phys_opt/route sequence. No false paths, multicycle paths, clock groups, or new clock/IO constraints were added.

- Input synthesis DCP SHA-256: `62ea84c5d09ac3e41b00157d8761a1834d11540c28566196148b8e74bb70ba52`.
- Route Tcl SHA-256: `0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.
- Routed DCP SHA-256: `0707432cca72c25e71ba35d7fa6968a5cbd413449ca40c425506f9ab56338aaa`.

The original owner records unchanged input DCP, original runner and copied runner after execution. Root's separate audit confirms route completion, actual timing failure, resource/CDC/IO counts, exact constraints and checkpoint identity. The archive retains both the audit program and its original JSON; packaging does not relabel any original result.

## Preserved evidence and scope

HDL archive `library/starlink_pss_acquisition/evidence/checked-product-route-v1` contains the complete original route-owner file tree, all 15 required nonempty route products, stdout/log/journal, original command/process/execution receipts, root audit source/result, and exact source DCP/Tcl copies. Its SHA256SUMS pins every file. Files are directly portable and below the 40 MiB per-blob limit; no checkpoint recompression or reconstruction is needed.

The earlier published `checked-product-actual-v2` and `checked-product-physical-preparation-v2` archives retain the successful functional evaluation, original v1 failure, offline preparation and complete synthesis evidence. Functional acceptance remains the reviewed changed-latency, qualified-status/accepted-tuple contract—not raw-217 cycle equality or arbitrary post-GOOD transport corruption coverage. Physical failure does not erase that functional evidence, and functional evidence does not override this physical failure.

Only additive evidence/report files and the FW HDL gitlink are changed for publication. No RTL, observer, parser, factory, constraints, or tested preparation files are edited.
