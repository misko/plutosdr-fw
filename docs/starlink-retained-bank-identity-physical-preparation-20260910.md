# Bank-local identity physical recipe: UNBOUND, offline only

The additive recipe is prepared and tested, but cannot admit a real bundle:
`ACCEPTED_ACTUAL=None` and `UNBOUND_PENDING_ACCEPTED_BANK_IDENTITY_ACTUAL`
reject before copying or invoking the actual CLI. The successful offered-summary
actual run is explicitly rejected as authority for this different runtime.
No new physical bundle, vendor process, or mapped measurement was produced.

## Source and launch boundary

The new files are `tools/prepare_starlink_retained_bank_identity_synthesis.py`,
`tools/retained_bank_identity_synthesis/`, and
`tests/test_starlink_retained_bank_identity_synthesis.py`. Previous source,
actual evidence and the original 133-file physical preparation are untouched.

The copier, synthesis Tcl and admission policy have exact whole-source inverses
to the previous reviewed versions: respectively 8, 10 and 6 literal edit groups.
The three candidate RTL copies have the separately reviewed full inverses to
the two offered-summary modules and original local-admission guard. All 13
other runtime entries remain byte-identical. No RTL is edited by this recipe.

Three replacements from narrow's frozen HDL `7e8898af9`:

| File under `retained_output_bank_identity_candidate/` | SHA-256 |
|---|---|
| `starlink_pss_fft_bank_owned_retained_output_probe.v` | `42b6f902aef4235d1ddfae3e38135f73deab3fe06ff8b57f4ff32c9684792489` |
| `starlink_pss_fft_retained_output_impl.v` | `c41ecec9ae2f6072c6725ec452edd999120947647caaa6648f69d4c5a153d07b` |
| `starlink_pss_realtime_input_guard_local_admission.v` | `1197df519574ceceaa1b17b5b972bd3fc38a1caedd18ede492dd3ec1e056b005` |

Exactly 16 runtime modules remain selected. The recipe adds explicit
`BANK_LOCAL_IDENTITY_EQ=1` to the existing retained/R1/B1/O1/L1/private-offer/
closed-input/offered-summary settings. The RTL default remains zero. The source
contract adds no register or cycle; mapped LUT/FF/resource changes are unknown.

The 100/175 MHz XDC, two-thread Tcl, unchanged route Tcl, generated-FFT factory,
part xc7z010clg400-1, AreaOptimized_high, OOC and threshold 4 are preserved.
Their source pins remain explicit. The prior synthesis/route owners are retained
as immutable **references only**, not executable authority for this candidate.
Future owner path/manifest binding and actual physical launch remain root-owned.

## Required future actual authority

The future candidate CLI is
`tools/prepare_starlink_retained_bank_identity_actual.py`; the agreed terminal is
`RETAINED_BANK_IDENTITY_ACTUAL_VERIFIED_SEVEN_CONTEXTS_NO_CONTINUOUS_OR_PHYSICAL_CLAIM`.
After root accepts the new original actual run, a separately reviewed source
edit must bind its exact manifest, qualified and owner paths, owner/command/
terminal hashes, result hash, generated FFT bytes and frozen CLI hash.

The complete frozen CLI result must equal the original result JSON, including
all numerical and service fields. Original and copied source checks, original
process success, absence of timeout/interruption, unique automation terminal,
and source-matched 16-module closure remain mandatory. No CLI or environment
argument supplies an acceptance override. All positive test fixtures are
explicitly `MOCK_ONLY`, not substitutes for actual authority.

## Mapped inspection, not a source-factorization claim

The only added post-synthesis observation hook sources
`inspect_bank_identity.tcl` after the original synthesis and standard reports.
It makes read-only queries and writes exclusive diagnostic reports. It does not
change properties, constraints, optimization, routing, or vendor run counts.

Seven kept-name families are inspected: source/product preflight comparisons,
original selected-metadata preflight fallback, unchanged expected-product
comparison, source/product input-guard comparisons, and original selected-
metadata input-guard fallback. Each family has 24 three-bit-or-trailing-bit
leaves and four reduction groups: 196 expected kept nets in the spelling
fixture, not an expected mapped utilization count.

For observed nets, the report retains actual names, KEEP properties, drivers,
driver primitive types, sequential fan-in startpoints, combinational fan-in
cells and fan-out endpoints. Max/min paths through each nonempty family are
reported separately. Missing, duplicate or merged names are recorded and make
`all_expected_kept_names_observed=0`; they are not evidence a slow path vanished.
`factorization_verified=false` remains explicit even if every name survives.
The actual cones, phase-selection location, retained fallback cost, and complete
critical paths require independent inspection after authorized synthesis.

Baseline comparison is the offered-summary measurement: synthesis 2,248 LUT /
4,759 FF / 21 DSP / 15 RAMB18; route 2,344 LUT / 4,766 FF with WNS −2.504 ns.
The current release/epoch paths are not addressed by source-local comparison
factoring. CDC findings (5 critical, 139 warning, 3 info), unconstrained external
I/O (114 input/124 output) and board clock integration remain unqualified.

## Retained offline gate

Original process `84077` completed with **80 PASS in 1.53 seconds**. Evidence is
under `/home/mouse9911/gits/starlink-build-recovery-20260910.vHzUVnBz/retained-bank-physical-offline-v1.VO5ZAswZ`:
source-before tar, pytest log/XML, and all mock case outputs. A subsequent
`tar --compare` confirmed the tested source files remained unchanged.

The suite retains 60 adapted preparation-policy cases plus 20 new cases for
old-actual rejection, the three RTL inverses and 13 unchanged entries, admission
mutants, mandatory new parameter readback, complete copied policy/reference
closure, both banks/fallbacks/trailing leaves, missing/duplicate mapped names,
and observer nonoverwrite/read-only constraints. Tcl query tests replace vendor
intrinsics with explicitly synthetic fixtures; no mapped-device claim follows.

Repeat from this worktree with a new absent basetemp and retained log/XML:

```sh
env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH -u PYTHONOPTIMIZE \
  /home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -B -m pytest -q \
  tests/test_starlink_retained_bank_identity_synthesis.py \
  --basetemp /ABSENT/UNIQUE/cases --junitxml /ABSENT/UNIQUE/results.xml
```

No radio/PPU changes, actual FFT evaluation, synthesis, route, source union,
lower-clock claim, receiver deployment, or timing waiver is authorized here.
