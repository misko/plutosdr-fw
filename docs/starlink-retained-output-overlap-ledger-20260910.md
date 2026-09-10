# Retained inverse-output / next-forward overlap: offline feasibility

Status: source-specific scheduling proposal, not implemented RTL, new vendor
simulation, physical timing closure, continuous-source capacity, or RF evidence.
The same one FFT, product DSP chain and three payload banks are assumed. No
runtime, clock constraint, numerical cohort, or completed 30/60 harness changed.

## Outcome

The accepted 175 MHz L1 trace contains avoidable *controller serialization*:
every one of the 36 opportunities for a following job already has source N+1
full at inverse N publication. All 38 inverse jobs have consumed their product
bank input before publication. The FFT is idle while the old inverse output is
read by the separate 100 MHz reader, because one result guard and scheduler
retain their consumer-ACK obligation.

| Measured quantity | Nominal, 32 blocks | Stalled, 6 blocks |
|---|---:|---:|
| Forward admission-to-publication | 1810 fast clocks | 1810 |
| Forward publication-to-inverse admission | 17 | 17 |
| Inverse admission-to-publication | 1810 | 1810 |
| Inverse publication-to-real output ACK | 904–905 | 1177–1178 |
| Inverse publication-to-next forward | 911–912 | 1184–1185 |
| Successive forward admissions | 4548–4549 | 4821–4822 |

These are two profiles of the same accepted run, not 38 new experiments.
The slow profile has READY on 13 of every 17 slow edges and three producer
pause edges after each word whose index is a multiple of 13. An indefinitely
stalled reader is not covered by either throughput result.

## Frozen evidence and executable derivation

Worktree: `/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired`, branch
`codex/starlink-rx-only-do-not-merge-high-rate60-paired`.
Recipe was committed **before counterfactual evaluation** at
`558889a282f16ab64028b96690359bfae277c7d6`; final tested model/tests are
`db4945dd4b13dfa9e40325b72620f3543bf5664b`.
HDL remains `ecbb3712965ff39b144b5adf84a2a262c6c53dff`.

New files are `tests/starlink_oracle/output_overlap_recipe.json`,
`tests/starlink_oracle/output_overlap_ledger.py`,
`tests/test_starlink_output_overlap_ledger.py`, and this report.

The original accepted actual directory is
`/tmp/starlink-coarse-alternatives.Y3JzOI/bank-arithmetic/hdl/library/starlink_pss_acquisition/build/local-admission-actual-R1B1O1-L1-175-prepared-v4`.
Within its `project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim` directory:

| Input | SHA-256 |
|---|---|
| `fft_bank_owned_trace.csv`, 35,662,681 bytes / 590,066 data rows | `e7127798f315772b95aff63b75fffcd9cf5d1af8ca3c96e878bae4b39e443d71` |
| `simulate.log` | `ead881d85bbcc6325e6300b8b26ef62ada0db4defce9ae91962db726c1f85e74` |
| Recipe | `1fb118404547d0a3eb13f72d969a5ee80687aec5a388c285839106d1e7fcc688` |
| Final `proof-v3/ledger.json`, 450,695 bytes | `7d50829165b7ee6d5599646a44a719a45279d92cb1dd3cd0a37f40f660073594` |

Final evidence root is
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/output-overlap-ledger-v1.Zha6fEKf`.
`proof-v3/ledger.json` contains all 38 original block ledgers and 12 separately
labeled conditional schedules. `proof-v3/integrity.json` binds nine input/source
files before and after derivation; eight small files are copied for review.
The complete original CSV remains external and pinned, not redundantly copied.
Replay uses the committed repository plus that original CSV/log; the flattened
review snapshot is not advertised as a standalone package layout.

All 76 jobs must match 512 actual input edges (including the one gap), 512 raw
output edges, third-word status, configuration, and qualified publication.
Every source capture/start/full coordinate, producer-ready observation, product
publication/visibility, slow output start/final read, and real ACK must match
before the helper evaluates any alternative. Block 0 records the initial
source-ready observation rather than inventing a preceding consumption.

Fast edges use `(2*c+1)*2,857,143 fs`; slow edges use
`6,300,000+10,000,000*s fs`. The mailbox recurrence independently accounts two
request synchronizers, read-start, prefetch, all accepted reads, and two return
ACK synchronizers. CSV observations are pre-edge, distinct from post-NBA wire
changes. For example source block 1's ready wire is observed at fast 1466;
its first producer acceptance is slow 838. They are not the same event.

The output-reader model has a defensive **25,000-fast-clock, publication-anchored
offline cap**. This is explicitly not the original whole-bench `await_results`
anchor. The original 25,000-fast drain, 1,500,000-fast whole bench, 8192 active-job
watchdog, 24-clock fault observation and [128,132] provisional-prefix gates
remain unchanged requirements for a future actual test, not newly proven gates.

## Minimal new ownership boundary

At a fully qualified inverse publication, transfer only the *consumer obligation*
to an independently retained context: accepted descriptor/lease, published owner,
reader-reference and real final-read ACK/release state. The current producer's
512 checked outputs, matching independent status and current fault fence must
already be complete. Do not declare a private final take or a status receipt to
be publication. Do not fake the old mailbox READY/ACK.

The current producer/result guard can then become idle and execute the existing
core reset/configuration sequence for F(N+1), while the old bank keeps I(N).
The next inverse still cannot reserve that output bank until the old final
read's real synchronized ACK and parked-context clearing. F(N+1) may finish into
the existing product bank while waiting; no second forward may overwrite it.

The proposed eight-clock handoff is explicit, not measured: inverse publication
at n parks the consumer and closes active producer work; n+1 observes the
registered result commit; n+2 obtains a completion receipt; n+3 changes to RESET0;
n+4/n+5 retain the two reset states; n+6 discovers source/product-bank capacity;
n+7 validates the descriptor; n+8 admits forward. This requires a reviewed
producer/consumer split at n. Adding an unreviewed transfer stage changes this
number and must be charged. A following inverse also waits at least one clock
for the parked context to clear after real ACK, then two discovery edges.

Current code cannot perform this schedule unchanged:

- Frozen result guard `09ab3533...`: lines 159–171 include `awaiting_ack` in busy
  and job admission; 283–284 retain the old descriptor during that wait;
  363–365 clear the wait only on actual mailbox readiness. A new, default-off
  ownership contract is needed, not a force or a per-job reset of this guard.
- Frozen L1 top `0cb54617...`: lines 326–329 and 431–434 wait for real output
  readiness and guard idle before changing phase. The corresponding P1 top
  `8923b42b...` uses lines 376–379 and 501–504. Its source/product/output banks
  are separate; inverse product reads finish at admission+517, well before
  inverse publication at admission+1810.
- Current inverse sealed issuer `8ad9c2e7...`: lines 50–52 classify phase change
  with an old reference as `phase_lost`, and any raw core output while
  `final_taken` remains set as `raw_orphan`. Lines 64–69 also use the *current*
  guard busy state in old producer/certificate idle and lease release. Merely
  allowing the scheduler to advance therefore faults; masking only phase loss
  still leaves false orphan classification and stalled release during new F.
  Separate immutable current-core-job ownership from retained-consumer ownership.

Metadata/control storage is small in kind, but not a mapped resource claim:
one illustrative parked record is 75 descriptor bits + 2 lease bits + 6 state
bits + an optional 13-bit observation-age field = 96 bits. The existing bank
already retains descriptor copies, so some fields may be reused after a proper
interface proof. Exact state, timeout semantics and whether a second full guard
is avoided require implementation review. No new payload RAM, FFT or DSP is
required by this proposed schedule; that is not yet a synthesis result.

## Executable counterexamples and fault/reset requirements

The tests include an explicitly abstract retained-owner model, not RTL execution.
They demonstrate rejection of early/wrong-lease/stale ACK, premature next inverse,
unclosed producer handoff, new-phase/old-issuer false faults, shared-busy release
coupling, and lease ABA after a common reset. Local core reset leaves the old
consumer intact. Common reset disables rearm until a fresh slow-domain purge
receipt and empty references; a paused slow clock cannot supply that receipt.
Two-bit equality alone cannot reject arbitrarily old certificates or ACKs.

Future RTL must retain these additional boundaries:

The model's `producer_closed` Boolean is an assumed premise, not a closure
proof. Moving the old guard's ACK wait earlier shortens its original raw-event
surveillance interval. A concrete cutover fence must cover publication, transfer,
every local-reset edge, reset release, new admission/configuration and the first
new input/result events. No event may disappear between observers or be tagged
as new merely because the scheduler phase changed. The accepted actual bench's
RAW_READY_CERTIFIED_ACK kinds 3/4/5 (frame/status/output at handoff), 7/8/9/10
(vendor/frame/status/output after ACK but before controller drain), inverse
final/postcommit veto cases at lines 628–640, and prefix case at lines 641–658
must remain executable. Add their inverse-publication-to-next-F counterparts,
including an old matching status immediately after new private admission and
at first new output. Preserve the unit guard's absent, late, mismatched, padded,
duplicated and idle-orphan status cases and all eight current final-edge vetoes.
Passing `producer_closed=True` in the abstract model establishes none of these.

- A held final payload is taken once; delayed validation drains before publication.
  Duplicate status, extra current raw output or a current fault must still veto
  publication on the same owning edge.
- Old I(N) metadata and ACK identity cannot follow new F(N+1)'s engine descriptor.
  A real ACK during new F's busy interval releases only the old consumer, not F.
- Current vendor events belong to the actual core job. Before the next job,
  qualified reset/drain and idle-event checks remain mandatory; vendor raw outputs
  contain no arbitrary job-generation tag that could magically detect every
  plausible stale word after a broken reset.
- A common fault quarantines both unfinished obligations. Already accepted slow
  words cannot be retroactively withdrawn. Fault visibility follows its actual
  domain and CDC latency; do not promise zero slow-prefix exposure after a raw
  fast event or reuse a failed epoch merely because its reader finished.
- Pause the slow clock/read READY through old ACK while new F executes; prove
  F may finish privately but next I waits, source N+2 remains separately owned,
  no bank is overwritten and explicit reset recovery is fresh.

## Conditional rate arithmetic, not physical qualification

With the eight-clock transfer assumption, both finite original profiles give
**3645 clocks per pair**, versus measured nominal maximum 4549. Every new forward
input beat occurs while the preceding output bank is owned; the independently
modeled slow reader accepts 222–293 words during that forward input span at
175 MHz. These are counterfactual clock-edge counts, not new actual overlap
witnesses. The first proposed next-F admission is 4590 instead of actual 5493;
the preceding real ACK remains 5486, and proposed next-I admission is 6417.

| Hypothetical fast clock | 3645-cycle pair | With separate +24-cycle sensitivity |
|---|---:|---:|
| 175 MHz | 20.829 us | 20.966 us |
| 150 MHz | 24.300 us | 24.460 us |
| 140 MHz | 26.036 us | 26.207 us |
| 130 MHz | 28.038 us | 28.223 us |
| 125 MHz | 29.160 us | 29.352 us |
| 120 MHz | 30.375 us | 30.575 us |

447 canonical samples at 15 MS/s allow 29.8 us. Holding the measured service
cycles fixed gives these conditional minima: two admission-to-publication
intervals alone, 121.477 MHz; proposed dispatch included, 122.315 MHz; with
the +24 sensitivity, 123.121 MHz; original 4549-cycle schedule, 152.651 MHz.
They are not fundamental FFT lower bounds or recommended clock settings.
At 125 MHz the +24 case leaves only 0.448 us / 56 clocks, so unmodeled latency
matters. No frequency other than the original 175 MHz was physically or
numerically simulated here. No timing constraint was changed.

This alternative does not resolve P1's failing 175 MHz route. That report's
top 20 paths contain two producer metadata cones (worst -1.492 ns), sixteen
product-read metadata-to-input-guard cones, and two distinct M1 ROM metadata
cones. Honest product staging needs *both* checked private write/seal and a
checked read-payload token before inverse core consumption; caching a descriptor
or delaying a fault register alone does not remove all checks safely. The ROM
cone remains separate. Scheduling overlap and staged validation are distinct
proposals; no automatic union of L1/P1/E1/K/M/C1 is implied.

## Tests, retained attempts and reproduction

On host `gauss`, final original process 23590 exited 0: **111 passed in 2.65 s**;
Ruff `--select F,E9` passed. Final derivation original 35361 exited 0 with
`PASS_ALL_38_BLOCKS_76_JOBS` and nine identical before/after source receipts.
Parent independently read the full helper/tests/recipe and repeated the same
111 tests: original 83965 exited 0, 2.70 s, with unchanged source hashes, retained
under `recovery/output-overlap-parent.mi8Jsngm`.
These runtimes describe Python on this host, not Zynq or real-time capacity.

The first test run (37684) retained 106 PASS / 1 FAIL: a handwritten specimen
expected source-ready at 1468 instead of S2-derived 1466. Only that specimen was
corrected; recipe/model/actual source coordinates were unchanged. Its exact
three source files, log and XML remain in `attempt-v1-sources`, `pytest-v1.log`
and `results-v1.xml`. The intermediate 109-PASS run and proof-v2 are retained.
Subsequent self-review tightened the offline loop's domain labeling from slow
iterations to the explicit fast-clock cap and added two boundary tests; no
healthy timeline or counterfactual dispatch number changed.

From the pinned worktree, with a unique non-/tmp output parent:

```sh
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH TMPDIR=<parent> \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest \
  -p no:cacheprovider tests/test_starlink_output_overlap_ledger.py \
  --basetemp <parent>/pytest --junitxml <parent>/results.xml

env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B \
  -m tests.starlink_oracle.output_overlap_ledger \
  --trace <accepted-actual>/project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim/fft_bank_owned_trace.csv \
  --log <accepted-actual>/project/fft_bank_arithmetic_actual.sim/sim_1/behav/xsim/simulate.log \
  --output <new-absent-output>
```

Next gate is a reviewed explicit producer/consumer owner interface, followed by
bounded offline RTL checks and separately authorized actual overlap at the
unchanged clock. Any lower-clock choice would then need its own actual numerical,
full service/deadline/CDC/reset and physical timing qualification. The eager
512-word source bench does not prove continuous canonical/native60 buffering,
full-map capacity, paired scanner timing, causal acquisition, or RF accuracy.
