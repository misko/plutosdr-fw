# Checked-product actual FFT: final sampled-drain failure

The first checked-product actual campaign is **not accepted**. The root-owned
original process 30484 completed with exit 1 after 264.56 seconds; it did not
time out. All 84 prepared and 30 live source pins remained unchanged, and the
generated FFT wrapper matched the known factory product. No radio was touched.

Before execution, root independently replayed the reviewed 171-test preparation
and observer gate (original 23256, exit 0, 35.02 seconds). This included the
unchanged 93-test observer gate, not 171 additional runtime cases.

## Exact failure and independent diagnosis

The frozen result checker rejects `verify_cycles` with
`incomplete full trace/service profile or observer accounting`. Read-only
inspection of the original failing function's locals narrows this to one term:

- 624,233 contiguous trace rows exactly equal the observer's 624,233 samples.
- Epoch 1 has 32 forward admissions, but only 31 sampled real-drain completions.
  Its final admission at cycle 142157 remains pending.
- Epoch 2 has all six sampled completions.
- Observed nominal service times are 4553–4554 fast-clock cycles; stalled-input
  service times are 4826–4834. All measured intervals stay within the unchanged
  absolute 5215-cycle bound. The unobserved final lifetime is not counted.

The unchanged terminal checks pass. Separately executing the unchanged ownership
ledger checker also passes all 109,367 rows, including full private products,
publication, ACK and core tuples. This diagnostic does not bypass the failed
cycle check or turn the original run into a PASS.

At the final nominal boundary, output-bank readiness appears at cycle 146706
and result-busy clears at 146707. The controller traverses RESET0/RESET1 at
146709/146710. The first CSV row showing WAIT_BANK, cycle 146711, already has
running=0 and output-bank-ready=0: the bench has begun the next reset.
The existing `await_results` observes the settled state after a fast edge,
then lets the caller start reset before a live pre-edge WAIT_BANK row is kept.

The next change is an additive, bounded service-profile drain witness before
reset, preserving the original wait calls, raw stimulus, numerical comparisons,
fault checks, 32/6 completion requirement and 5215-cycle limit. It must observe
the actual live ready state and settle before allowing reset; neither accepting
31 completions nor interpreting reset as successful drain is allowed. Runtime
RTL and the original failed package remain unchanged. A new frozen run will be
required; the old failure is not retrospectively reclassified.

## Evidence locations

All directories below are under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/`:

- `checked-run-parent.pA6npmAc`: independent 171-test gate, snapshots and XML.
- `checked-product-actual-prepared-v1`: frozen source package and actual project.
- `checked-actual-parent.xtGiofa6`: original owner, command, tool logs, source/IP
  checks, rejected result and outcome.
- `checked-failure-parent.yKucfsxj`: root read-only diagnostic script, before
  hashes and original checker locals; independent ledger diagnostic.

Main trace SHA256:
`f2b630686631207f218d946f83bda8d9e4f992fa484cb0d9f8232fc0a0324130`.
Extra trace SHA256:
`cbe1fa4f61071325e170fa1e94625bd8c79642152c5ccacbaa50896c1efaa035`.
Ownership ledger SHA256:
`a4fd52a81bcfacd1af6fe1be697efc776920a6d691e536b8ad1706c922a70e57`.

Physical qualification and deployment remain false. The separate retained-output
candidate is undergoing its own actual campaign; neither approach has a new
timing-closing route. Latest retained routed WNS remains -4.068 ns.
