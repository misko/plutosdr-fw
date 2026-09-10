# Actual-bank production-map probe: prelaunch review, 2026-09-10

Status: reduced smoke passed; **the 20,000 × 64 production simulation has not been run**. No runtime RTL, existing bench, original golden, receiver profile, AXI/BD, or IP-generation helper changed. HDL additive test commit: `22aa00d457576927dcb11927fc9e6e6a6aaf32df`, based on `6ae9c302390b97f44d86f1d9e825a0cf40ae3464`. Firmware base: `ad6dfbb79a93ad9d8bf882ef5672ef809cb2aaed`.

The candidate is a periodic synthetic arithmetic/geometry stress test, not RF acquisition, frame-detection accuracy, paired pilot/fine integration, live throughput, physical clock timing, or a production switch. Its actual vendor FFT runs on ideal 100/175 MHz simulation clocks. It does not repeat the separate generated-MMCM qualification.

## Frozen oracle and production acceptance contract

`tools/generate_starlink_periodic_map_vectors.py` takes the original fixture's first 447 CI16 samples as a repeated period. Thus each 512-sample overlap block, starting at `block * 447`, is identical. A fixed 18-bit C-model subclass avoids changing the existing oracle's global width. The installed Vivado 2022.2 FFT C-model archive is SHA-pinned by the unchanged helper. An independently derived 66-tap reversed-conjugate kernel, fixed-transform schedule `(2,0,0,0,0)`, must byte-match the existing 512-word kernel. Kernel SHA256: `694d0d9b8dd55368bcaaedec37a7cda3a837d491d592ede60eec57a9821fc99a`.

Before generating the periodic fixture, the independent integer product/energy/score calculations reproduce all three original blocks: 1,536 forward, product and inverse words each; all three exponents per direction; all 1,341 scores. Admission also checks these original seven immutable SHA256 values, not merely self-consistency:

| Original file | SHA256 |
| --- | --- |
| samples_ci16.mem | `4abe27ba953cf49f84d9979966625a2436ad59359b616321e881b42dd4c84723` |
| forward_q17.mem | `d934a8ecd0888c294fc0abfbdbe7c439bff7097ea169b937638c4b7000479bfd` |
| product_q17.mem | `b316522a68529a73d3d8e4121badea61e24621c93a97365e894f5bd416bcecb7` |
| inverse_q17.mem | `c8c5b4e28ab621d0b1d5c1dc288f6e66495b3319d348442ce5d7b8f6ea8025a1` |
| forward_exponents.mem | `18ac6df6a1ae3f19e5153524b33f336a60eabdd6dbd182d46c43450302e4b52f` |
| inverse_exponents.mem | `899b7a2486fd3759c6e4905110fc4d86ffdb6ec884da2a7f2aca4acdfd363dff` |
| scores_u8.mem | `c22f751a2a82244268dd9ea4989c4ff3b5364c172526e80886c5da3d1959e45d` |

The complex product uses signed integer ties-to-even division by `2^18`. Energy is the exact sum of 66 CI16 powers; coefficient energy is `1,073,742,825`. Numerator is `(I²+Q²) << [2*(7+Ef+Ei)]`, saturated to unsigned69. Denominator is energy times coefficient energy. Scores use exact rational ties-to-even normalization to unsigned8, with zero-denominator and saturation behavior explicit. The periodic case has `Ef=4`, `Ei=4`, power shift30. Python tests cover signed rounding, ratio ties/zero/saturation, shift68/69/70/127, and the 36-bit-power/69-bit saturation boundary. Those unit boundary tests do not claim that this particular actual-IP fixture exercises every saturation boundary.

Only one block's 512-word intermediate arrays and 447 scores/energies/ratios are stored. The independent map equation is:

`map[p] = sum(score[(p + frame*bins) % 447], frame=0..frames-1)`.

Unit tests separately compare it with sequential accumulation over all 1,280,000 score positions. Production map SHA256: `7dedc4a434401a50183a53ca33d5e966c2c435a014121a53d2e7a1490fae4f9f`. Parent independently regenerated all 14 periodic `.mem` files and reported byte equality before full-run approval.

| Frozen geometry | Smoke | Production (not yet evaluated) |
| --- | ---: | ---: |
| Bins × frames | 343 × 2 | 20,000 × 64 |
| Selected map scores | 686 | 1,280,000 |
| Required overlap blocks | 2 | 2,864 |
| Full-block potential scores | 894 | 1,280,208 |
| FFT source support, samples | 959 | 1,280,273 |
| Direct 66-tap support, samples | 751 | 1,280,065 |
| Last-block selected scores / excluded potential tail | 239 / 208 | 239 / 208 |

For production the last selected score starts at relative index1,279,999 and needs direct samples through1,280,064 inclusive. Whole FFT block support extends through1,280,272 inclusive. At15 MS/s, 85.333333 ms selected-score exposure, 85.337667 ms direct support, and 85.351533 ms FFT support are distinct from elapsed pipeline/stop/control time. Source continues beyond those minimum supports. No 16.7 ns native-sample spacing or timing-accuracy claim is made.

The production bench uses the unchanged runtime's actual 20,000 bins, 64 frames, 15-bit phase address, 16-bit map, and ten 2,048-address RAM segments. The runner checks those defaults in the runtime declarations before admission. The initial index is `0x00000001fff80000`; the production selected interval crosses the low32 carry.

Every actual vendor core input is compared on its own FFT clock, including real component payload and zero-padded 24-bit wire slots. Every visible accepted forward/product/inverse word, descriptor/index/position/TLAST, and BFP exponent is checked. Every energy/correlation and69-bit ratio prefix is independently checked. Every visible score/index/phase is checked, including tails and the final partial-abort prefix. The map must admit exactly the selected score count, publish atomically, return every word exactly, retain identity through deterministic read bubbles, and reject tail admission after its stop fence. Final stop timestamp is sampled after the actual ACK observation edge; source offered/consumed reconciliation occurs after the consuming positive edge.

A complete map may have0..208 visible tail scores, all checked, but none may enter another map. Visible and admitted totals are separate. Third-block forward work is legal in the smoke: stop is a map-boundary fence, not a promise to complete or undo all speculative FFT work. No partial FFT prefix receives a blanket numerical waiver.

## Measured smoke and lifecycle scope

Final run: `hdl/library/starlink_pss_acquisition/build/bank-production-map-smoke-v5`, periodic inputs `build/periodic-map-vectors-v4`.

Two complete343×2 maps passed, including a complete fresh map after enable-cycle recovery without external reset. Each admitted686 scores, exposed687 checked scores, returned343 exact words, and retained the generation/start/end tuple through all reads and release. Each had959 minimum FFT support,1,540 offered source samples at stop, and354 additional source samples through retained/read/release work. Each stop receipt arrived102,694.998 ns after starting its source epoch.

The final fresh epoch admitted and exposed447 exact scores, then deliberately aborted its incomplete map. Native `map_counter_fault=1`, detector flags remain0, abort count1, terminal reason10 (explicit abort plus local map health), no ready map, and historical generation2/start/end are retained. The combined PSMA map-health bit is not part of this native interface. The failure does not retroactively invalidate the earlier complete publications; released maps are no longer readable, while `HAS_MAP` is historical.

Aggregate:1,821 visible checked scores /1,819 admitted /2 checked excluded tails;5,058 consumed source samples;4,096 forward and3,072 inverse actual core-input words;3,072 forward,3,072 product,2,560 inverse returned words;1,827 energies;1,825 ratios;686 map words;3 terminals. Final bench PASS, strict postprocessor, close_project and wrapper verification all completed; Vivado process exit0.

Production recovery scope is deliberately smaller: one full production map, then447 exact fresh scores and a classified partial abort. It will **not** qualify a second full production map after recovery.

Final policy run:151 tests passed (`production-map-policy-v3.xml`), Ruff clean. Tests cover immutable originals, integer boundaries, full map equation, malformed/missing/oversized/range-invalid vectors, receipt hashes, non-overwrite, production review admission, frozen sources, and missing/duplicate/wrong/late-failed terminal inventories. The helper accepts evidence only; these tests are not substitutes for the actual-IP run.

## Retained failures and source provenance

1. Smoke-v1: Tcl admission expression typo, before simulation. Rejected runner/bench/oracle snapshot and log retained.
2. Smoke-v2: expected sign-padding instead of unchanged zero-padding in the core wire ABI. It also exposed that `quit` in custom xsim Tcl exited before wrapper verification; the final custom script contains only `run all`. This attempt is not a valid wrapper-qualified result.
3. Smoke-v3: terminal timestamp checked before the next positive edge observed registered ACK. Strict wrapper rejected the fatal. No numerical or map threshold changed.
4. Smoke-v4: both complete maps passed; final partial assertion incorrectly expected PSMA-combined flags from the native split-health interface. Native map fault and failed terminal expectations remain mandatory.
5. Smoke-v5: all bench and wrapper checks passed. Corrected source-consumption receipt edge avoids treating a legally pending offered sample as a lost sample.

All runtime modules and old tests remain unchanged. [JSON receipt](starlink-bank-production-map-prelaunch-20260910.json) inventories336 retained files, including each attempted run's frozen inputs/logs, final policy test, all original golden snapshots, compact oracle source dependencies, generated-wrapper hashes and C-model archive/library hashes. Unused early vector-generation versions are retained with their manifest source digests; the final generation includes its source snapshot. No generated proprietary C-model libraries, large waves, expanded production IQ, or generated IP project is bundled.

Portable archive: `reports/experiments/20260910-bank-production-map-prelaunch.tgz`,736,028 bytes, SHA256 `56ef3a428bd29d174a5939d231b8d964dc4a3f730ff0845eba2f5ef39e0abed9`.

## Review gate and estimated cost

Final source signature (runner, bench, policy, oracle/dependencies, runtime, helpers, kernel, receipt and14 vectors):

`b10e4f2384084f7caff844d7508fff0a538e09caf8f3713d6fddcb7f2f39b75a`

Production requires this explicit reviewed digest as fourth argument; it is not authorization by itself. No full run is launched before parent approval. The signature includes the manifest's original-source paths and uses sorted input paths; relocated/regenerated receipts can require a new digest despite byte-identical numeric vectors.

On host `gauss`, Linux7.0.0-30-generic x86_64, the smoke simulated343,040 ns with16,760 ms xsim CPU;17 s simulation wall,28,944 ms including compile/elaboration. Linear scaling by simulated duration suggests roughly70 minutes for the full run, with substantial uncertainty because the production RAM geometry and active-work ratio differ. This is host simulation cost, not Zynq real-time capacity or a measured120 ms deadline.

After explicit approval, from `hdl/library/starlink_pss_acquisition`, the candidate invocation is:

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vitis_HLS/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch -nojournal \
  -log build/bank-production-map-full-v1.vivado.log \
  -source simulate_bank_production_map.tcl \
  -tclargs build/bank-production-map-full-v1 build/periodic-map-vectors-v4 \
  production b10e4f2384084f7caff844d7508fff0a538e09caf8f3713d6fddcb7f2f39b75a
```
