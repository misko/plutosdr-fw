# ROM K1/M1: actual-core simulation result

The one authorized relocated C1+K1/M1 run passes its frozen actual-core,
numerical, fault/reset, qualified-status and unconditional ROM-state gates.
Original10102 and independent terminal audit64438 both exited0. This is
simulation equivalence evidence, **not raw217 equivalence, physical closure,
resource measurement, production promotion or RF evidence**. The earlier
23845 quota failure remains separately archived and unchanged.

Tested source remains FW `e7d8b229e1719eb4fd40810b4e5be5fad98a96d6`,
HDL `54af5727801b3f0cb3a9a178b3135cc6e5a311fd`; all seven canonical C1
runtime files remain unchanged. R/D/S/C/K/M=111111, extras1, FAST175, QUICK0.
There is no arithmetic or local-control flag union. The original internal
reference remains dec20 R1/D0/S0; the additive ROM shadow is literal C1,
parameter-matched including S1, driven only by the actual ROM input ports.

## Complete original process and terminal checks

Run directory:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-relocated-actual-v2.CWJkzwEi`.
Original10102 started2026-09-10T12:55:57.787981380Z and ended
13:06:14.381724767Z. `/usr/bin/time` records616.59s wall time and exit0.
Vivado2022.2 used the explicit SuSE loader environment/two threads, unique
owner logs/journal and non-/tmp TMPDIR; immediate preflight found52GiB free.
The proposed owner differs only by five base-path substitutions from the first
owner; reversing those substitutions restores its complete original bytes.
No second successor or source changes occurred during execution.

Original process/post-integrity/IP/independent-receipt files are all nonempty
and exactly `0\n`. Both56-entry source audit logs pass. The stored
before.sha256 and after.sha256 are nonempty and identical; an independent
external check revalidates inventory
`6f5eddb99510e869bbe65548acc6ed64cd76bd98908aacfcd6e1c0361ccbe4ae`
and runner
`9f198abf60d9119eae2ef565ae3d65b64104f93ce5f1b5be4b2e89776dd3deed`.
Frozen `verify_prepared` and `verify_result` pass from `/`. Independent
terminal audit64438 also checks persisted receipts, unique completion marker,
all four CSVs and all19 after-only generated-IP hashes. No empty receipt is
interpreted as success. `$finish` occurs at3560734467751fs.

The new terminal receipt is exact:

```text
ROM_READ_AHEAD_ACTUAL_PASS word=1 metadata=1 pre=623129 post=623129 accepts=74440 first=148 last=141 stalls=11 resets=4011 current_fault_edges=7882 final_fault_edges=115 private_reset_edges=164648 old_source=C1 input_ports_only=1 unconditional_old_state=1
```

All old visible coefficients, metadata, controls and state are compared
unconditionally before NBA and after NBA/+1ps, including invalid cycles.
These counters count sampled edges:115 is aggregate-fault observations while
the kernel expected index was511, not115 separate injected final faults.
Similarly164648 samples `fast_running && !core_aresetn`, including ordinary
private-core hold/reset periods; it is not164648 distinct fault resets. The
separate CDC monitor's4265 private-reset samples additionally require a fault.
The unchanged active whole-bank observer independently records exactly two
active final-fault edges. First/last acceptance counts include incomplete
fault epochs, not a claim of148 complete healthy transforms.

Original exact observer:1246258 checks,780367 active,36 consumed identities,
270 unused private-scratch differences,2 active final-fault edges,99936
owned-stall edges and143 reset-owned edges. Both independently driven extra
benches report exactly2 final faults,3 held-final stalls,2 one-sided resets
and4 healthy recoveries. CDC712146 comparisons retain the original scalar
actual-fast-fault source and slow-running reset; stage0/1 high counts8958/8686,
reset samples4675, current fault7882, final-index fault115, faulted private
reset-low4265.

The original bank receipts retain44 healthy blocks, nominal maximum forward
interval4548 cycles,8 registered fault boundaries,4 reset boundaries and106
completion consumptions. Preflight retains84 reason rows,84 raw-bank boundary
rows,12 expected-cache cases and12 active input tuple corruptions. Original
forward-retirement checks1179897 still report `inverse_current=0` and
`sticky_forward=0`; this actual run does not newly establish those separate
corruption cases. Their prior fast witnesses remain the relevant evidence.

## Exact numerical output and literal observation scope

Both complete main CSVs are35655334 bytes/589950 lines, SHA
`25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122`.
Both extra CSVs are2055036 bytes/33180 lines, SHA
`b965d12603a64111fa9c6ea36cb0f12189945ad4d9be7cf4fbd883980c4ec4a0`.
All four terminate with a newline and match the passing C1 history exactly;
no numerical, latency, metadata or fault gate was relaxed.

Qualified-status accounting is1246258=953943 raw-equal+292315 invalid-only.
That is148 fewer invalid-only observations than the earlier C1 run; no fixed
invalid-only count was required. All rows and both validity values are kept.
All216 other whole-bank fields stay unconditional, and all eight status bits
are checked whenever either valid is not exactly zero. The terminal explicitly
states `original_raw_contract_pass=0`; the raw217 trace is not claimed equal.
The separate ROM shadow has no invalid-word or metadata mask.

Warnings are retained without waiver: one long IP name, one empty compiled
library path, eight forward-declared identifiers, sixteen initialized non-net
outputs, one glbl parameter warning and one distributed-cause pretty-print
warning. Generated IP is absent before project creation and hashed afterward;
this is not a precompile IP-equivalence or synthesis-support claim.

## Preserved evidence and next scope

Portable terminal archive is HDL
`library/starlink_pss_acquisition/evidence/rom-read-ahead-actual-v2`.
Non-/tmp staging is
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/rom-success-10102.rjcEJGHe`.
It preserves the complete frozen bundle, prelaunch/owner/independent receipts,
full logs and four CSVs, generated IP and exact full WDB in <=40MiB parts.
Original project and monolithic gzip remain outside the worktree; the old
quota-failure package remains untouched. The archive HDL pin is
`7ef21048255669918b0fc8ee2be46b0c665579a8`; its130-member manifest SHA is
`0b83a3933d7d02211a2f0e6f5dbd6cde0c624f7a78a9abbd4db4acecd806d4d3`.
Git-object verification passes all130 members with exactly131 tracked files;
receipt is `git-object-verification.json` in the non-/tmp staging directory.
All raw gzip identities and actual WDB reconstruction pass. WDB130586439 bytes
has SHA `6d41bf2fd7f09149cbd19e7a24ba08c2327f5f6b0e0723b6c26dd6ec634c9030`;
gzip118973350 bytes has SHA
`de7838280cef902e72830d4d5f263f295f0bdec5bc0909530a090eb8c0c8020c`.
No tracked member exceeds40MiB; total portable payload is142282627 bytes.

Next work is authorized **offline physical preparation only**: explicitly bind
this exact accepted C1+K1/M1 source to the existing C1 synthesis/route recipe,
retaining clocks/IP/constraints/directives/two threads and strict full-source
admission/inverses. The +107 logical register bits/105 mux bits at D18 remain
an estimate, not measured area. Metadata/word muxes, selector fanout and other
held-phase fault paths can still dominate. No synthesis or route follows until
separate source-specific review and authorization.
