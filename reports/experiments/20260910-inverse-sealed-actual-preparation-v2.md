# Inverse sealed actual v2: source-specific preparation

This is preparation evidence, not an actual-run PASS. Original 21014 remains
an automation failure with a separately reviewed functional assessment; see
`20260910-inverse-sealed-actual-original21014.md`.

FW source `fb186470204f314681a37c7fe2962d024e876e04`, HDL unchanged
`b26f56dd32106c8e91290d075255ac4a6b9ff72d`. The independently repeated
111-test suite covers the bounded completed-epoch parser correction and all
65 original preparation policies.

Frozen v2 is under
`/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/inverse-actual-prepared-v2.g5UoQ9Ag/`:

- Bundle `inverse-sealed-actual-R1B1O1L1E1-175-prepared-v2`;
  manifest `39b1c731eb6f001983d5e842b1861d059c6f1f7a9ad986c26cde2a341ed74853`.
- Owner `own_inverse_sealed_actual_v2.py`;
  SHA `46ecfe1c67c7c480be86bb7b27c7e698a11c485f62fcefe3da90c8dbce27e59f`.
- Unchanged runner `23e9e9b989e35f013113bd6356288952bf05d58c57d7803c8baa1d74b8239972`.
- Offline verifier `verify_preparation_v2.py`;
  SHA `6f7b0fc4efdcffad0e4c18d57dc01b178ef3378b0342de3b975ceaacc4b8b652`.

All 64 names are identical to v1; the **only source delta** is
`inverse_sealed_actual_timing.py` to
`09061c6d56fab3460536cca74733f2da764ea6f2a2e508a11d4f4d60482f17c6`.
The manifest changes only that source hash. All 10 runtime modules, 21 compiled
sources, 8 numeric vectors, IP factory, flags, 100/175 MHz clocks, fault tests,
155/119-bit observers, diagnostic selection and absolute service budgets remain
unchanged. The new 46-test source is archived alongside, not added to the
unchanged runtime import closure.

The owner is the literal v1 owner with exactly four substitutions: parent
directory, prepared directory, owner directory and expected manifest. Its
process/environment/log/pre-post integrity/error handling is unchanged.
Offline inverse verification passed from `/`; three deliberately missing,
duplicate or out-of-scope owner modifications were rejected. No owner function
was executed during preparation. Parent independently repeated this gate.

The prelaunch archive contains 73 safe unique regular members, all hashes
verified: **218,653 bytes**, SHA
`a738e8ef3b0af72ee97cc50357318c1b61faae053486d8658329f217cf2c8063`.
Files: adjacent `20260910-inverse-sealed-actual-preparation-v2.{tgz,json}`.
The original archive is retained under recovery directory
`inverse-prepared-v2-archive.MKhGJqHP`.

After that freeze and independent review, parent separately authorized exactly
one actual evaluation. It launched at `2026-09-10T16:16:12.061356Z`, original
handle **77697**, using explicit venv Python `-B`, with `PYTHONOPTIMIZE`,
`PYTHONHOME`, `PYTHONPATH`, and outer `LD_LIBRARY_PATH` unset. The owner restores
the exact Vivado 2022.2 SuSE environment and exclusive local TMPDIR. Its actual
terminal outcome belongs in a separate report; it was pending when this
preparation report was written. No retry, synthesis, route or promotion is implied.
