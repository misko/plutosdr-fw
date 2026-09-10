# Forward-only certified retirement: functional comparison

Both actual-core modes pass and their complete trace CSVs are byte-identical
to payload-bubbles-v1. The new forward-only output matches the frozen old
public return masked by phase; no raw-private retirement is introduced.
This change has **no synthesis or route result**. The prior measured design
still fails 175 MHz at −1.559 ns and remains an immutable negative checkpoint.

Actual-tested RTL is `ae42e59cb4198d1e2c7321dea04f0240acda1f12`, FW
`ce987ffe5ef3b7a1e8780cd99e37b64bba90ea99`. Seven RTL files, the actual bench
and its frozen shadows were committed before both runs and still byte-match
their freezes. Subsequent changes only bind unused default-off ports in two
legacy benches, adapt one test-only instance anchor, and add a literal inverse
check. No actual-core rerun or RTL change followed those testbench fixes.

## Exact interface contract

The real explicit-commit output mailbox computes current framing fault C as
`input_valid && input_ready && !input_framing_valid`. Its wrapper input_valid
is literally `return_private_valid && next_inverse`, so **C implies
next_inverse**, regardless of payload, ordinal, TLAST, cursor, READY or healthy
job state. C is therefore zero on the forward joiner's `!next_inverse` phase.
This is a functional wiring invariant, not a timing exception.

The guard adds default-off USE_FORWARD_RETIREMENT, inputs inverse_phase and
forward_mailbox_fault, and output forward_retirement_valid. The wrapper opts
in only under REGISTERED_SCHEDULING, supplies the same next_inverse phase and
the sticky output_bank_fault, and selects the new output only for the forward
joiner. Its existing fast-fault, product-bank READY and kernel handshake gates
remain. Default mode keeps the original joiner expression.

The parallel output retains every old nonfinal/final predicate and substitutes
only the sticky mailbox fault for the original sticky-or-current mailbox input.
The original mailbox_input_fault connection, public/private/commit outputs,
faults_now, reason accumulation, active/ACK state, final commit and controller
remain literally unchanged. No fault is delayed and no bank publication or
ownership release uses the new output. The existing default, phase-input and
completed-input fault branches are all tested independently.

Strict whole-source inverses restore guard and wrapper to `ce6a885e`; the other
five RTL modules are unchanged. The guard reference is an exact module-renamed
copy of that pin, not a shared new predicate. All pre-existing actual stimulus,
assertions, trace writes and numerical comparisons restore literally after
removing only the additive shadow and receipt blocks.

## Two distinct proof scopes

The fast bench drives arbitrary identical internal guard snapshots, with the
actual mailbox RTL computing C from the production phase-masked input-valid
wiring. This is not natural bank-lifecycle or FFT numerical simulation.
All eight ENABLED/COMPLETED/PHASE_INPUT settings pass 13,833 rows each:

- 640 state/phase/readiness/current-cause combinations, including inactive,
  active-input, nonfinal, unqualified/qualified final, ACK, empty and quarantined
  snapshots; matching and malformed status/output events, ownership, watchdog,
  duplicate input certificates, simultaneous faults and invalid X payloads.
- 900 rows cover all 75 metadata bits including header/bit 74, both phases,
  first/interior/final mailbox cursor and both ownership READY states. Metadata
  is ignored on the first word exactly as in the original mailbox.
- 12,288 rows exhaust all 512 raw positions, both TLAST values, three cursors,
  both phases and both READY states, with changing numerical payload.
- Same-edge and next-edge exact reason accumulation under fixed snapshots,
  phase flip, sticky fault and common-epoch reset checks.

Every old guard output bit, including invalid payload, is compared against the
136-bit frozen full-output tuple. The new output is compared against
`ENABLED && old_valid && !inverse_phase`. Phase-mask removal, wrong phase
wiring, sticky-veto removal and full/nonfinal raw-private substitutions all
fail their specific forward-retirement mismatch witnesses. Deliberately forcing
C=1 while inverse_phase=0 is rejected as a broken caller invariant, not counted
as an equivalent legal interface. Known binary phase is required; unknown
invalid payloads are exercised, but an unknown/independently forced phase is
not declared legal. Global old outputs/reasons are never weakened to hide it.

The unchanged actual-core suite separately proves natural runtime behavior and
the original arithmetic/metadata/fault traces at 100/175 MHz. An added frozen
full old guard compares every old output and the phase-restricted new output
on both clock edges. A second frozen arithmetic chain is driven from that
**old certified return**, not the candidate joiner input. All previous shadows
and their assertions remain active.

| Actual observation | Default | Registered |
| --- | ---: | ---: |
| New frozen-guard comparisons | 651497 | 1179897 |
| Old valid forward-phase observations | 75165 | 140701 |
| Current inverse output-bank framing fault observations | **0** | **0** |
| Sticky output-bank fault observed in forward phase | **0** | **0** |
| Maximum nominal admission interval, fast cycles | 4540 | 4548 |

The zero corruption counters are explicit limits: these actual runs do not
inject post-guard output-bank corruption. That raw-predicate coverage belongs
to the fast snapshot bench above, not to the numeric FFT runs.
Both actual runs retain 44 healthy blocks, ten fault cases, 24,064 forward and
product words, 22,658 inverse words including 130 provisional prefix words,
four purge cases, all reset/handoff/retirement checks, 84 preflight boundary
rows, 12 expected-cache rows and 12 active-input corruption cases. Registered
private readiness/admission/masked-start counts remain exactly 44/8/60.
The new combinational output adds no cycles or logical FF/BRAM/DSP state.
Mapped LUT cost, realized timing path removal and power remain unmeasured.

## Retained failure and testbench compatibility fix

The first expanded regression ended **745 passed / 10 explicit physical skips /
30 failed**. Twenty-three failures were genuine bench-interface elaboration
errors: two legacy `.*` guard instances lacked inverse_phase. They affected four
final-authorization rows, four phase-input rows, twelve final-veto rows and
three occupancy rows. The remaining seven failures were already-known missing
files in the uninitialized Linux submodule; no dependency was initialized.
The complete failure log and original two benches/test anchor are archived.

After both original actual sessions finished, only explicit inert bindings
`.inverse_phase(1'b0), .forward_mailbox_fault(1'b0), .forward_retirement_valid()`
were added to those two default-mode benches. USE_FORWARD_RETIREMENT stays zero.
The one Python phase-parameter substitution anchor was adapted to the new
literal instance text. New strict inverses restore both complete benches and
the complete Python test; no stimulus, assertion, parameter choice or expected
mutation failure was relaxed. All 23 affected cases plus the final 17 new tests
pass: **40 passed**. The earlier combined focused suite was **55 passed**.
The final expanded regression is **769 passed / 10 existing physical skips /
seven failed**, all seven being the same missing-Linux-file failures, with no
remaining wildcard elaboration errors. Both regression receipts and every skip
reason are retained. The uninitialized Linux gitlink is
`4357f41a721df9d89a66be7a2a3f921a71d46bad`; affected files are five map-driver
tests, one DMA-backend test and one pilot-driver test, with exact IDs and
FileNotFoundError tracebacks in the raw logs. Ruff and diff checks pass.

## Frozen receipts and limits

Original default session 59515 exited 0 at 2026-09-10 04:58:19 UTC; registered
51933 exited 0 at 04:59:59 UTC. Runs remain at
`/tmp/starlink-completed-input.5EaJuD/forward-retirement-default-v1` and
`/tmp/starlink-completed-input.5EaJuD/forward-retirement-actual-v1`.
Raw simulation logs and CSVs are under
`project/fft_bank_owned_slice.sim/sim_1/behav/xsim/` in each run.
Original focused session 61235 exited 0 (55 passes); affected-case session
17884 exited 0 (40 passes). Expanded sessions 23495 and 29501 exited 1 with the
preserved 745/10/30 and 769/10/7 results respectively. Logs are the matching
`forward-retirement-unit-v2.log`, `forward-retirement-affected-v1.log`, and
`forward-retirement-regression-v1.log`/`v2.log` under the same temporary root.

| Artifact | SHA256 |
| --- | --- |
| Wrapper | `363e4315fcc2df75fabd116ffced055bc569ba3dfd9bbcd92c7dd7be8713eee8` |
| Guard | `09ab35339d55ddf88e813830322d21574d0794c489c9749f68113e9da7807be2` |
| Default actual log | `1bc6113733e0bad7ca9d1917b2746610dfe78cf4428e750f918a13d3f4851cb1` |
| Registered actual log | `4955d348d58f38106134a50eafc59de9c9bb3ec398581c9bbd27d27b076ca106` |
| Default complete CSV | `b0d60e80101b34ff163b85ef7547814e0403561b315f975eb38a98817b7eb84d` |
| Registered complete CSV | `25ab9d06ca0e03f280540cda625a7826b3c4cbaa6322ce3266c59e1fbad94122` |

Archive `hdl/library/starlink_pss_acquisition/evidence/forward-retirement-v1/`
holds raw receipts, both source/vector freezes, all unit and mutant outputs,
the failed and corrected regression logs, literal-inverse harness sources and
trace hashes. SHA256SUMS covers the archive; complete CSVs remain in their
original paths. No new synthesis, route, timing waiver, receiver build, radio,
PPU, production BD, main, remote push or promotion occurred. The previous
negative physical evidence remains unchanged. A physical decision requires
separate root review and explicit authorization.
