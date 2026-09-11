# Destination candidate: actual FFT PASS, timing FAIL

Root actual session 3613 passed in 61.05 seconds. All 77953 numerical rows and
the entire previous parsed result match offered-summary after removing only
the additive destination witness. Numerical SHA256:
`07321b026a637e5922c56a84a955e58549056337198c952a9d73b1245cb4efaa`.
Seven service results remain 3645/3645/4912/3645/3645/3645/3645 cycles.
The witness checks 89723 pre/post edges each, 17 releases, 19 admissions and
19 publications. 85 actual-preparation tests and 69 physical-policy tests pass.

Synthesis session 27610 and independent audit pass: 2246 LUT, 4759 FF, 21 DSP,
15 RAMB18, with all 149 prepared files unchanged. Route session 72265 completes
but timing FAILS: **WNS -3.106 ns**, TNS -1106.223 ns, 827/11065 failing setup
endpoints. Hold +0.064 ns passes; all 7216 nets route without errors. Resources
after route: 2314 LUT, 4769 FF, 21 DSP, 15 RAMB18.

This is worse than offered-summary (-2.504 ns), so do not promote the candidate.
The worst path is held_phase → input metadata validation → fault/control logic
→ retained-owner reserved/D: 14 logic levels, 8.854 ns total data delay
(2.856 logic, 5.998 route). Another metadata→cutover-owner path fails -3.103 ns.
Clock-crossing waivers cannot solve these same-domain paths.

Five critical CDC findings and 114 input/124 output delay constraints remain
open in the isolated diagnostic model. No clocks, route settings or exceptions
were changed. No continuous receiver, board, RF or deployment claim.

Candidate source was published on the separate rom-prefetch DNM lane:
FW `2e93be5f3a6d22098085f2a836ad936f05775dc6`,
HDL `681f444c70aaad633fac3684d9f4852b0b74e1c7`.
The primary production HDL gitlink is unchanged. No radio or PPU operations.

Evidence root: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz`.
Actual: `destination-actual-parent.LQnQo9ny`; physical-policy gate:
`destination-physical-prep-parent.NJlhw5AK`; synthesis:
`destination-synth-parent.G1XLB1ik`; route: `destination-route-parent.ZwqAjdhv`.
All owners are terminal. Raw local evidence is preserved; remote artifact
packaging remains separate from source publication.

Next: explicit registered descriptor-validation/control boundaries. Tagged
certificates must expire on reset, replacement or fault; no delayed certificate
may authorize an early publication or release. Then prove integrated numerical
correctness and the coarse-block service deadline, re-route, integrate full RX,
qualify sustained 60 MS/s plus 2.5 MS/s IIO, `.18` canary, `.17` PPU Ethernet
deployment and the 300-second blind comparison scan.
