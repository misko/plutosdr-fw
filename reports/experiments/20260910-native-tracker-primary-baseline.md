# Native tracker reference before concurrent bank integration

Primary FW `9c6bee20cf9d970067bb5f8c8fc336ab85e3590d`, HDL
`9759cf121e899975e841b17c593289cf646249fa`. No runtime or test source changed.
Root reran the existing DSP-choice public-AXI tests in a fresh directory,
`/tmp/starlink-native-baseline.ud78ix`: **4 passed,18 deselected,29.24s**.

The15/30/60 geometry cases pass with66/132/264 taps,61/121/241 qualified lags,
26-word packets and three checked metadata packets each. Coordinated reset,
retained result, concurrent telemetry snapshot and deferred-candidate witnesses
remain. These functional clocks/stimuli are not measured sustained ADC rates.
The independent recorded15-rate replay passes210 windows/5,460 packet words,
210 fixed/float lag matches and zero reported errors. It includes130 injected
window-zero samples and209 direct windows; it is not an ambient capture.

Command, from the primary firmware worktree:

```sh
/home/mouse9911/gits/pluto-plus-utils/.venv/bin/python -m pytest -q \
  tests/starlink_oracle/test_track_reducer_choice.py \
  -k 'actual_axi_wrapper_with_explicit_dsp_choice or actual_dsp_wrapper_preserves_all_210_recorded_window_packets' \
  --basetemp=/tmp/starlink-native-baseline.ud78ix/pytest \
  --junitxml=/tmp/starlink-native-baseline.ud78ix/results.xml
```

Use a **new output directory** for a repeat; pytest basetemp is disposable.
Archive `20260910-native-tracker-primary-baseline.tgz` preserves the four exact
source/fixture sets, bench changes made by the existing test harness, logs,
JUnit result and test driver; waves/executables are excluded. SHA256:
`75e564063355f36cf71d3e6823a4ea6e06ccb2626dcb7de7cbabcdf32550b964`.
JUnit SHA256:
`dc9b43196d27084e6fa3106dff06ea9122375dd5c6a663cec4d45defb5d96201`.
Pytest's `*current` aliases are not additional runs or additional evidence.

The remaining integration test must feed **the same original-rate source** to
native tracking and to the actual coarse canonicalizer/pilot path. It must
check native26-word results, coarse scores/maps and independent pilot bytes
together, including stop/reset/retune ownership. First prove15-rate wiring,
then rate-matched30/60 canonical filtering and source-index units. Existing
paired coarse/pilot and separate tracker passes cannot establish concurrent
composition, causal coarse-to-fine scheduling, DMA/IIO delivery, native60 timing
accuracy, routed timing or RF acquisition. All remain release gates.
