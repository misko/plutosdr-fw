# Fresh coarse25 checkpoint — C0 failed, not deployed

**Historical checkpoint, superseded by [continued progress](FPGA_COARSE25_PROGRESS.md).**
The user reaffirmed the full 2.5/5/15 MS/s FPGA PSS plus 2.5 MS/s inspection
goal. Work continued without substituting an IQ-only objective. The failed
unrecentered detector below remains a real failure, not a deleted result.

2026-09-12. The new feasibility screen found a problem before RTL implementation
or a long build. This is **not** completion of implement/test/deploy/verify.
The frozen [plan](FPGA_COARSE25_PLAN.md) is retained unchanged so its hash and
pre-evaluation acceptance criteria remain auditable. This file is the current
status; the plan's initial ledger is historical.

## Implemented and tested

- New isolated firmware and HDL branch `codex/pss-coarse25-do-not-merge`, based
  on the preserved baseline, not the stopped shared-FFT experiment.
- Bounded 16-tap direct PSS correlation screen using the exact existing fixed
  15 -> 2.5 MS/s conditioner, nine pre-filter CFO template hypotheses, causal
  filter support and exact fractional-frame phase folding. No hardware access,
  same-window CFO prior, or GLRT timing seed is used by this search.
- Preparation pins source windows, code, configuration and NumPy version before
  evaluation. Receipts distinguish synthetic/model evidence from live hardware.
- 45 tests pass: 15 new detector-contract tests plus 30 existing conditioner
  tests. This is not an HDL or full-repository regression count.
- All 18 noiseless synthetic phase/CFO cases pass the one-inspection-sample
  timing bound. These use the same waveform/filter family as the templates:
  they check coordinates, not independent analog-model or modulation realism.
- 32 seeded white-noise and three CW controls produce no threshold crossing.
  Maximum control z is 6.55647, below the frozen threshold of 8. This small
  sample does not qualify a deployment false-alarm rate.
- All score/phase/control results reproduce exactly in a second complete run;
  only measured processing wall time differs.

## Failed real-data gate

The held-out intervals are 120 ms each from capture
`cap-20260909T121248-414fb81f488c`, through the previously retained canonical
15 MS/s derivative. Historical pilot phases are used only after the blind
detector finishes, for comparison. They are not absolute RF timing truth.

| Interval | Blind PSS phase (us) | Saved pilot phase (us) | Difference (us) | Peak z | Gate |
| --- | --- | --- | --- | --- | --- |
| 36.5 s | 213.2000 | 400.4667 | 187.2667 | 8.69046 | FAIL |
| 37.0 s | 214.2667 | 401.2667 | 187.0000 | 8.06742 | FAIL |

Both select the +300 kHz hypothesis. The historical 1.0 s and 1.5 s negative
controls pass (z 4.50292 and 5.03896). A strong peak alone is therefore not
sufficient to identify PSS timing in these recordings.

A separate **label-assisted diagnostic, not an acceptance run**, inspected
the +/-2 us neighborhood of the saved pilot epoch across all nine hypotheses.
Its maximum z was only 3.02245 / 3.92976. The correct neighborhood is not just
a slightly weaker above-threshold runner-up. Existing wider-band PSS evidence
also places a candidate near the pilot epoch (e.g. 5997 canonical samples,
399.8 us, in the first saved prior-assisted 256 ms report). Different supports
and prior assistance mean that older result is corroboration, not a fair new
120 ms blind detector benchmark.

The 16-tap templates retain 97.92–99.85% of the energy of their **already
filtered** references. This does not reverse the substantial information loss
from selecting the narrow RF band. The exact physical cause of the real-data
wrong-epoch peak is not established by this screen. In particular, it is not
valid to declare it a different received frame, correct it by subtracting a
constant, or lower the threshold after inspecting these outcomes.

Current limitations: upper-edge screen only, zero drift hypothesis, bounded
residual CFO, noiseless synthetic positives, direct power correlation rather
than a statistically qualified interference-rejecting detector. No actual
2.5 MS/s AD9361 analog-response qualification has occurred.

## Radio preflight — read-only, settings unchanged

Both attempted radio probes acquired the PPU global serial lock for their
duration. Locks were released afterward; no continuing reservation is claimed.

- `.18`, serial `1040007c4a94000211000b009186843ef2`: exact USB sysfs
  `/sys/bus/usb/devices/3-11`, URI `usb:3.101.5` at observation time. PPU exact
  USB selection and IIO context serial agree. Read-only RX attributes were
  30.72 MS/s, 18 MHz RF bandwidth, slow-attack gain control, 71 dB gain.
  The existing Ethernet SSH attempt closed before accepting the read-only
  script. No repair, reset or configuration change was attempted.
- `.17`, expected serial `104000bac4950008230026001b440a003a`: Ethernet-only
  attempt at 192.168.1.17 rejected the saved SSH pin with
  `SetupSshHostKeyChangedError`. Identity was **not** remotely re-attested.
  The trust check was not bypassed and the saved pin was not changed. Resolve
  the endpoint identity and authorized SSH trust update before deployment.
- No TX enabled, buffers started, captures taken, firmware loaded or radios
  rebooted. No operations on .14/.20/.21 or other radios.
- PPU source was not changed. Its four existing dirty files were preserved;
  there are no new PPU changes requiring publication to main.

## Decision and remaining work

**Do not implement/promote this particular detector in RTL or deploy it.**
The failure was found inside the first feasibility timebox; another timing-
closure build would not address this algorithmic acceptance failure.

C1-C5 remain unimplemented/unverified on the fresh branch. The smallest useful
next release is the independent 2.5 MS/s IQ capture/IIO foundation on .18,
then serial-trusted .17, with blind host GLRT as the reference. That is a
capture-only milestone, not the originally requested FPGA PSS deployment.
Seek user direction before dropping the detector requirement or starting a
replacement-detector campaign. A replacement must keep this failure visible,
freeze a new comparison, and use new held-out windows to avoid claiming these
now-inspected windows as fresh holdout data.

## Evidence and reproduction

- [Frozen evaluation plan](reports/coarse25-screen-20260912/plan.json), SHA256
  `7a97780a6fbcddedd8cb52eae93d21dc85818ec8d96efec91a86d7e35e5c3906`.
- [Published repeat-run results](reports/coarse25-screen-20260912/result.json),
  SHA256 `6a16cd0cb9ab079a9dde7619b717f4a31ff99969ddaab63dc5c2aed74ffa04e1`.
- First result at
  `/srv/bulk/leo/starlink-pss-preflight.RVtFMZII/fresh-coarse25-artifacts.ZwJPCrqH/screen-v1/result.json`,
  SHA256 `fa8ff119fbdcab80e8bf285ccde23b50c5a7a809026e9e94f8c63cd8ef1d3c51`.
- Saved independent pilot comparison receipt:
  `/tmp/starlink-coarse-alternatives.Y3JzOI/narrow-coarse/reports/narrow-coarse-20260910-v1/study-result.json`.
  Source of comparison values, not detector input.

Run from this firmware worktree, with NumPy 2.4.6 and the recorded source files
available. Use a new output directory; receipts are never overwritten:

```sh
python -B -m pytest -q -p no:cacheprovider tests/test_starlink_coarse25.py tests/starlink_oracle/test_pilot_ddc.py
python -B tools/starlink_coarse25.py prepare --output /path/to/new-screen
python -B tools/starlink_coarse25.py evaluate --output /path/to/new-screen
```

Evaluation exit status **2** means the frozen acceptance screen failed, not
that pytest failed. No firmware, live lock, transport or deployment success is
inferred from these offline tests.
