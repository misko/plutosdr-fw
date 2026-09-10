# Bank coarse + native fine + pilot: bounded digital smoke

Status: the explicit native-anchor **520** profile passes one actual-core run
at 175 MHz and one at 200 MHz. This is concurrent arithmetic/ownership evidence,
not causal acquisition, injected-PSS timing lock, 750 Hz accuracy, physical
timing, ADC/DMA/IIO receipt or RF qualification. No product RTL, receiver
default, packaged AXI capability, board design, radio or PPU state changed.

The independent FW/HDL worktrees start at FW
`9c6bee20cf9d970067bb5f8c8fc336ab85e3590d` / HDL
`9759cf121e899975e841b17c593289cf646249fa`, on
`codex/starlink-rx-only-do-not-merge-bank-native-paired`.

## What actually ran

One original signed-CI16/index source feeds both the real acquisition-shell CDC
and the public native tracker input. `sample_clk` is genuinely 15 MHz, with
one valid sample on every enabled edge, distinct from 100 MHz AXI/coarse and
175/200 MHz FFT clocks. An idle strobe on an enabled native sample-clock edge
is a gap, not an ordinary pacing bubble. The explicit pre-roll configuration
pause is before native admission; no native-owned window contains a pause.

The additive bench mechanically adapts, but does not modify, the existing
paired PSMA/PIL1 bench. The real native AXI wrapper uses injection=0,
DSP reducer=1 and timestamp=index. All coefficient loads, command submission,
26-word result reads/re-reads, release and telemetry reads use public AXI.
Separate bench AXI agents are not a measured CPU/interconnect scheduling path.
Hierarchical probes only observe actual admission, capture, ownership and
health; they never drive product state.

The exact existing 4,096-word source, 768-sample pre-roll, original 1,406-word
numerical segment, coarse kernel, seven numerical vectors and independent pilot
expectations are unchanged. Each successful run checks 894 ordered exact
scores, 447 exact two-frame map words, 512 exact pilot words/2,048 little-endian
bytes, pilot support/index/snapshot accounting, coarse boundary-stop ownership,
and continued pilot delivery after coarse stop. Forward/product/inverse
intermediate words are preserved as input goldens, but this paired bench adds
no new intermediate-word numerical comparison claim beyond its exact scores.

| Measured actual-core run | 175 MHz | 200 MHz |
|---|---:|---:|
| Capture overlapping FFT RUN_JOB, fast clocks | 319 | 366 |
| Native compute + coarse-active + pilot-DDC accepted canonical beats | 842 | 842 |
| Actual source-domain command lead before capture START | 461 | 461 |
| Exact native raw capture words | 130 | 130 |
| Complete native packets / public words read | 1 / 52 | 1 / 52 |
| Native packet retained across coarse stop | yes | yes |
| First actual forward-FFT input, ns | 123615.592 | 123608.800 |
| Capture first / last accepted beat, ns | 116835.433 / 125435.433 | 116835.433 / 125435.433 |
| Terminal simulation time, ns | 311240 | 311240 |

The 842 count is sampled at the 100 MHz owning edge and requires native
correlator busy, coarse pipeline active, pilot enabled and a pilot-DDC input
acceptance. It is not a count of 2.5 MS/s output words or proof of all detector
stages simultaneously computing. Capture overlap is observed at `fft_clk`.
These short, fixed-phase executions are not guaranteed worst-case latency,
sustained native-window capacity or achieved physical clocks.

Both benches finish with the inherited deliberate invalid map release after
healthy drain: joint coarse health becomes failed, historical coordinates and
already captured pilot bytes remain, and the coarse FFT stays quiescent. This
is not the broader concurrent native gap/reset/fault suite, which remains next.

## Exact native profile and failed earlier anchor

`FIRST = 2^33 - 16 = 8589934576`. The successful explicit profile uses
center `FIRST+520 = 8589935096`, request `0x15005200`, coefficient generation
`0x15000001`, and raw support `[8589935064,8589935194)` (130 original samples).
It lies entirely within the selected map's full FFT-input support
`[FIRST,FIRST+959)` and the unchanged pilot support envelope.

The zero-CFO upper-edge 15 MS/s Q15 template is derived independently. Every
qualified lag −30 through +30 is checked for positive Ex/Eh, no signed48
per-tap saturation and the actual DSP reducer's signed39 correlation,
unsigned38 Ex and unsigned31 Eh bounds. Ranking uses exact cross-products,
excludes constant Eh, and keeps the earliest lag on ties. The files use native
`iiiiqqqq`; AXI coefficient data is explicitly swapped to low-I/high-Q. Tests
reject a missing swap, wrong profile, illegal nonwinning tuple and all changed
packet/identity fields.

Independent Python-integer/Fraction review agrees with the complete 26-word
golden: winner lag −17, Re=144077802, Im=−27795799, Ex=204670264,
Eh=1073742825, power=21531019471199605. Its normalized score is approximately
0.0979737. This is **not** the injected PSS start at offset 447 and not timing
lock; the winner begins at offset 503. The command is prearranged and issued
before any causal coarse result. Actual admission occurred at `FIRST+26`;
the enforced source deadline is `FIRST+128`. Even that deadline leaves 359
samples before capture start, above the unchanged minimum lead of 64.

The default anchor 447 remains available with the same strict overlap gate;
it is intentionally a preserved negative result, not a passing default smoke.
The retained attempts are:

1. `bank-native-paired-175-healthy-v1`: runner startup failure before source
   allocation/IP/simulation; Vivado's bundled Python 3.8 lacked `numpy.typing`.
   The runner now requires an explicit absolute Python executable and clears
   Vivado's Python/loader environment for the independent oracle subprocess.
2. `bank-native-paired-175-healthy-v2`: exact native packet/map/pilot comparisons
   reached, but the strict final overlap/inventory gate failed. No PASS claim.
3. `bank-native-paired-175-healthy-v3`: diagnostic-only replay, unchanged anchor
   and gates, confirmed the sole failed term was capture/FFT overlap=0.
   Done=1, admissions=1, raw=130, public reads=52, retained stop=1 and compute
   overlap=842. Capture ended at 120568.766 ns; first FFT input was
   123615.592 ns, with source index `FIRST+590`. The real 512-word 100 MHz bank
   fill was omitted from the initial overlap prediction. The capture ended
   3.046826 µs too early; the gate was not relaxed.

The reviewed 520 profile shifts the native aperture by 73 samples (4.866667 µs)
without changing any raw source, coarse or pilot expectation. Exactly one new
175 MHz and one new 200 MHz execution then passed. The failed runs were not
overwritten or relabeled.

## Evidence and provenance

- [Exact results and all 86 original frozen-file hashes](../reports/experiments/20260910-bank-native-paired-results.json).
- [Portable original source/log/vector/generated-wrapper archive](../reports/experiments/20260910-bank-native-paired-frozen-study.tgz), SHA-256
  `4b61cb46b208c86886510b9d66c931d0ad3b3967058161eb85a8f729d2a8a0b8`.
- [Additive Python dependency audit](../reports/experiments/20260910-bank-native-paired-python-postrun-audit.json).
- [Final policy/regression JUnit](../reports/experiments/20260910-bank-native-paired-policy-v2.xml):
  180 PASS, 23 deselected; 59 are the new native oracle/runner policies.
  Ruff passes. The earlier 179/24 filtered receipt is retained separately.

The 86 frozen files and generated FFT wrapper are byte-identical between the
two successful clocks. Each original runner verifies exact ordered packet
rows, required terminal markers, actual pilot byte equality, no unexpected
FAIL/FAULT/Fatal/ERROR even after an apparent PASS, and equality of the complete
pre-run frozen filename/hash inventory after simulation. All attempts and
their original manifests remain unchanged in the archive. Vivado 2022.2 and
its installed generated-FFT simulation libraries are still required; the
archive is source/evidence, not a redistribution of the Vivado installation.

There is an explicit original-run provenance limitation: `python -m
tests.starlink_oracle.bank_native_paired` imports package initializers and
transitive modules. The original runs froze the four direct math modules but
not six additional project-local imports. The separate **post-run** audit
records all ten modules, SHA-256 and tracked git blob identities (the nine
pre-existing files match the pinned FW HEAD), Python 3.11.16 and NumPy 2.4.6.
This does not retroactively make those six files pre-run frozen inputs.

A subsequent future-runner-only revision now freezes the deterministic ten-
module closure with noncolliding encoded paths and checks its list against a
fresh import closure in policy tests. This revision has policy tests, **not a
new actual-core replay**. Neither the numerical oracle nor bench/product RTL
changed for that packaging fix. Current helper/runner provenance must not be
silently attributed to the earlier successful run snapshots.

## Reproduction entry points and remaining gates

New files are `tests/starlink_oracle/bank_native_paired.py`,
`tests/test_starlink_bank_native_paired.py`, and HDL acquisition files
`prepare_bank_native_paired.tcl`, `simulate_bank_native_paired.tcl`,
`tb/bank_native_paired_checks.svh`. No existing bench/product file was edited.
Generate absent-only native vectors with the Python module's explicit
`--anchor 520`; use `--verify --anchor 520` before running. The Tcl entry takes
`NEW_OUTPUT ORIGINAL_SCORE_VECTORS ORIGINAL_PILOT_ORACLE NATIVE_ORACLE
175|200 520`, and requires `STARLINK_NATIVE_PYTHON` to name an absolute compatible
interpreter. All paths are normalized before changing cwd. Original source
authorities and commands are recorded in each archived outer transcript.

Remaining separately reviewed gates include combined negative epochs,
native-owned source gaps/index/timestamp discontinuities, pending/active/result
reset, coefficient cohort changes, expired/late/overlapping commands, and true
PSS capture concurrently with coarse processing. The current native scheduler
only captures future windows: its minimum lead is measured at actual
sample-domain admission, not inferred from a stale Gray-index read. Native
capture/result banks have ownership/overrun rules, not a continuous raw-history
cache that can retrospectively recover a just-detected coarse PSS. Causal
coarse-to-fine scheduling therefore still needs an explicitly future prediction
and its missed/expired-window rejection contract.

30/60 MS/s remain genuine integration work. The public acquisition wrapper
currently rejects realtime and boundary-stop modes outside 15 MS/s; those
guards cannot be bypassed by bench `defparam`. High-rate coarse needs its
distinct conditioned kernels/energies (30:1073744004; 60:1073765335), not the
15-rate kernel (1073742825). Independent x2/x4 DDC references map canonical k
to raw center 2k/4k and newest 2k+7/4k+21. A pilot output with newest canonical n
has original-source support `[R*(n-538)-delay, R*n+delay+1)`, with
R=1/2/4 and delay=0/7/21. Native remains at the original rate with 66/132/264
taps and 61/121/241 qualified lags. Existing high-rate short raw fixtures alone
do not contain 512 fully supported pilot outputs; a separately reviewed common
raw source/support fixture and public-shell/profile design are required.

The full goal is unchanged: continuous canonical15 coarse from source15/30/60,
original-source sparse fine, independent 2.5 MS/s pilot IIO inspection,
.18 before Ethernet .17, then eight targets, 120 ms valid dwells and a 300 s
source timeline. This sub-millisecond digital smoke satisfies none of the
deployment, physical, RF, accuracy or long-duration completion gates by itself.
