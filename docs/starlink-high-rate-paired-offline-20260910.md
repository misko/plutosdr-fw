# 30 MS/s upper-edge common-source offline cohort

Status: **OFFLINE PASS, not RTL/profile/receiver qualification.** One independently
derived original-raw cohort supplies native132-tap tracking, canonical15 MS/s
conditioned coarse arithmetic, and2.5 MS/s pilot filtering. No RTL, public rate
guard, ABI, build profile, BD, radio, PPU or existing golden was changed. No
actual-IP simulation, synthesis, route, receiver build or push was performed.

Worktree: `/tmp/starlink-coarse-alternatives.Y3JzOI/high-rate-paired`, branch
`codex/starlink-rx-only-do-not-merge-high-rate-paired`. Starting FW
`e2f957b0a1f03c04ea594097ee88ff0d90351536`, unchanged HDL
`b49553c16319f59ad8d7b44fd24c494f96eba142`. The completed production-map
worktree/evidence was neither edited nor rerun.

## Frozen inputs and executable gate

The additive `tests/starlink_oracle/high_rate_paired.py` declares `CONTRACT`
before numerical evaluation: only30-upper, raw8205/canonical4096, canonical
pre-roll768, native132/capture260/qualified121, zero CFO and native winner0.
The fixed acquisition mixer is -7.5 MHz; the subsequent fixed canonical pilot
mixer is -2.8125 MHz. These are frequency translations, not an applied residual
CFO correction. Synthetic source CFO, separate correction and remaining CFO
are all0. No RF tuning operation is claimed.

The raw source uses explicitly seeded NumPy PCG64 integer noise in[-400,400],
asymmetric nonperiodic identity probes and an exact replacement of132 samples
by the projected30 MS/s upper PSS. Noise is outside that replacement; this is
not a noisy-detection sensitivity test. The PSS starts at canonical520/raw1040
relative to the coarse epoch, raw-array offset2583. No FPGA/RTL observation
supplies expected values.

`tools/generate_starlink_high_rate_paired.py` is absent-only. Its `--verify`
path recomputes the entire cohort and compares every file, full metadata and
source snapshots. Merely changing a payload and its receipt SHA does not pass.
No15 MS/s source/template/score golden is consumed. The production-map helper
is reused only for its explicit18-bit C-model owner and width-independent
integer/packing helpers, not its15 MS/s template, energy, block oracle or
periodic fixture. Existing C-model width globals remain24/23.

Final directory: `build/high-rate-offline-v5/cohort`.

- `cohort.json` SHA256: `ba3046d56a6eb1cf2792070cf63f8d7ffb44958f0ef9f4999907b2b2a49bdb4d`.
- Source-set signature: `dd6989f9c6b43fd9695e581692c193898bc109f423c80d88dc1a8c5a63aa2136`, defined as SHA256 of `jq -cS '.source_sha256' cohort.json` including its newline.
- 51 derived files and71 byte-copied source/dependency snapshots, with complete hashes in the receipt. The snapshot includes the imported package initializer and the unchanged complete coarse/native Verilog runtime; those Verilog sources were not executed.
- Python executable, NumPy version/distribution RECORD and eight numeric module hashes are frozen. The installed FFT C-model archive and two extracted-library hashes are frozen; proprietary model binaries are not included in the portable archive.

The frozen30 coarse kernel is independently transformed from the conditioned
Q15 template and byte-matched, not copied as the expected transform:

| Identity | Frozen value |
|---|---|
| Kernel text SHA256 | `23996c80f79f112ea7739049050ad8cb2c85a8067792889bf2a774886ac2ce24` |
| Kernel little-endian int32 complex SHA256 | `926a6477ded55f163a888945ec35ccf4fa55614beea62339fc19f266721d6b8f` |
| Conditioned coarse Eh |1073744004 |
| Native132-tap Eh |1073746351 |
| FFT C-model archive SHA256 | `0f264e0e15f93fcf5df9c60e715fe51c9bcd9639b578a5ae67be4df5cf2d5f87` |

The native and conditioned template identities are explicitly distinct in the
receipt. Neither uses a native66-tap legality shortcut.

## Exact support and numerical results

All intervals below are half-open unless explicitly called inclusive. Let
`K=8589934576`, `P=K-768=8589933808`. For canonical index`k`, raw center is`2k`
and its inclusive FIR support is`[2k-7,2k+7]`. Thus N consecutive canonical
samples require`2*(N-1)+15` phase-aligned raw samples.

| Inventory | Result |
|---|---|
| Complete raw payload |8205, indexes[17179867609,17179875814) |
| Complete canonical payload |4096, indexes[8589933808,8589937904) |
| Canonical768 pre-roll |1549 raw samples including first FIR halo |
| Complete coarse blocks |7; each512 input, forward, product and inverse words |
| Per-stage/input word inventory |3584; explicit source indexes, positions and zero-padded AXI48 input packing |
| Exact scores/energy/numerator/denominator records |3129 |
| Full7-block canonical FFT support |[K,K+3194);134 later canonical samples remain outside complete blocks |
| Full7-block raw FFT support |[17179869145,17179875546) |
| Two-block raw FFT support |[17179869145,17179871076),1931 samples |
| Pilot selected |512 supported CI16 outputs,2048 bytes |
| Full offline pilot cascade |683 outputs,90 initial unsupported,593 supported before selection |
| Native capture |260 ORIGINAL raw samples,[17179870128,17179870388) |
| Native aperture |129 raw lags[-64,+64],121 qualified lags[-60,+60],132 taps each |
| Native packet |26 public-format words; exact winnerlag0 |
| Native winner |Cr=Ex=Eh=1073746351,Ci=0,power=1152931226285815201 |

Every x2 mixed word and full convolution sum is retained; an independently
implemented convolution/rounding trace byte-matches the existing streaming
integer conditioner. Forward/product/inverse exponents are respectively
`[1,3,1,1,1,1,1]` and`[1,4,2,2,2,1,2]`. The independently derived coarse score
at520 is255, an observed numerical control result, not a threshold/admission
criterion added after evaluation. Both343x2 and447x2 map arrays are independently
accumulated from the selected sequential scores.

Pilot mixed/halfband/full-cascade words and indexes are retained and checked
against the separate streaming integer oracle, including chunk invariance.
The selected first/last newest canonical indexes are8589934350/8589937416.
Centers are`n-269`, not newest indexes; raw centers are[17179868162,17179874294]
inclusive and raw support is[17179867617,17179874840). Absolute modulo6 phase
is preserved, giving12 raw samples between pilot centers. Acquisition group
delay is already corrected in canonical indexes and must not be subtracted
again. Selected pilot support and center coverage include the native capture
and two-block reduced-map FFT envelope, **not the full seven-block ledger**.
Later coarse evidence stays available for arithmetic/tail checks without a
false full-ledger pairing claim.

Conditioner saturation, all three pilot-stage saturation counts and69-bit
normalization saturation are zero. Native legality checks all121 tuples against
the actual rate-scaled capture/aperture and existing hardware predicates:
signed39 C, positive unsigned38 Ex, positive unsigned31 Eh, no saturation.
All129 direct tuples remain in a separate raw-aperture JSON record. Tests of
predicate limit values are not arithmetic qualification of those extremes.

The planned latest native command-accept sample is`2*K+256`; capture starts
at`2*K+976`. The scheduler subtracts the next sample, so available lead is719,
not720, against minimum128. This is offline arithmetic eligibility only:
actual AXI writes, CDC acceptance, timing, source continuity during capture and
core-consumption/concurrency witnesses remain unmeasured.

## Tests, attempts and host runtime

Final v5:134 tests PASS, comprising91 additive tests and43 existing pure
conditioner/pilot/native-coefficient tests. Mutation coverage includes every
cohort field, bool/float aliases, rate/edge, halo/phase/length, packing/lane swap,
native66 substitution, wrong15/60 kernels, self-rehashed numeric files,
source snapshots, extra files, signed rounding/clipping and next-sample lead
boundaries. All FFT input words/indexes/positions and zero padding are checked.
Ruff is clean; FW tracked-file diff and HDL status confirm no existing/runtime
edits. There were no numeric test failures in v1-v5.

The actual host was`gauss`, x86_64 Intel Core Ultra9 285K, Linux7.0.0-30,
Python3.11.16, NumPy2.4.6. `/usr/bin/time` measured:

| Final command | Host elapsed | Peak RSS |
|---|---:|---:|
| Generate complete cohort |0.70s |73700 KiB |
| Independently rederive/verify |0.67s |74148 KiB |
|134-test gate |6.31s (pytest6.13s) |97740 KiB |

These are host offline observations, not ARM/Zynq capacity, live deadlines or
detector runtimes. Earlier attempts remain under`build/high-rate-offline-v1`
through`v4`:86/89/132/134 tests passed respectively. v2 added input-word/index
coverage and numerical environment fingerprints; v3 included the existing
pure tests; v4 explicitly separated fixed frequency translation from CFO;
v5 added the omitted25-byte package initializer to provenance. All51 v4/v5
numeric files byte-match. Earlier source snapshots/cohorts remain on disk;
the portable archive retains their test logs/JUnit plus the complete final
cohort and its provenance.

Replay from the pinned FW/HDL source checkout with the frozen Python/NumPy and
installed, hash-matching Vivado2022.2 FFT C model:

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python tools/generate_starlink_high_rate_paired.py build/high-rate-offline-v5/cohort --verify
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest tests/test_starlink_high_rate_paired.py tests/starlink_oracle/test_ddc.py tests/starlink_oracle/test_pilot_ddc.py tests/test_starlink_pss_tracker_coefficients.py -q
```

For fresh generation, supply an absent child directory of an existing parent.
Archive:`reports/experiments/20260910-high-rate-paired-offline.tgz`; its external
receipt records the archive SHA and member count without a circular self-hash.

## What remains unqualified

This is only the30-upper frozen offline cohort. No60 or lower paired cohort
was admitted. Lower standalone filter support is not integrated edge selection.
Two cleanup/prime raw beats are explicitly outside the fixture, and no source
continuation tail after its endpoint is supplied. A future actual bench must
freeze those extra bytes/counts if it claims traffic during later computation,
STOP, drain/read/release or recovery; these cannot be inferred from this file.

Actual bank+STOP at30/60 still requires reviewed public admission/ABI work:
retain existing guards; solve disabled-DDC startup by observing the real raw
CDC rather than waiting for nonexistent disabled canonical output; include
DDC saturation bit13 with service health in the new STOP mask (`0x77ff`, not
the current source15-only`0x57ff`); define version/capabilities/DDC high-word
semantics; update the PSMA driver contract/STOP/health serialization. No guard
was bypassed here. An existing admitted dedicated-core composition would be
only a numerical intermediate, never a substitute bank deployment.

There is no actual core-consumption witness, paired fine/coarse feedback,
retrospective native buffer, causal future-repeat command,120ms dwell/three-map
deadline proof, RF truth/timing accuracy, noise false-alarm qualification,
DMA/IIO/host throughput, hardware capacity or physical implementation claim.
