# Actual-bank full production-map simulation: PASS, 2026-09-10

The single approved full-v1 run passed on unchanged firmware `e2f3a582be5d24aef3bf72029a4af0fb2c046d99` / HDL `22aa00d457576927dcb11927fc9e6e6a6aaf32df`. Original process handle88186 exited0 after bench PASS, `close_sim`, strict terminal verification, `close_project`, and wrapper verification. There were no restarts, altered thresholds, runtime edits, or additional full-run attempts.

The reviewed source signature was and remains:

`b10e4f2384084f7caff844d7508fff0a538e09caf8f3713d6fddcb7f2f39b75a`.

All61 frozen full-run input files byte-match the reviewed smoke-v5 files. The [prelaunch report](starlink-bank-production-map-prelaunch-20260910.md) contains the seven immutable original-golden SHA256 pins, kernel byte-match, independent18-bit C-model/integer oracle, frozen acceptance criteria, source support equations, and the retained smoke failures. Parent independently reproduced all14 periodic numeric files before authorizing this run.

## Result and exact inventory

The actual bank-owned FFT scorer fed the unchanged20,000-bin ×64-frame phase-map runtime, including its ten configured RAM segments. Every admitted score/index/phase, every visible transform and arithmetic prefix, and all20,000 returned map words were checked against the frozen compact oracle. The deliberate low32 source-index rollover passed. The mid-tile stop request was accepted at the prescribed640,013-score threshold; the admitted tile finished before publication and terminal ACK.

| Checked item | First complete production map | Whole run, including fresh partial epoch |
| --- | ---: | ---: |
| Admitted scores | 1,280,000 | 1,280,447 |
| Visible exact scores | 1,280,001 | 1,280,448 |
| Visible exact tails excluded from map | 1 | 1 |
| Actual forward core-input words | 1,466,880 | 1,467,904 |
| Actual inverse core-input words | 1,466,368 | 1,467,392 |
| Exact returned forward words | 1,466,368 | 1,467,392 |
| Exact product words | 1,466,368 | 1,467,392 |
| Exact returned inverse words | 1,466,368 | 1,466,880 |
| Exact66-sample energies/correlations | 1,280,004 | 1,280,451 |
| Exact69-bit numerator/denominator pairs | 1,280,003 | 1,280,450 |
| Complete-map words returned exactly | 20,000 | 20,000 |
| Terminal receipts | 1 healthy | 1 healthy +1 classified partial abort |

The1,466,368 returned words in each transform direction are exactly2,864 ×512. All BFP exponents, positions, TLASTs and absolute descriptors were checked. Extra speculative forward/inverse input or arithmetic prefixes were also checked; they were not required to finish after the map fence disabled the coarse engine. Actual core consumption was witnessed on its own175 MHz clock, including the unchanged zero-padded18-bit payload in24-bit wire slots.

The independently accumulated production map remained SHA256 `7dedc4a434401a50183a53ca33d5e966c2c435a014121a53d2e7a1490fae4f9f`; every map word was compared, not only a checksum or selected peaks.

## Stop, support, retention and recovery

The final selected score was residue239 of the last447-score block. The2,864 blocks could produce1,280,208 scores, leaving208 potential tail scores. One tail was actually exposed, numerically checked and excluded; no tail entered a subsequent map. The other potential tail work was not required to drain after deliberate coarse disable.

Support accounting remains distinct:

- Direct66-tap support:1,280,065 samples, through relative1,280,064 inclusive.
- Whole FFT support:1,280,273 samples, through relative1,280,272 inclusive.
- Offered source samples at the post-ACK receipt:1,280,854; this is observed continued traffic, not a revised minimum support requirement.
- Additional offered source samples during retained-map hold, all reads and release:19,520.
- Total source sample presentations checked on slow-clock edges across the whole run:1,301,644, including intervals when coarse processing was disabled.

The source remained contiguous at15/100 cadence through stop, retention, deterministic read-request bubbles and release. Every one of20,000 synchronous read responses was matched to its outstanding request and expected word; publication/admission counters and generation/start/end stayed fixed throughout. Source offered/consumed reconciliation was sampled after the real consuming positive edge.

Publication followed the final accepted score and drained RAM-update stages; terminal ACK was observed after publication. The healthy stop receipt occurred85.390294998 ms after the source epoch began. That is distinct from85.333333 ms selected-score exposure,85.337667 ms direct support, and85.351533 ms FFT support. These ideal-clock simulation observations do not qualify a physical120 ms scanner visit or host return/control deadline.

After complete-map reads and release, an explicit enable cycle without external reset produced447 fresh exact scores. The new incomplete map was deliberately aborted: one abort, native `map_counter_fault=1`, detector-health flags0, reason10 (explicit abort plus local map health), no ready map, and historical generation1/start/end retained. Released maps are not readable merely because `HAS_MAP` preserves historical publication. No failure retroactively undid an earlier accepted score or healthy publication.

This is **not** a full second production map after recovery, nor recovery after the final partial fault. The final failed partial epoch is explicitly classified; background map-bank clearing is not a claim of full idle/clock-gating qualification. The reduced smoke separately exercised a complete fresh map after recovery.

## Runtime, verification and provenance

Six bounded live checkpoints were emitted at200,000,400,000,600,000,800,000,1,000,000 and1,200,000 exact scores. Their simulated times were13.592095,26.922235,40.259835,53.589995,66.927595 and80.257735 ms. The original process was polled in intervals of at most60 seconds; buffered log output was not treated as a score-progress measurement or an observation timeout requiring restart.

Host: `gauss`, Linux7.0.0-30-generic x86_64. Actual simulation wall time was1:35:03; compile/elaboration/simulation wall receipt5,715,646 ms; xsim CPU5,683,370 ms. Simulation finished at86.977990 ms. These are host simulation costs, not ARM/Zynq real-time throughput. The optional WDB was only301 KiB and is excluded from the archive; there are no large recorded waveforms or expanded production IQ files.

The strict postprocessor was independently replayed against the terminal log and passed. The unchanged151 policy/oracle tests passed again (`production-map-policy-v4.xml`); Ruff remained clean. All103 full-run source/artifact SHA256 receipts were verified. No radio, PPU, synthesis/route, receiver-profile, AXI/BD, main-worktree, or remote write was performed by this task.

Evidence directory:

`hdl/library/starlink_pss_acquisition/build/bank-production-map-full-v1`

Portable archive: `reports/experiments/20260910-bank-production-map-full.tgz`,244,576 bytes, SHA256:

`42d8401b36ab64c47a0a857563a5b0d27da44ab44b5258907a1333669eb5c920`.

The [full JSON receipt](starlink-bank-production-map-full-20260910.json) inventories the103 files and preserves every terminal/progress row. The archive includes the61 actual frozen simulation inputs, all14 periodic numeric files, original seven goldens, oracle source dependencies, source/scope/generated-wrapper hashes, final policy result, simulator logs, measured runtime and original-process exit receipt. Proprietary generated IP projects/C-model shared libraries are omitted; installed vendor archive/library/wrapper hashes and unchanged generation helper identify the required tool inputs. Earlier failures remain in the separate prelaunch archive and were not overwritten.

Scope remains periodic447 synthetic geometry/arithmetic stress with ideal100/175 MHz clocks. Identical repeated blocks cannot expose every possible stale-payload substitution when the substituted values are identical. This run is not RF/frame-detection accuracy, native15/30/60 fine support, paired pilot/PIL1 truth, physical timing closure, a worst-case backpressure/capacity qualification, or authorization to switch a production profile.
