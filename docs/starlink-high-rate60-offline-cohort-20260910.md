# Frozen60-upper common-source offline cohort

Final offline qualification:256 tests PASS in15.67s. Parent independently
repeated all256 tests PASS in16.94s and executed the frozen snapshot CLI's
complete69-file rederivation successfully. No runtime/profile/guard edits,
actualRTL/FFT simulation, service probe, source-tail budget, physical work,
radio, driver or deployment action is part of this result. Upper-only;
lower-edge admission is not implied.

Separate worktree `/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired`,
branch `codex/starlink-rx-only-do-not-merge-high-rate60-paired`, based on
completed30 FW5bf4019a4bd151ee2769703a81c3112d63da4fc0 /
HDL529dc8e8d33afc237c7b26f8969ec32fa97cdbdd. HDL remains unchanged. The
completed30 worktree and all its proof archives remain intact.

## Identities and pre-evaluation recipe

Final cohort: `build/high-rate60-offline-v2/cohort`.
Cohort receipt SHA256:
`6de2f3645459f8649d8fee127e479991fb1cc55b75001a37c763223e716b4dfa`.
76-source signature:
`c56f812b79f5bb8d5b60bc70af43ad0b5f1579e5af0e74dd8516fabeb2237c0a`.

The literal recipe file SHA remains
`bd39c5fdf850dc6ec1ecbbf6476ac6a8e2990ce1be7455e98a0fc5294647f4c4`,
declared to parent before any numerical generation. The approved support
helper/test are byte-exact copies from primary198e935813eb4eb395aba938c8bcfa953eb83309;
their hashes are recorded and enforced, not independently altered here.

PCG64 seed0x600052020260910 uses explicit int64 draws[-400,400] inclusive,
then CI16. Exact264-tap upper60 projected Q15 PSS replaces the raw samples
at center34359740384; there is no added noise inside that replacement.
The five asymmetric identity probes, center, seed, packet identities,
winner0, kernel/Eh and zero-CFO contract were frozen before evaluation.
No measured later result selected those values. Details are retained in
the pre-evaluation recipe document and executable recipe source.

## Complete numerical evidence

| Consumer/stage | Count and support |
| --- | --- |
| Original raw CI16 | 16423, [34359735211,34359751634) |
| Integer60→30 stage | 8205 outputs, first index17179867609 |
| Integer30→15 stage | 4096 outputs, first index8589933808 |
| Preroll | 768 canonical outputs /3111 raw support samples |
| Native capture | 520 original raw, [34359740256,34359740776) |
| Native coefficients | 264, original60 projected PSS; Eh1073758594 |
| Native raw / qualified tuples | 257 lags[-128,128] /241 lags[-120,120] |
| Native packet | all26 words, IDs60000520/60000001/60000052 |
| Coarse overlap jobs | seven512-word blocks, stride447;3584 words/stage |
| Coarse scores | 3129, indexes[8589934576,8589937705) |
| All coarse block raw support | [34359738283,34359751098) |
| Two complete coarse block support | [34359738283,34359742158) |
| Pilot selected / full offline / unsupported prefix | 512 /683 /90 |
| Selected pilot raw support | [34359735227,34359749686), step24 raw |

The x2 stages each have their own signed17 quadrant mix, Q15 FIR,
nearest-even conversion and CI16 saturation. Both output stages, their
mixed words, sums and absolute indexes are retained. Canonical sample k
has original raw support[4k-21,4k+22). The test deliberately keeps the
first stage unrounded and demonstrates that a single flattened rounding
differs, so the cascade cannot silently collapse to one linear filter.
All conditioner and pilot stage saturation counts are0 in this fixture.

The explicit18-bit vendor C model leaves global24-bit defaults unchanged.
The independently derived conditioned60 kernel byte-matches the existing
512-word file SHA7b006bac23a3c58f614728dbfdb17d28bd77defb3d6d0d24aaa76255669c0c67,
with canonical integer hash497ab1527fefaf2e0c2ed0ad7260c1fc01bec6b9062a1857b66bd7ec45bedccb.
Coarse energy is explicitly1073765335; the30 value1073744004 is rejected.
Forward BFP exponents[1,2,0,1,0,1,1], inverse[1,4,2,1,2,1,1]. There is
no FFT/product overflow or u69 normalization saturation. The synthetic
projected-control score is255; this is not a detection-threshold claim.

Every512-word forward/product/inverse block, BFP exponent, original
CI16→signed18/zero-padded24-bit input word, input/score index,66-tap energy,
u69 numerator/denominator, saturation flag and score is retained. Tests
independently recompute all3584 stage words using vectorized exact product
rounding around separate C-model calls, and independently sum both
343x2/447x2 maps. No original15/30 golden is replaced.

Native sums use Python integers and signed48 per-tap saturation, checked
against the unchanged generic fixed-correlator contract and a separate
vectorized direct-sum test. Every257 raw tuple is preserved, not only the
winner. Qualified legality requires264 taps, C signed39, positive Ex
unsigned38, positive Eh unsigned31 and no saturation. Winner0 has
real=Ex=Eh=1073758594, imag0 and power1152957518188856836. Exact normalized
power is1 for the declared template replacement. Strict cross-product
comparison retains the earliest qualified lag on ties. All26 packet words
are independently assembled and checked, including zero and high words.

Pilot calculations independently mix/filter the common canonical source
and cross-check the existing streaming integer oracle. All outputs and
support-valid flags are preserved, plus each selected output's original
raw support endpoints.512 outputs are2048 bytes;2.5MS/s CI16 remains10MB/s.
The fixture does not predict hardware auto-stop/drain or CDC startup counts.

## Source closure, tests and retained attempts

The76-source closure includes17 recursively recorded local Python modules,
approved support/test, recipe, all unchanged coarse/native runtime bodies,
public wrappers, pilot ABI/coefficients and conditioned60 kernel metadata.
Only parameter-independent serializers, rounding, environment fingerprint
and Model18 helpers are reused from earlier work; no30 globals/functions
with hardcoded geometry or energy are monkeypatched. Source snapshot,
recipe, source-before, source-after and environment-before receipts are
verified against rederivation. Interpreter, NumPy RECORD/numeric extension
hashes, vendor C-model archive and extracted library hashes are recorded;
third-party binaries are not duplicated in the portable package.

First cohort v1 remains retained:250PASS17.28s, CLI generation/rederive
PASS. Test-only additions created v2 with the final source closure; all69
numeric files are byte-identical between v1 and v2. No numerical failure
or moved acceptance bound occurred. Lint-only import cleanup preceded the
first numerical evaluation. The frozen recipe did not change.

Exact final scope (use a new basetemp for an independent repeat):

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest \
 tests/test_starlink_high_rate60_paired.py \
 tests/test_starlink_high_rate60_support.py \
 tests/test_starlink_high_rate_paired.py \
 --basetemp=build/high-rate60-offline-v2/pytest-tmp \
 --junitxml=build/high-rate60-offline-v2/junit.xml -q
```

The standalone replay uses
`build/high-rate60-offline-v2/cohort/source_snapshot/tools/generate_starlink_high_rate60_paired.py`
with `build/high-rate60-offline-v2/cohort --verify`. Mutations cover every
top-level recipe/support field, wrong30 energy/kernel, raw halo/phase,
single-round cascade, component packing, native66/132 substitutions,
missing/mutated numeric files, source/import closure and pre/post receipts.
All old30 paired tests remain unchanged and pass in this combined suite.
Raw pytest attempts remain in place; portable proof avoids duplicating
their many intentionally corrupted fixture copies.

No native60 service cost or continuation is qualified.10858 raw samples
after capture and67848 tap-lag products are support/operation counts, not a
completion bound. A later actual native60 service probe must use a true
60MS/s source clock, declare command eligibility and budget before any
measurement, and independently qualify lifecycle/readout. Current public
bank+STOP60 admission remains absent; numerical success does not bypass
those guards or supply an AXI/driver/physical/RF deployment.
