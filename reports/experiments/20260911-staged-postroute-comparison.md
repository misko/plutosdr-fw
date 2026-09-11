# Post-route optimization: small improvement, timing gate still fails

Saved on `codex/starlink-rx-only-do-not-merge-postroute-physical`, FW commit
`b331c448c`. No HDL change; experiment gitlink remains
`cf4b702305b78d8992705aa4bf10cf4bc7ed5977`. Primary production gitlink remains
`0b4bf2f0fd8c58c79852266b07f9e95770f75f36`. No radios, PPU, main or receiver
runtime were changed.

## What was tested

The retained reference routes have long control paths with about 80% routing
delay. The existing recipe stops after routing, with no post-route physical
optimization. Run exactly one `phys_opt_design -directive AggressiveExplore`
pass on each pinned private-certification and guard-fact routed DCP.
[Vivado 2022.2 UG904](https://docs.amd.com/r/2022.2-English/ug904-vivado-implementation/phys_opt_design)
documents post-route physical optimization.

The new runner derives its recipe from the immutable original by replacing
only the four implementation steps with one post-route pass. All reports,
100/175 MHz clock checks, source/checkpoint receipts and path-safety checks
remain. Inherited XDC commands compare exactly after removing comments and
blank lines. No timing waivers or clock changes. Both runs use new output
folders and two threads, and finish on their first attempt in 22.54/23.85 s.

**19 tests pass**, including all original report-auditor corruption controls,
new exact-recipe inverse, changed-recipe rejection, read-only parent re-audits
and separation of report summaries from provenance validation. Both new routed
DCPs, all clock-pair reports, routing completion and source receipts verify.
RTL simulations were not rerun: the retained sources already have 449/464 tests
and 64512 matching actual FFT records respectively. This is not a new
post-implementation functional simulation or formal equivalence claim.

## Results

| Candidate | Global WNS before -> after | TNS before -> after | Failing endpoints before -> after |
|---|---:|---:|---:|
| Private certification | -1.452 -> -1.364 ns | -451.168 -> -448.933 ns | 704 -> 704 |
| Guard facts | -1.340 -> -1.307 ns | -463.636 -> -457.279 ns | 821 -> 822 |

Private-certification worst path still runs from scheduler phase through input
validation into inverse fault diagnostics. Its new resources are 2746 LUT,
5668 FF, 21 DSP and 15 RAMB18; 8352 fully routed nets, no routing errors.

Guard-facts same-domain 175 MHz WNS improves to **-1.167 ns**. Its global worst
is now **-1.307 ns** across the held output-metadata fast-to-slow crossing.
Resources: 2812 LUT, 5691 FF, 21 DSP and 15 RAMB18; 8469 fully routed nets,
no routing errors. One additional endpoint fails despite improved WNS/TNS.

Hold and pulse checks pass. Both retain 114/124 unconstrained I/O. **Both
timing gates fail**; no crossing has been waived. CDC/bundled-data qualification
is still required. This is a modest physical-flow improvement, not deployment
or full-receiver qualification.

## Next step

Keep post-route optimization as a finishing step, not a blind repeated sweep.
Shorten the common control path. Specifically investigate comparing source
and product metadata locally before selecting a one-bit comparison result,
instead of selecting 70 bits before equality and global fault reduction.
This is not yet implemented and does not promise timing closure.

First prove equivalent four-state behavior, including unknown phase: selecting
after equality is not automatically equivalent to equality after a ternary mux.
Preserve an exact fallback where necessary. Check both owners, each identity
bit, malformed position/last, unknowns, duplicate starts, core stalls, resets
and current-edge publication cancellation against the real original checker.
Then run the actual FFT and unchanged physical gates. Do not remove checks,
delay public fault vetoes, or alter reset semantics merely to shorten one path.

All end-state requirements remain: native 60 MS/s fine search, independent
2.5 MS/s CI16 IIO inspection, subsystem and full receiver timing/CDC/reset/board
qualification, actual 60 MS/s RX calibration, sustained Ethernet/IIO, `.18`
reversible canary, `.17` Ethernet-only PPU deployment with rollback, and a
300-second/120 ms valid-dwell scan compared with blind host GLRT.

## Evidence

[Archive](20260911-staged-postroute-evidence.tgz) and
[receipt](20260911-staged-postroute-evidence.json): 17729580 bytes, 212 members,
all read-back verified; SHA256
`b13e079045c47177958237ad5e7aaad48df97473b75f2aacdc03e00b6bcfa292`.
Includes both new and parent route checkpoints/reports, prepared source
inventories, actual FFT logs/CSV, test result, runner, auditor and detailed note.

Certification new DCP:
`1d3129f9ca10a89ab11e84b595ad591b69a01ce65a78240537d5be0552668cef`.
Guard-facts new DCP:
`569a91801822ff351762cba9783d032d1b0611a395a375fd1383c161d5fbadba`.
Generated recipe:
`1595ce0202e985e9937bfb98801008ec0cb6fe6b2aaed12cd880fa91cdfed5b6`.

Worktree: `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/postroute-physical-worktree-v1`.
Sibling runs: `staged-{certification,guardfacts}-postroute-v1`.
