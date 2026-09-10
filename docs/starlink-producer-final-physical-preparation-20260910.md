# P1 physical preparation — offline only

The exact passed producer-final design is prepared for separately authorized OOC
synthesis. **No synthesis or route was launched for this preparation.** No RTL,
arithmetic, clock, constraint, synthesis/route strategy, or default changes.

Tested FW `3bdaaf06440f969520acaa8828b6c39bc60dc820`, HDL
`6923f5352951f8e03b9c29b6d4ef3c091a3cac90`.
Generator SHA256 `2b6174a783cb3f78cec9701dde6567d9302cf377074271db42891c392e323bc4`;
test SHA256 `a11ee4870a75b912cb1818f30f70d7049b2b37b6dbe5ac20c4bc816b0fb05f76`.
Original offline 43852 exited0: **33 PASS in64.21s**, no skips/failures; Ruff PASS.
Original freeze30861 exited0. All source bytes stayed fixed during testing.
Parent independently repeated the same sources: original10408 exited0,
33 PASS in63.32s. The subsequent separately authorized synthesis is not part of
this offline proof; original75133 launched at2026-09-10T15:22:18.723278+00:00
under `product-final-synthesis-v1` and receives its own terminal report.

## Frozen bundle

Directory:
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-physical-prepared-v1`

- 19-file inventory: `b3c446578c0c35f8e0f199aa12f66d8635b6f7d21c9b97713a5ffed2ac2b0f06`.
- Generated helper: `d22bda330f571774a3099d0da9615a6a445e58fb4aecf43d10e6657fc954e876`.
- Generated synthesis Tcl: `d46e1f2f1def64f6021c652b65b792ecfc554116b791ef99bec525380ea86406`.
- Unchanged synthesis owner: `d0f36ce2817ab20baaff8668b6743e367d296f7a60e714099fe69aa5b6912111`.
- Unchanged diagnostic route Tcl: `0873675fcec384f676a80b75b746460fbff2ecc3ee162f6111705ead2fad6d4a`.

This matches the root's independent offline smoke manifest byte-for-byte. Actual
input remains original50316, exact65-source inventory7adf2efa…, owner62e4fa75…,
R/D/S/C/K/M/P1111111/extras1/175/QUICK0. Full old/new receipt, four historical
CSV, source-before/after, zero-exit, unique terminal, and19 after-only IP checks
are performed before admission. The actual authoritative metadata is
`fence-preparation.json`; inherited `preparation.json` intentionally omits P and
is not substituted as the candidate configuration.

## Minimal source closure and preserved recipe

There are **eight RTL modules, still three banks**: additive producer-fence top,
input guard, result guard, canonical block mailbox (source/output banks), additive
product-fence mailbox, read-ahead joiner, read-ahead ROM, and unchanged spectrum
product. Canonical mailbox must remain present; replacing it with the additive
module would not elaborate the frozen source. The only top substitution is
`starlink_pss_fft_bank_owned_product_fence`. P=1 is explicit in admission,
generic assignment, exact single-entry readback, settings, and resource scope.

All eight files byte-match the passed actual freeze, including top8923b42b… and
product mailboxe4f4c56d…. No new bank, state, or cycle is introduced by listing the
eighth module. Source closure is12 files before the copied adapter: eight RTL,
original IP factory, coefficient memory, resource XDC, and thread setup.

The entire derived helper strictly restores the frozen ROM helper73553095…,
then the unchanged C1 and base helpers. Generated Tcl strictly restores the
prior ROM Tcl after only top-name, extra mailbox-list entry, P1 binding, and
corresponding receipts are inverted. Full eight-source inventory and original
actual receipt checks cannot be bypassed by refreshing local metadata hashes.

Part `xc7z010clg400-1`,100MHz source/175MHz island constraints, two threads,
IP factory, synthesis directives, route strategy, owner completion checks, and
all existing interface/CDC/IO caveats remain unchanged. No timing exceptions or
waivers are added. The owner preserves post-integrity audits on process failure
and requires actual synthesis completion/nonempty products/zero black boxes,
not merely a zero loader exit.

## Executed offline checks

33 tests cover full helper/Tcl/source inverses; explicit P1 missing/zero/duplicate/
conflicting/case/X/readback mutations; rejected source hashes and authoritative
metadata changes; both mailbox dependencies; copied-source closure; rejection of
the old ROM actual as a P1 result; empty owner status/wrong owner/missing or wrong
sampled-final receipt; no-overwrite and source/output symlinks. Full Tcl admission
executes only to a mocked `create_project` trap, including poisoned Python
environment while preserving parent values. No vendor tool is called by tests.

Archive:
`hdl/library/starlink_pss_acquisition/evidence/producer-final-physical-preparation-v1/`.
The actual result and older negative route remain independent immutable packs.
Actual sampled negative finals were0; no new simulation coverage is asserted by
this preparation. The separate fast fault witnesses and actual140 healthy seals
are the already reviewed evidence, not a complete formal reachability proof.

## Separately authorized one-shot synthesis command

```
env -u PYTHONHOME -u PYTHONPATH -u LD_LIBRARY_PATH TMPDIR=/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-physical-tmp-v1 /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-physical-prepared-v1/run_exact_control_synthesis.py --execute-synthesis --prepared /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-physical-prepared-v1 --expected b3c446578c0c35f8e0f199aa12f66d8635b6f7d21c9b97713a5ffed2ac2b0f06 --new-run /home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/product-final-synthesis-v1
```

The frozen owner itself sets the Vivado2022.2 SuSE LD path; Python children are
sanitized. TMPDIR is a writable non-/tmp directory; the proposed run directory
was absent before the approved launch. This preparation does not authorize route, any retry,
receiver integration, radio work, or promotion. The cut addresses only the
sampled product publication cone; the remaining full completion/result-fault
cones are deliberately unchanged and may still limit timing.
