# 60-upper cohort recipe frozen before numerical evaluation

Separate worktree `/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate60-paired`,
branch `codex/starlink-rx-only-do-not-merge-high-rate60-paired`, starts at
completed30 FW5bf4019a4bd151ee2769703a81c3112d63da4fc0 /
HDL529dc8e8d33afc237c7b26f8969ec32fa97cdbdd. The completed30 tree and
recordings are not modified. This stage is offline numerical preparation;
no RTL/profile/driver, actualFFT, physical work, radio or PPU action.

The two approved support sources are copied byte-for-byte from primary
198e935813eb4eb395aba938c8bcfa953eb83309, not independently changed:
support SHA fbd2b193f683b77a59c93d75fa2efa75856790ed7b76b20c0149436bac71ee68;
test SHA27009f25bce43929dbcf89b399bc5e98dbe1403787114c601caecffc6a7a8509.

The executable literal contract is tests/starlink_oracle/high_rate60_recipe.py.
It fixes PCG64 seed0x600052020260910, int64 draws[-400,400] inclusive,
shape16423x2 then CI16. Original raw range is
[34359735211,34359751634), yielding4096 canonical samples with768 preroll.
Both x2 stages round separately. Canonical center k requires raw[4k-21,4k+22).
Stage60-to30 outputs8205 values; stage30-to15 outputs4096.

At declared native center34359740384 replace exactly264 raw samples by
Q15 projected upper60 PSS, without additive noise inside that replacement.
Native capture [34359740256,34359740776) includes520 original raw samples.
Raw lags[-128,128] give257 tuples, qualified[-120,120] give241; known
winner0 and earliest-qualified tie rule are frozen, not selected afterward.
Asymmetric probes outside capture are fixed source offsets and IQ pairs:
0:(903,-311),42:(-817,209),127:(137,709),14023:(-619,-223),16422:(317,-911).
Request/generation/visit identities are60000520/60000001/60000052.

The coarse branch remains canonical66 taps,512FFT/447stride, seven complete
blocks/3584 words per stage/3129 scores. Use explicit18-bit Cmodel with no
global width mutation. Independently regenerate the existing conditioned60
kernel bytes, SHA7b006bac23a3c58f614728dbfdb17d28bd77defb3d6d0d24aaa76255669c0c67,
with conditioned coefficient energy1073765335. A30 kernel/denominator is
not admissible. Integer product, exponents, energies, normalization, packed
input words and indexes must all be retained.

Pilot512 outputs use the independent canonical /6 filter, raw step24 and
both upstream filter halos. Fixed acquisition mixers are-15MHz at60 then
-7.5MHz at30; fixed pilot mixer-2.8125MHz at15. Source CFO/applied correction/
residual CFO are all0; no tuning operation or coverage claim follows.

No continuation/source-tail or native service budget is frozen here.
Postcapture raw support10858 and67848 native tap-lag products are support/
operation counts, not a completion bound. Actual native60 service probe,
public profile admission and any later actual composition require separate
review. All old30 sources/goldens remain immutable. Numerical generation
will preserve source/import/environment closure and reject wrong kernel,
phase/halo, native264-vs-coarse66, packing and identity mutants.
