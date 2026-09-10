# FFT/product/IFFT island first slice — experimental, no physical qualification

The runnable first slice removes the intermediate 100 MHz forward-result /
product-return trip by running the existing realtime FFT service, kernel join
and exact spectrum product on one 200 MHz simulation clock. Actual generated
FFT simulation passes. This conservative version still retains both local
mailbox RAMs, their local toggle/ACK protocol, and the per-job reset/configuration
sequence. It is not instantiated in any receiver.

The useful conclusion is limited: there is nominal service capacity at 200 MHz
with explicit outer-bank overlap; this version cannot sustain canonical 15 MS/s
at 150 MHz. Its nominal 175 MHz projection has just 33 fast clocks of slack per
447-result block. These are scheduling results, not physically achieved clocks.

The complete objective remains continuous canonical 15 MS/s coarse processing
at source rates 15/30/60 MS/s, original source samples for sparse native fine
search, continuous 2.5 MS/s pilot IIO inspection, .18 qualification before PPU
Ethernet .17, and eventually eight targets with 120 ms visits over about 300 s.
No radio, PPU, deployment, remote push, merge, detector removal, constraint
waiver or complete-receiver build was performed here. Sample spacing does not
establish timing accuracy.

## What was implemented

- `hdl/library/starlink_pss_acquisition/starlink_pss_fft_island_slice.v`: a
  single-clock, one-block-at-a-time wrapper around the unchanged checked service,
  unchanged one-cycle kernel join and unchanged three-stage spectrum product.
  Products loop directly into the freed service input bank. The existing
  four-word transform FIFO is not needed in this serial composition: the
  service input bank has been completely consumed before forward output starts.
  Ready/valid and the elastic product still handle bounded output stalls.
- `hdl/library/starlink_pss_acquisition/tb/tb_starlink_pss_fft_island_slice.sv`
  and `simulate_fft_island_slice.tcl`: actual generated fixed BFP18 FFT,
  immutable vectors, per-clock trace, exact intermediate/result checks, reset,
  flush and fault probes. The runner checks all existing generated-core
  generics and uses `general.maxThreads=2`; evidence directories cannot be reused.
- `tests/starlink_oracle/fft_island_budget.py`: parses only a passing actual-core
  trace and models explicit outer ingress/egress bank ownership and retention.
  It verifies the six frozen numerical-vector hashes before reporting.
- `tests/starlink_oracle/test_fft_island_budget.py`: eight passing tests cover
  nominal rate classification, retained energy expiry, bounded sink stalls,
  insufficient repeated service margin, excessive sink stalls, bad inputs,
  missing references and rejection of failed simulation evidence.

The FFT configuration is unchanged: 512 points, C_ARCH=1, fixed 18-bit input
and output, 16-bit twiddles, block floating point, convergent rounding, natural
order, realtime throttle and separate status. The signed spectrum product
retains its original divide by 2^18, ties-to-even rounding and saturation/fault
behavior. There is no substitute FFT or direct-correlator numerical contract.

## Measured cycle budget

All measurements below came from Vivado 2022.2 behavioral simulation of the
actual generated core at a 5 ns clock. Cycle differences and inclusive transfer
spans are distinguished in the trace-derived JSON.

| Component | Observed fast clocks |
| --- | ---: |
| Initial complete local input-bank transfer | 512 |
| First raw input to forward admission | 516 |
| Admission to config handshake, each transform | 2 |
| Config handshake to first accepted core input | 2 |
| 512 accepted core inputs, inclusive span | 513 |
| Last accepted input to first raw output | 781 |
| 512 raw outputs, inclusive span | 512 |
| Last raw output to checked bank commit | 1 |
| Admission to checked commit, each transform | 1809 |
| Forward admission to inverse admission | 2334 |
| Commit to next admission during forward loop | 525 |
| First island input to first inverse output | 4664 |
| First island input through last inverse output, inclusive | 5176 |
| Consecutive first-input interval including local ACK/idle lifecycle | 5182 |

The 525-clock interval includes local forward-bank reading, overlapped ROM /
multiply / inverse-bank writing, synchronizers, ACK drain, reset and admission.
It is not 525 clocks of idle overhead. The actual input is not a continuous
512-clock delivery: there is one additional input-transfer clock. Independent
status was observed 1299 clocks after admission; every transform had exactly
512 checked inputs, 512 outputs, one config, one status and one commit.

For context, the earlier read-only `shared-realtime-service-v3` service run in
the reference checkout reported 1809 clocks to commit and 2846 clocks between
transform admissions with its 100 MHz output ACK. That six-job service test
reported a 5692-clock pair interval. It starts at transform admission and does
not include all first-slice ingress work, so subtracting it directly from the
5182-clock first-input interval would not measure an end-to-end improvement.
The isolated local service comparison is 2846 versus 2334 clocks per transform;
one 100 MHz output drain costs 512 additional 200 MHz clocks. Avoiding that
cost for the final inverse drain requires an outer egress bank that can drain
while the next block computes; the bank and its ownership are charged below.

The observed first-input intervals under the implemented port profiles were:

| Port profile | Actual maximum interval | At 200 MHz |
| --- | ---: | ---: |
| One beat per fast clock on both ports | 5182 clocks | 25.910 us |
| Fast input; inverse output accepted every second fast clock | 5694 clocks | 28.470 us |
| Three extra ingress clocks every 13 words; output every second clock except four blocked clocks per 17 | 6130 clocks | 30.650 us |

The third bounded-stall profile remains numerically correct but exceeds the
29.8 us arrival interval. Passing finite stalled ordering is not a sustainable
throughput claim. Six consecutive blocks per profile are the measured sample,
not a proof of a universal worst-case service bound.

## Explicit outer-bank scheduling model

The model retains the two internal 512x36 service banks and **adds** one
512x36 ingress bank and one 512x36 egress bank. Added payload is 36,864 bits,
plus at least 145 descriptor bits and ownership/prefetch/control state. At the
usual 512x36 geometry the raw payload is two RAMB18 capacities (one BRAM tile),
but synthesis, mapping, packing and CDC have not been measured. No net BRAM
saving is claimed. The existing 512x36 kernel ROM and four signed 18x18 product
multiplies remain; their logic/control moves into the fast domain.

Ingress writes take 512 clocks at 100 MHz (5.12 us), then the island reads the
bank during its already measured 512-clock local ingress transfer. The model
keeps the outer bank busy until that read's ACK. Egress receives all 512 inverse
words at the fast rate, publishes only a complete validated result, then takes
512 clocks at 100 MHz (5.12 us) to drain. The bank cannot be reused before its
actual modeled ACK. Its drain may overlap the next forward/inverse computation.
If it has not retired by the next inverse burst, the internal completed inverse
bank waits and the measured island interval is extended by that wait.

Declared CDC scheduling assumptions are four destination clocks from commit
to readable data and three producer clocks from last-read to ACK. These are
model costs, not a new qualified crossing or event-latency bound. The model
also charges 65 slow output ordinals before the first usable result plus eight
slow clocks to request energy. That last allowance is an explicit estimate;
the downstream energy/scoring pipeline is not instantiated by this slice.

The exact-rational simulation runs 4096 blocks (about 122 ms of canonical
source time, not a 300 s run). Complete input blocks arrive every 447 / 15e6 =
29.8 us. It accounts for the first 512 samples needed to form a block and the
66-sample support before a denominator exists.

| Fast-clock projection | Nominal island interval | Slack per block | Model result with outer banks |
| --- | ---: | ---: | --- |
| 150 MHz | 34.547 us | -4.747 us | Growing queue; energy expiry by block 14 |
| 175 MHz | 29.611 us | +0.189 us (33 clocks) | No backlog under the declared nominal model |
| 200 MHz | 25.910 us | +3.890 us (778 clocks) | No backlog under the declared nominal model |

At 200 MHz the modeled maximum denominator age is 923 canonical samples,
below the existing 2048-entry cache. A 1000-slow-clock (10 us) egress stall on
every block still fits the outer-bank lifecycle in this model; it raises the
age to 1073 without stalling the island. This is precisely why that extra bank
is not free: it converts a slow downstream drain into overlappable ownership.
At 175 MHz a repeated 64-fast-clock service delay changes the interval to
29.977 us; modeled backlog grows and the energy cache expires at block 401.
At 150 MHz deeper buffers cannot correct the service-rate deficit. Failure
projections intentionally continue accounting after a real finite queue would
already fault; they do not imply that the hardware can retain that backlog.

## Publication, reset and fault contract

The 70-bit transform descriptor is `{inverse, source_block_start[63:0],
forward_exponent[4:0]}`. The 75-bit result appends the current transform's
exponent. The inverse return thus preserves source identity and both exponents.
The service checks complete input-bank framing/identity and actual core
delivery, then independent output count/order/TLAST/exponent/frame/status,
owned output storage and current faults before commit. The original certified
cause fence remains; no guessed vendor-event delay has been introduced.

Forward results become visible only after their original service commit, then
remain private to the island. Each product beat carries its unchanged block
identity and forward exponent into the inverse bank. No partial product bank
can launch the inverse transform. An inverse result becomes externally valid
only after its checked service commit. A fault inhibits output immediately
when observed and remains latched until the whole epoch is reset/flushed.
The core/checker epoch remains alive throughout the real output ACK interval;
a post-commit vendor fault is still observable and stops the remaining output.
Already accepted words are not retroactively retractable: integration must
associate them with epoch/visit fault evidence, as in the current receiver.

The outer egress bank is not RTL in this slice. Its eventual publisher must
require a complete same-identity inverse block, healthy current epoch, and
registered validation; private writes alone must never publish it. Reset or a
visit/source gap must purge both boundary banks, the local banks, arithmetic,
prefetch and ownership state together. A raw source discontinuity is not a
permissible FFT delivery stall. This bench exercises gap-driven epoch flush,
not the upstream sample-gap/index detector or the full visit protocol.

Private-before-commit output storage already existed and is preserved here;
it is not presented as a new saving.

## Executed checks and artifacts

Successful actual-core evidence:

`hdl/library/starlink_pss_acquisition/build/fft-island-v2/`

- `project/fft_island_slice.sim/sim_1/behav/xsim/simulate.log` ends with
  `FFT_ISLAND_SLICE_PASS healthy_blocks=23 exact_inverse_words=11776
  exact_forward_words=12800 exact_product_words=12800 purge_cases=4 fault_cases=4`.
- `project/fft_island_slice.sim/sim_1/behav/xsim/fft_island_trace.csv` records
  145425 simulation clocks, core transactions, bank commits and local transfers.
- `scope.txt` hashes the immutable copied sources, vectors and verified generated
  wrapper. The original reference directory was used read-only.
- `frozen_sources/` contains the exact RTL/testbench/runner/vector input snapshot.
- `reports/starlink-fft-island-budget-20260910.json` retains vector hashes,
  trace/log hashes, all 23 measured block records and nine model scenarios.

The four purge cases are reset and flush during forward input and during inverse
input, each followed by a fresh exact block. Fault cases are missing active
core delivery, a same-edge inverse final-commit vendor fault, malformed initial
input ordinal, and a vendor fault after inverse commit while awaiting output
ACK. A final fresh exact block establishes recovery only after epoch reset.

The first `fft-island-v1` evidence is retained as failed testbench evidence: its
READY-pattern counter changed on the sampling edge, causing a checker/DUT race
on the first stalled-output case. The v2 bench changes that counter on the
opposite edge and passes all profiles. No v1 result is admitted by the report
parser. There was no product RTL fix between the runs.

Reproduction from the firmware worktree (use a new output directory):

```sh
env LD_LIBRARY_PATH=/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE \
  /opt/Xilinx/Vivado/2022.2/bin/vivado -mode batch \
  -source hdl/library/starlink_pss_acquisition/simulate_fft_island_slice.tcl \
  -tclargs NEW_EVIDENCE_DIRECTORY FROZEN_VECTOR_DIRECTORY
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m tests.starlink_oracle.fft_island_budget \
  NEW_EVIDENCE_DIRECTORY FROZEN_VECTOR_DIRECTORY NEW_REPORT.json
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest -q \
  tests/starlink_oracle/test_fft_island_budget.py
```

## Costs and evidence still missing

The two actual outer CDC banks, reset/epoch coherency, their physical constraints
and acknowledgments need implementation and independent checking. The existing
overlap scheduler, 2048-entry energy cache, 447-result qualifier, normalization,
both coefficient banks and visit fencing need integration and sustained actual
simulation. This slice checks only the frozen upper-edge FFT/product/IFFT
vectors; it does not create new scored results, held-out sensitivity data,
lower-edge qualification or evidence at physical source rates 30/60 MS/s.

Moving the product and descriptor/control logic to 200 MHz can increase fast
domain placement pressure. The current complete receiver is already slice
limited; neither the extra boundary storage nor faster logic has been placed,
timed or measured out of context. No LUT/FF/DSP/BRAM utilization or WNS is claimed.
For a relevant measured starting inventory, the root task's read-only report
of saved best18c complete-receiver placement has the following hierarchy counts.
These are the original design, not resource measurements of this new slice:

| Existing complete-receiver component | Combined LUT | FF | DSP | BRAM tiles |
| --- | ---: | ---: | ---: | ---: |
| Whole IQ-to-score coarse pipeline | 3674 | 6329 | 27 | 15.5 |
| Transform service, including FFT | 1490 | 3571 | 17 | 6.5 |
| FFT alone, inside that service | 1171 | 2988 | 17 | 5.5 |
| Kernel join | 49 | 224 | 0 | 0.5 |
| Spectrum product | 104 | 277 | 4 | 0 |
| Four-word transform FIFO | 107 | 83 | 0 | 2 |
| Energy cache | 371 | 427 | 2 | 2.5 |
| Candidate scoring path | 1366 | 1198 | 4 | 2 |

Read-only provenance: `/tmp/starlink-idle-mailbox.N0l1fN/baseline-resource-audit-v1/`
`acquisition.rpt` and `transform_service.rpt`. Cross-hierarchy LUT combination
means these rows cannot simply be summed to establish a new net utilization.
In particular, the local prototype omits that four-word FIFO and adds modeled
boundary banks, but an inferred difference of BRAM capacities is not a measured
placement saving. The roughly 319 LUT difference between service and FFT shows
that this work primarily targets service timing/control, not a large standalone
FFT area reduction.

The same-clock mailbox copies could potentially be removed in a later bank
ownership redesign, but their checks, reset/status ordering and full observed
fault coverage would have to be retained and measured with the actual core.
That potential saving is not included in these results.

At 150 MHz this conservative slice needs at least 713 clocks removed from its
5182-clock interval to fit the 4470-clock deadline with any positive margin.
Eliminating only the roughly 512-clock post-commit forward copy is insufficient.
A deeper design could compute products into a private inverse bank during raw
forward output and transfer validated bank ownership locally after the same
status/fault fence. Feeding a committed outer ingress bank directly into the
core could also remove its extra 512-clock local copy. Those are concrete
targets for a second slice, but neither handoff is implemented or qualified
here, and neither may reset away a late fault or launch an unvalidated inverse.
