# Experimental GLR1 host workflow

This profile exports one continuous 2.5 MS/s little-endian CI16 stream and
separate 64-byte native FPGA GLRT events. The current board/driver profile is
upper-edge only. Receiver source rate is compiled into the FPGA image and must
match the configured AD9361 clock. Source rates are 2.5/5/10/25/60 MS/s.

The hardware window belongs to the original FPGA task. Obtain its allocated
window before opening a context; this task's user authorization does not imply
that a shared radio is currently available. All capture commands below arm IQ.
No hardware has yet been qualified by this workflow.

## Capture

`starlink_glrt_capture.py` uses libiio 0.21..0.x through a small ctypes binding;
the tested host library loads as 0.26. It checks both contexts' exact `hw_serial`
and `fw_version`, the GLR1 ABI, source clock, RX LO/bandwidth and TX powerdown.
Configure the RF path beforehand in the allocated window. The collector does
not tune, deploy, or unmute TX. It records gain/port state before and after.

For a 120 ms observation with an already loaded and configured 2.5 MS/s image:

```sh
python3 tools/starlink_glrt_capture.py \
  --uri '<allocated exact IIO URI>' \
  --serial '1040007c4a94000211000b009186843ef2' \
  --firmware-version '<exact /opt/VERSIONS device-fw label>' \
  --source-rate 2500000 --lo-hz '<configured RX LO>' \
  --bandwidth-hz '<configured RX bandwidth>' --visit 101 \
  --samples 300000 --chunk-samples 25000 --output artifacts/capture-101
```

Use a nonzero visit ID different from the preceding observation. Finite sample
limits must fill whole even-length CI16 buffers; one invocation is bounded to
30 seconds. IQ uses four kernel buffers. Events use one-record client refills
and a requested 1024-record kernel kfifo, preserving a short final event tail.
This relies on the pinned target libiio software-buffer behavior and still
requires real network/USB qualification.

The driver caches `capture_baseline_snapshot` after CLEAR/configuration and
before ARM. Reading it after IQ buffer creation cannot miss early event counts.
On completion or error the collector disables IQ first, saves the final
snapshot, drains all CPU-pushed current-visit events, cancels the event reader,
then closes the event buffer and contexts. Other-visit records remain in
`events.raw` and are counted separately. Event failure does not shorten IQ.

`summary.json` reports IQ-prefix and event-transport attestations separately.
Partial IQ and final metadata are retained on failure. An attested prefix checks
actual saved bytes against FPGA endpoints/counters; it does not prove analog
clipping immunity, input-eye calibration, RF truth or complete detector coverage.
Busy rejections, pending work and DDC clipping remain explicit fields. Context
firmware labels must be bound to the separately recorded deployment manifest;
the collector cannot read back a bitstream hash from the current GLR1 registers.

## Independent offline GLRT

The numerical reference is the clean Leo commit
`5f25fc57cca3ea564ac42debe3561139592c82b0`, in the isolated checkout
`artifacts/host-reference-5f25fc57`. Its environment is installed with
`uv sync --frozen --no-dev --project artifacts/host-reference-5f25fc57`.
The native acquisition extension must be built by that installation. Inputs,
reference source, native extension and dependencies are recorded and checked.

```sh
artifacts/host-reference-5f25fc57/.venv/bin/python tools/starlink_glrt_host.py \
  --leo-source artifacts/host-reference-5f25fc57 \
  --iq artifacts/capture-101/iq.ci16 --edge upper \
  --minimum-exact 0.175 --minimum-margin 0.025 \
  --output artifacts/capture-101-blind
```

The example gates are previously used development settings, not independently
qualified thresholds. Freeze the chosen settings before a new evaluation. The
analyzer has no FPGA-event input. It searches every overlapping 20 ms window
with 10 ms stride, retaining a short tail and reporting insufficient support
when fewer than two frames can be acquired. It preserves all eight retained
candidate basins and their scalar GLRT-64 scores and integer sample support.
Noise-only windows are still analyzed. Overlapping windows are correlated.

Acquisition CFO search is +/-100 kHz around the digital pilot band center.
The subsequent periodic GLRT residual can put tracking CFO outside that band;
`within_cfo_comparison_band` and the separate in-band positive count preserve
that limitation. Integer timing uses the 0.4 us output grid. The host uses a
multi-frame coherent-ceiling statistic and intra-symbol CFO correction; FPGA
scores use single-frame symbol energy normalization without that correction.
Raw scores must not be treated as identical estimators.

Compare FPGA events only after the blind output is finalized and hashed. Use
`Snapshot.source_center()` and `Event.observable_interval()` for counter/filter
mapping, never as acquisition seeds. A complete comparison, agreed tolerances,
fresh holdouts and live validation are still required by the firmware goal.

`starlink_glrt_saved_development.py` replays every record of a specified hashed
LPP1 worker pack. It uses recorded CI16 and edge, preserving old labels solely
as provenance. Those previously examined saved probes are development data;
they are neither fresh holdouts nor GLR1 transport evidence.
