# ROM K1/M1 synthesis: complete, timing still unmeasured

The one authorized synthesis completed: original11476 exit0,131.84s,
2026-09-10 13:35:46–13:37:57 UTC. All owner before/tool/after/overall statuses
are0. Independent post-audit36656 exits0: eight nonempty products,13 input/IP
hashes plus the actual simulation log, full copied closure and frozen
prepared/actual admission all pass. No runtime or physical recipe changed.

| Synthesized xc7z010clg400-1 | Old C1 | C1 plus K1/M1 | Delta |
| --- | ---: | ---: | ---: |
| LUTs | 1986 | 2059 | +73 |
| Flip-flops | 4500 | 4607 | +107 |
| RAMB18 / tiles | 15 / 7.5 | 15 / 7.5 | 0 |
| DSP48E1 | 21 | 21 | 0 |

New LUTs comprise1871 logic and188 SRL;7 F7 muxes,0 F8 muxes/latches/black
boxes. The kernel hierarchy changes71 LUT/224 FF to114 LUT/331 FF. Its107 FF
increase matches the logical word+metadata estimate. Hierarchical LUT
allocations elsewhere also change under optimization/combining: do not
attribute all73 LUTs to that submodule. These are synthesized, not routed,
counts; placed slices and control sets are not measured yet.

Actual propagated clock reports show source_100=10ns onclk and
island_175=5.714000225ns onfft_clk. CDC reports17 informational two-stage
ASYNC_REG paths,139 clock-enable CDC warnings and0 critical findings. Those
mailbox warnings remain open. check_timing reports114 inputs and124 outputs
without IO delays,0 unconstrained internal endpoints,0 no-clock pins/loops.
Neither external interfaces nor full-receiver timing/CDC are qualified.

The top synthesis run has15 warnings,0 errors/critical warnings; the IP run
has440 warnings,0 errors/critical warnings. All raw diagnostics are retained.
Synth8-7052 specifically reports speculative_word_reg as block RAM whose
optional output register could not be merged. RTL control changes therefore
do not establish timing improvement, or removal of every critical path.

## Exact checkpoint and provenance

Synthesis source FWcae523aa869b859f84b242d3b6dd03157fddc87d /
HDL49a133554c8cb738d2a93136355571225df7076c. Accepted runtime remains
FWe7d8b229 / HDL54af5727 from original actual10102. Explicit R/D/S/C/K/M=1;
all seven physical RTL files equal that actual freeze. The actual numerical
CSV/extra/fault/reset/ROM gates remain intact. Status scope remains qualified
953943 raw-equal plus292315 invalid-only, not raw217 equality.

All execution paths are under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`:

- Prepared: `rom-k1m1-physical-prepared-v1`,18-file manifest
  `d4d364427c31531358ce747b5931d4fa441e8e46002bf986626c69e923be2a39`.
- Original run: `rom-k1m1-synth-v1`; unchanged ownerd0f36ce2 and adapter902a1fd0.
- Final DCP: `rom-k1m1-synth-v1/synthesis/fft_bank_owned_synth.dcp`,2181849bytes,
  `264b7dbb89ccef59b1b41dbaee2e01d4138b8d9a368f64ebc6532efd04f5405e`.
- Independent audit: `rom-synthesis-package-v1.ltXxPqvT/independent-post-audit.json`.

Portable HDL evidence is
`library/starlink_pss_acquisition/evidence/rom-read-ahead-synthesis-v1`:
all eight products, raw owner logs/statuses, original sources and generated IP
configuration/wrapper/synthesis logs, frozen recipe, audit and old C1 resource
comparison. Complete original file identities also inventory uncopied local
project caches/netlists. Original run and all prior failures remain intact.
Git-object manifest closure is required, not merely local filesystem hashes.

## Separately authorized route

The reviewed local-admission owner is reused with exactly four literal
substitutions: BUILD, DCP path, Tcl path and expected DCP SHA. Complete inverse
and syntax checks pass. Owner SHA
`e9b7ca13900d5b04e807bed408aab87022d05cab81c18cec33e79305f700c3b0`;
unchanged route Tcl
`0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.
Parent separately approved one diagnostic route after reviewing these inputs.
Original87839 launched13:45:49.908096 UTC, Vivado PID743957, with49GiB free.
This report does not claim a route result; that evidence will be separate.

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
  /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-k1m1-route-v1/own_route.py
```

The owner supplies explicit SuSE LD_LIBRARY_PATH, its own non-/tmp tmp,
log/journal before Tcl arguments, source hashes before/after even on failure
and no retry. Tcl retains100/175 clocks,2 threads and exact inherited
opt/place/phys_opt/route directives, no exceptions. All15 expected route
products must additionally be nonempty and verified. Timing, CDC/I/O and
full-receiver closure remain independent gates; no promotion or radio work.
