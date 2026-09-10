# Retained output: bounded offline control prototype

The additive prototype permits the next forward transform while the previous
inverse result retains its real slow-reader obligation. The final source cut
passes **415 offline tests**. No vendor FFT simulation, synthesis, route, radio,
receiver profile, native-fine, pilot/IIO or deployment work was performed.

Tested code: FW `464e9bf34309501dd37089521288b81ccdbe5b4d`, HDL
`2e8a7de221889084ea58cc6c44dd9a8407c56c9f`. Both are isolated DNM commits.
All existing runtime files and prior numerical fixtures remain unchanged.
The approved design is `5aa90f4`; the earlier scheduling ledger `db4945dd4`
remains a separate conditional model, not retrospectively changed RTL evidence.

## Exact scope and interfaces

New HDL is confined to `library/starlink_pss_acquisition/retained_output/`:

- `starlink_pss_fft_bank_owned_retained_output_probe.v` defaults
  `ENABLE_RETAINED_OUTPUT=0`, instantiating the unchanged frozen L1 top.
  The opt-in requires known exact R1/B1/O1/L1 parameters; X/Z/non-Boolean entry
  values are rejected at elaboration. This is not live profile switching.
- `starlink_pss_fft_retained_output_impl.v` uses the same source, product and
  inverse-output payload banks, unchanged input guard, join/product arithmetic
  and one physical-FFT interface. No P1, K/M, C1 or inverse-sealed source union.
- `starlink_pss_result_guard_owner_view.v` and
  `starlink_pss_mailbox_owner_view.v` have strict whole-body inverses to the
  accepted guard `09ab3533...` and mailbox `e85122eb...`. Only names and
  read-only ownership outputs are added; no original state transition changes.
- `starlink_pss_retained_output_owner.v` binds the bank generation at actual
  inverse admission. Publication creates a held scheduler transfer receipt.
  It is not a fabricated READY/ACK. Real release requires observed occupancy,
  the actual request/ACK toggle match, and the original inverse guard's ACK.
- `starlink_pss_core_job_cutover.v` tracks the current core owner, reset,
  released-quiet observation, actual configuration handshake, fresh frame and
  full new input. Raw events are not masked during reset or ownership gaps.
- `starlink_pss_retained_epoch_barrier.v` keeps both mailbox sides closed until
  actual reset-idle observations from both clock domains are fresh. Either raw
  reset closes the outer interface; per-transform core reset never rearms or
  clears the retained reader. A paused slow clock must actually resume/purge.

Both exact result guards remain common-epoch owners. The old inverse guard may
wait for the real ACK while the forward guard owns the core. Raw return/status
events route to the admitted current core owner, not the scheduler's next phase.
Both guards retain their full current/sticky faults, descriptor and watchdog.
The independent retained owner may remain quarantined even if a real reader ACK
and current forward fault coincide and the old guard retires its private wait.

The owner rejects unknown or contradictory admission/publication controls on
release. A still-pending transfer receipt may legitimately be consumed together
with a real ACK; an already-consumed transfer cannot be repeated. In the actual
tested top, completion consumes that receipt early, independently of next-source
readiness: every healthy guard ACK independently witnesses known-zero admission,
publication and transfer controls. The final owner SHA is
`b6280f6a894ec120f0e57415d5cc6da7b9e193a65f42b1d7f9789cbdbaa5d648`.

The two-bit local generation is not an arbitrary-age certificate authenticator.
There is no external certificate queue in this prototype. Wrap requires real
read completion and no outstanding bank reference; common reset requires fresh
purge. A fabricated matching toggle from an unqualified external issuer is not
made safe by a two-bit tag. Six clean lifetimes exercise wrap with empty owners.

## Reset premise: documented, not inferred from silence

AMD PG109 v9.1 (May 4, 2022), pages 11–12, states that synchronous reset
reinitializes FFT outputs/state/counters and pending load/transform/unload work;
its internally registered reset must be asserted for at least two clock cycles.
This is the vendor interface premise used here, not a new measured latency.
[Official PG109](https://www.amd.com/content/dam/xilinx/support/documents/ip_documentation/xfft/v9_1/pg109-xfft.pdf)

The installed 2022.2 core is v9.1 revision 8. The accepted generated wrapper has
`C_HAS_ARESETN=1`, `C_HAS_ACLKEN=0`, `C_THROTTLE_SCHEME=0`, 512 points and an
actual reset connection. The generated example's five released waiting cycles
are an example, not an additional documented guarantee. This prototype requires
the documented two sampled reset cycles, an extra known-quiet released edge,
and the real configuration READY handshake. It observes raw faults throughout.
An arbitrarily late untagged but plausible old status/result after new full input
cannot be distinguished by assigning it a current phase tag. Actual-core reset
and cutover qualification is therefore still a required separate gate.

Reference source receipts: accepted factory `0795ea7e...`, XCI `80c403b3...`,
generated wrapper `4f4cccc8...`, generated example `632d6aef...`. These are
reference inspection only; no encrypted source was decoded or vendor model run.

## Executed matrices and numerical limits

The 17 immutable baseline files (nine RTL, eight vector files) are pinned in
`tests/starlink_oracle/retained_output_prototype.py`. They are exact copies from
the accepted R1/B1/O1/L1 run, not regenerated goldens. The FFT-port script returns
those fixed words and independently checks every core input against the frozen
sample/product vectors. The actual unchanged join/product arithmetic executes.
This is **SCRIPTED_NOT_FFT**, not an FFT algorithm or vendor timing validation.

| Gate | Final offline evidence |
|---|---|
| Default and guard preservation | Default wrapper equals original unconditionally; every guard output and original state bit compared, even when invalid; original 23 healthy / 37 rejected / 12 reset stimulus preserved |
| Healthy overlap | Three blocks: 1,536 source writes and every 1,536 forward/product/inverse/read word checked; status at raw ordinal 2; independent metadata/index/exponent checks |
| Real reader phases | Nominal, periodic READY, parked-reader, ACK during F output, and held final prefetch through F handoff; next I waits for registered actual release |
| Raw cutover | 14 sampled offsets × 8 raw/unknown stimuli; every distinguishable fault rejects, preserves sticky reasons and compares all visible healthy prefixes |
| Original fault boundaries | RAW_READY_CERTIFIED_ACK kinds 3/4/5 and late 7/8/9/10; exact final veto tests retained; 128–132 slow prefix with legitimately admitted next F, no further publication |
| Reset | Both raw-reset sides × three full-overlap phases, old inverse unread/F input active, slow clock paused, fresh exact third-fixture replay; eight independent already-full source/purge cases |
| Lifetimes/deadlines | Exact 8,192 active missing-output/status deadlines; 9,899-cycle retained wait does not invent an active timeout; stopped reader explicitly fails the original 25,000-fast harness drain bound |
| Structure/admission | Known exact public opt-in guard tests, literal source inverses/mutations, LS_/multi-suffix graph controls and declared-state inventory |

One frame=1 offer at publication+13 equals the natural first-new-input frame=1.
It is explicitly **unobservable**, not a detected fault; that case must complete
the full healthy numerical replay. X/Z injection uses explicit producer values,
not OR logic that could hide an unknown behind an existing one. The separate
cutover unit delegates phase-legal events to the exact owner guard; the complete
composition checks their actual context without an event-observation gap.

No source/ownership state is forced in the new composition. Test-only scripted
producer fault controls drive FFT interface events. The unchanged older guard
stimulus retains its own original adversarial behavior, separately identified.

## Measured scheduling, not lower-clock qualification

Final clock model matches the original accepted bench: 1 fs precision,
2,857,143 fs fast half-period, 5,000,000 fs slow half-period. First edges and
half-periods are asserted; declared slow pauses retain the original edge grid.
Clock-driving benches alone were corrected from an earlier 1 ps rounding.
Earlier 17/415 runs remain evidence at 2,857,000 fs, not exact-original-clock runs.

| Reader profile | Next-F dispatch | Observed recurrence in final model |
|---|---:|---:|
| Ready continuously | 8 fast clocks | 3,645 F-admission / I-publication clocks |
| READY 13/17 slow edges | 8 | 3,645 |
| Park read until after F completion | 8 | 4,911–4,912 |
| ACK during F output or final handoff | 8 | 3,645 |
| Protocol-only 9,000-clock initial park, two blocks | 8 | 11,711 I-publication clocks; 9,899 maximum real-ACK wait |

The nominal pair consists of two scripted 1,810-clock transforms, the unchanged
17-clock forward handoff, and the measured eight-clock inverse producer transfer:
`1810 + 17 + 1810 + 8 = 3645`. Unlike the old shared `guard_busy`, an old reader
does not unnecessarily block a new forward context. A full product bank still
blocks another forward; next inverse still needs genuinely reusable output.

A real ACK during next-F input is unreachable under this clock/geometry:
the earliest 512-word slow read plus CDC ACK is about 904 fast clocks after
publication, but the next F input span ends at publication+525. The tests do not
fake an ACK or stall the realtime input to manufacture that combination.

The tested 3,645 and 4,912 values are below the 5,215-fast-cycle allowance for
447 canonical samples at 15 MS/s and a nominal 175 MHz compute clock. The long
parked case is protocol evidence only, not throughput. `capacity_claim` in raw
receipts refers only to the explicitly bounded scripted profile; it is never a
physical capacity claim. Converting 4,912 clocks to another clock is only a
constant-cycle sensitivity calculation: real reader/CDC cycle counts also change
with clock ratio. No 130/140/125 MHz replay or timing closure is established.
Concrete downstream stall/drain bounds are needed before any lower-clock plan.

## State and graph budget

The Icarus inventory counts 2,480 non-array declared variable bits versus 2,257
in the unchanged composition: **+223**, not the proposal's illustrative 16–24.
The delta is one additional 180-bit clocked guard, 17 owner bits, 17 cutover bits
and nine fresh-epoch barrier bits. Read-only view ports add no state. The same
three 512×36 payload arrays and unchanged kernel ROM remain. No FFT/DSP is added.
These are source/elaboration declarations, not mapped FF/LUT utilization.

The final conservative continuous-node graph contains 5,893 nodes, including
69 `LS_` nodes. It rejects unresolved `L`/`LS` continuous references and deliberate
cycle/suffix mutants. Other references are cuts without complete definition/type
validation, and operations/functions have no allowlist. Thus this helper does
not establish that every cut is genuine state or that every unknown operation
is supported. Parent review is separately auditing the actual saved netlist;
typed missing-variable/unknown-operation mutants remain a future gate obligation.
This is neither synthesis, Boolean reachability nor a physical timing result.
The owner release refinement was rechecked within that stated graph scope,
not merely argued phase-excluded.

The parent separately audited the actual saved graph with complete referenced
`v`/`L`/`LS` definitions, state-cut type checks, an operation allowlist and the
reviewed pinned pure boundary-rounding function. That independent audit passed
the same 5,893 nodes / 69 `LS_` nodes and seven parser controls, including
missing-variable, unknown operation/function and LS-cycle controls. It does not
retroactively add those capabilities to the frozen helper above.

## Final replay and receipts

Final original handle `19306` terminated zero: **415 passed in 38.28 s**.
Host: `gauss`, x86_64 Linux; Icarus 12.0, the existing Python 3.11 environment.
No ARM/Zynq runtime measurement is implied. Ruff F/E9 passed for the new helpers.
The parent independently replayed the immutable 46-file closure: original
`46498` terminated zero, **415 passed in 45.77 s**, with every source receipt
unchanged. Parent repeat/strict graph audit remains separately retained at
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained415-parent.NuSfm0Ii`.

Frozen portable source root:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-output-prototype-final-v1`.
Its `source.sha256` binds all 46 source/import/configuration files, SHA
`a4dfa8d603d1d7782b51106c6224a3dc6dfbc67d07e241abac8d7c390f83aeb8`.
The full raw preparation tree is retained at the sibling
`retained-prototype-preparation-v1`, including `source-v19`, `pytest-v19`,
`pytest-v19.log` and `results-v19.xml`. Each generated bench, compiler diagnostic,
simulator output and original compiled executable remains there.

The compact portable package is `artifacts/retained-output-prototype-v1.tar.gz`
with an adjacent SHA/length receipt. It contains the final replay closure,
the development source snapshots, logs/XML/expanded benches, and a complete
SHA-256/length inventory of the original raw tree. Most generated VVP executables
remain in that raw tree and are inventory-referenced rather than duplicated;
the final graph VVP is included for independent structure inspection. Symlinks
are recorded, never followed or included as archive members. The standalone
collector is packaging tooling only, not part of the 415-test source identity.
No prototype push was performed in this lane.

Replay from the frozen `source` directory, using a new non-`/tmp` result folder:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH TMPDIR=<new-result-folder> \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest -q \
  tests/test_starlink_retained_output_prototype.py \
  --basetemp=<new-result-folder>/pytest -p no:cacheprovider \
  --junitxml=<new-result-folder>/results.xml
```

## Preserved development failures

All original attempts remain, rather than being relabeled by the final PASS.
They include import-closure collection failures; the initial genvar connection
compile issue; repeated level-sensitive forward closure (new cutover reason80);
a parked-reader test incorrectly demanding simultaneous reads; a guard-output
inventory typo; duplicated offset0/1 stimulus indexing found before final freeze;
natural-frame and OR-masked-X collision tests; and a long-reader assertion that
incorrectly used the first forward interval instead of retained lifetime.

The original owner also allowed a same-edge release pulse with contradictory
controls before its registered reason. The first known-zero fence fixed those
negatives but blocked a legitimate still-pending receipt/ACK coincidence. Both
versions and parent independent counterexamples are preserved; final `b628...`
accepts the valid coincidence and rejects invalid or unknown controls. These
were standalone-boundary findings, not demonstrated top-level reachable failures.
The final clock-precision correction preserved all numerical expectations and
limits; its separately retained direct replay passed without further adjustment.

Next gate is parent review of this frozen source, followed only by separately
authorized actual-core preparation/execution. The broader native15/30/60 +
canonical15 coarse +2.5 pilot paired scanner goal is unchanged. This island proof
does not qualify RF accuracy, causal acquisition, continuous native capacity,
complete production maps, host deadlines, IIO or a physical FPGA implementation.
