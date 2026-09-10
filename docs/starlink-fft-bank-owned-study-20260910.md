# Three-bank FFT island — actual-core slice, receiver integration still open

The second bounded slice eliminates the stored forward FFT result and its
post-commit 512-word copy. Checked forward results feed the unchanged kernel
join and spectrum product directly into a private inverse-input bank. A separate
source bank can capture N+1 after the core has consumed N. One generated FFT
still performs both transforms. The final inverse output bank still waits for
the actual 100 MHz last-read ACK before the core/checker reset and next job.

All three banks exist in RTL: source 100 MHz -> fast, private products fast ->
fast, inverse results fast -> 100 MHz. Each is 512x36 bits plus the existing
70/75-bit descriptors and checked ownership machinery. There are no modeled
extra ingress or egress banks in this result. This is a changed dataflow and
ownership schedule, not a deeper version of the original queue.

Actual generated-core tests pass at 150, 175 and 200 MHz. The 150 MHz nominal
margin is only 60 clocks and the tested repeated-stall profile exceeds its
deadline. The 175 MHz slice has useful measured service margin under that
profile, but its achievable physical clock and complete receiver are unqualified.

## Measured service budget

Each clock run uses 32 back-to-back nominal blocks and six consecutive blocks
with repeated stalls. The latter inserts three slow ingress clocks every 13
words and blocks four of every 17 slow output clocks. These are independent
frozen numerical blocks with consecutive metadata, not a continuous canonical
overlap scheduler/source stream. The three frozen fixtures repeat; this does
not assert source-sample continuity across that repetition.

| Actual simulation fast clock | Maximum nominal forward-admission interval | Nominal slack against 29.8 us | Maximum repeated-stall interval | Stalled slack |
| --- | ---: | ---: | ---: | ---: |
| 150 MHz | 4410 clocks / 29.400 us | 60 clocks / 0.400 us | 4650 / 31.000 us | -1.200 us |
| 175 MHz | 4540 / 25.943 us | 675 / 3.857 us | 4820 / 27.543 us | 2.257 us |
| 200 MHz | 4668 / 23.340 us | 1292 / 6.460 us | 4986 / 24.930 us | 4.870 us |

These observed maxima are not universal bounds on vendor latency, sink stalls
or clock-domain crossings. The simulator uses femtosecond resolution for the
fractional 150/175 MHz clocks; the table converts the counted fast clocks using
the nominal frequency. No physical timing accuracy is inferred from this.

Every nominal transform still has admission-to-config = 2 clocks, input
transfer span = 513 clocks for 512 accepted inputs, last-input-to-first-output
= 781 clocks, and admission-to-checked-commit = 1809 clocks. There is no
one-sample-per-clock compute assumption or replacement numerical FFT model.

Forward admission to inverse admission is now 1822 clocks. The sequence after
forward guard commit is four clocks to final product-bank write/commit, then
the actual local mailbox ownership/prefetch and guard retirement/reset/config
lifecycle. The portable JSON records each actual ownership and ACK timestamp.
The previous serial slice took 2334 clocks between these admissions, so this
cut removes exactly 512 clocks from the measured forward loop.

The full interval includes the final 100 MHz bank drain and its actual ACK.
At 150 MHz, 2x1809 transform clocks plus 512 slow drain clocks (768 fast
clocks) already use 4386 clocks; the measured total is 4410, just 24 clocks
more for the remaining handoffs. The old conservative slice's 5182-clock
schedule included serialized next-input loading. Removing that serialization
as well as the forward copy yields 772 clocks of improvement at 150 MHz,
even while charging the actual slower final drain here. Initial source-bank
fill is real 512-cycle 100 MHz work; it overlaps steady-state processing only
when its actual previous-reader ACK permits it. Capture start/commit and
output start/final-read times are retained per block, rather than omitted.

## Ownership and fault contract

Input bank ownership lasts until all 512 actual core deliveries are checked
and the real reader ACK crosses back to the source writer. The bench compares
every delivered source/product word with its frozen reference and forbids a
write while an earlier loaded source bank remains unconsumed. It also witnesses
prefetched N+1 while N's input is complete and RUN_JOB remains asserted: the
core input valid, delivery certificate and source read-ready must all stay low.

Forward nonfinal results may compute into private product storage before the
independent FFT status arrives. The final forward result reaches the multiplier
only on its original fully qualified guard retirement. Inverse scheduling
requires both this guard commit and the actual complete product bank, with
matching source identity, forward exponent, position zero and nonfinal TLAST.
That observed ownership transfer acknowledges the forward result consumer;
it does not free the product RAM. Its own mailbox remains immutable until all
512 inverse core input reads and its actual ACK. No fabricated data-read ACK
is supplied to either source or product bank.

The original input certificates and final cause fence remain. Current vendor,
framing, overflow, metadata and reservation faults veto commit/handoff, and
the forward core/checker epoch remains alive through the ownership transfer.
Faults immediately after forward commit and on the handoff edge quarantine
without resetting away the fault or admitting inverse work. This shorter
handoff uses the existing certified-cause argument, not a newly guessed bound
on vendor event delay.

Guard retirement and kernel-join acceptance are explicitly identical. A held
final return cannot enter the joiner while product-bank readiness is absent.
The legal-stall witness withholds forward status until the first 511 products
drain, withdraws product-bank readiness while the real joiner is empty/ready,
then supplies the one delayed status. The qualified final remains held for
three observed clocks and recovers exactly when readiness returns. A separate
actual-core mutation run removing only this input-valid gate fails the
acceptance equality assertion on that witness.

Inverse output retains private-before-publish validation and the real final
slow read ACK. A late fault after 128 words have already been accepted permits
the measured sticky-fault crossing to close the slow interface. At all three
frequencies the final provisional prefix is 130 exact words, zero completed
blocks, and one queued N+1 source block with no new admission. The previously
accepted prefix is not retroactively retracted; downstream epoch/visit fault
evidence must keep it provisional. Reset of either domain purges all banks,
arithmetic and ownership. Source gaps/flush must be translated into the common
pipeline epoch reset by the surrounding acquisition composition.

## Executed tests and resource measurement

Each v3 clock run ends with 44 healthy complete blocks, 22,658 exact inverse
words (22,528 complete-result words plus the 130-word provisional prefix),
24,064 checked forward words, 24,064 checked product words, four purge cases
and ten fault cases. There are 37 observed overlapping source loads, nonfinal
readiness-loss witnesses, three legal held-final witnesses, and thousands of
closed-input/prefetched-N+1 witness cycles.

The fault probes cover late forward commit/handoff faults, product overflow,
product ordinal/metadata corruption, missing active core input, lost nonfinal
product-bank readiness, inverse final-commit veto, postcommit fault before any
slow output acceptance, and postcommit fault after accepted output. Reset
probes cover partial source fill, active forward input, active inverse input
and inverse ACK wait, using independent reset sides and exact recovery blocks.
A status-absent inverse-candidate probe cannot bypass forward qualification.

The combined evidence/parser tests pass (19 tests), and Ruff/diff checks pass.
The first 200 MHz v1 run is retained as failed bench evidence: it wrongly
rejected the deliberately healthy inverse commit preceding an ACK fault.
The corrected bench uses a narrowly scoped permission for that pre-fault
commit; all commit certificates and the same-edge veto remain checked.

Synthesis uses the exact v3-tested RTL copied and hashed before measurement,
the actual generated FFT, and explicit two-thread hooks in both synthesis
processes. No black boxes remain. It performs no placement or route:

| Three-bank slice, synthesized | Total LUTs | FF | DSP48 | BRAM tiles |
| --- | ---: | ---: | ---: | ---: |
| Entire slice including FFT, product, kernel and all three banks | 1834 | 4375 | 21 | 7.5 |
| FFT child within that slice | 1205 | 2989 | 17 | 5.5 |

All 15 RAMB18 instances are counted: eleven in the FFT, one in the coefficient
ROM and one in each of the three banks. No RAMB36 remains. The standalone
resource-probe top defines 100/175 MHz clocks, while the generated IP's own
original OOC synthesis clock is unchanged. This is not an achieved 175 MHz
result. External timing/CDC constraints are incomplete for qualification;
diagnostic reports make no CDC or full receiver pass claim. These standalone
synthesis counts cannot be subtracted directly from earlier placed receiver
hierarchy counts to claim net receiver savings.

## Reproduction and integration boundary

Sources and runners are additive under `hdl/library/starlink_pss_acquisition/`:
`starlink_pss_fft_bank_owned_slice.v`, `simulate_fft_bank_owned_slice.tcl`,
`synthesize_fft_bank_owned_slice.tcl`, the resource-probe XDC and thread hook,
and `tb/tb_starlink_pss_fft_bank_owned_slice.sv`. No receiver default selects them.

Successful immutable evidence directories under that library's `build/` are
`fft-bank-owned-{150,175,200}-v3`, `fft-bank-owned-mutant-v2`, and
`fft-bank-owned-synthesis-v2`. Each has frozen sources and generated artifacts;
the simulations retain full logs and per-fast-clock traces. The portable
`reports/starlink-fft-bank-owned-study-20260910.json` contains frozen source and
vector hashes, log/trace hashes, 38 complete bank-lifecycle records per clock,
all terminal/fault receipts, mutation rejection and full synthesis inventories.

```sh
vivado -mode batch -source hdl/library/starlink_pss_acquisition/simulate_fft_bank_owned_slice.tcl \
  -tclargs NEW_OUTPUT FROZEN_VECTORS 175
vivado -mode batch -source hdl/library/starlink_pss_acquisition/simulate_fft_bank_owned_slice.tcl \
  -tclargs NEW_MUTATION_OUTPUT FROZEN_VECTORS 200 join-gate-removed
vivado -mode batch -source hdl/library/starlink_pss_acquisition/synthesize_fft_bank_owned_slice.tcl \
  -tclargs NEW_SYNTHESIS_OUTPUT PASSED_SIMULATION_DIRECTORY
```

Use `/opt/Xilinx/Vivado/2022.2/bin/vivado` with the environment library path
`/opt/Xilinx/Vivado/2022.2/lib/lnx64.o/SuSE`. The evidence scripts reject reuse
of an output directory. The Python report command is
`python -m tests.starlink_oracle.fft_bank_owned_evidence OUTPUT_JSON EVIDENCE_150
EVIDENCE_175 EVIDENCE_200 MUTATION --synthesis SYNTHESIS`.

Next composition must preserve the original overlap scheduler, energy cache,
447-result qualification, normalization and scoring at 100 MHz. Input words
retain `{Q16, 2'b00, I16, 2'b00}`. Output metadata is
`{inverse=1, source_start[63:0], forward_exponent[4:0], inverse_exponent[4:0]}`;
the old 100 MHz inverse-input exponent observer cannot simply watch a removed
interface. Independent exponent/identity checks must use the actual new bank
handoff and stable output descriptor. Numeric forward/product probes must
sample the fast clock, not invent 100 MHz observations of fast transfers.

Continuous canonical 15 MS/s overlap, energy retention/scoring under bounded
stalls, source-gap/index quarantine, lower-edge coefficients, native source
15/30/60 front ends, both detectors, 2.5 MS/s pilot IIO, physical receiver
timing/CDC, .18 then Ethernet .17 qualification, and eight targets / 120 ms /
300 s remain required. This isolated exact-block study completes none of those
larger integration or RF gates, and sample spacing is not timing accuracy.
