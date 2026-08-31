# Direct-async IQ queue with optional RAM extension

This prototype is based directly on firmware `origin/main`
`4f15c87033e332293711ad679a50af0109c72862` as observed on 2026-08-31. It
preserves the minimal direct DMA transport and optionally lets the existing
RAM ring extend that same FIFO. The branches are local, unmerged, and not
authorized for persistent flash or publication.

## Interface

Ringless direct mode is unchanged:

```python
with radio.begin_metadata_capture(
    1_048_576,
    kernel_buffers=15,
    direct_async_frames=23,
    ddr_ring_bytes=0,
) as capture:
    blocks = [capture.read_block() for _ in range(23)]
```

RAM extension is opt-in. `direct_async_frames` remains the single finite
target, while `ddr_ring_bytes` contributes extra queue storage:

```python
with radio.begin_metadata_capture(
    1_048_576,
    kernel_buffers=10,
    direct_async_frames=23,
    ddr_ring_bytes=13 * 4_194_304,
    ddr_ring_frames=0,
    ddr_ring_continuous=False,
) as capture:
    assert capture.direct_async_ring_extension
    blocks = [capture.read_block() for _ in range(23)]
```

Standalone finite and continuous RAM-ring modes remain supported. A host can
therefore select direct DMA only, direct DMA with RAM overflow capacity, or the
existing standalone RAM ring without changing the block-reading API.

## Queue semantics

iiOD presents one ordered producer/consumer FIFO. Every descriptor records its
metadata and whether its IQ payload is owned by a DMA-block lease or a RAM-ring
slot.

1. The producer always captures into a kernel DMA block.
2. Normally that DMA-backed descriptor stays in the FIFO until the network
   consumer sends it.
3. When the DMA watermark is reached and RAM extension is enabled, iiOD copies
   the newest eligible queued descriptor into the next RAM slot. It never
   spills the head descriptor because the consumer may already be using it.
4. The descriptor keeps its FIFO position, the DMA lease is released for
   immediate capture reuse, and the consumer later sends the RAM-backed payload
   through the same path.
5. The consumer releases whichever owner backs the descriptor only after its
   IQ bytes have been accepted by the existing TCP transport.

There is no RAM prefill phase, second output queue, or ordering hand-off. RAM
only extends the existing DMA queue. When RAM is disabled, no IQ copy or ring
allocation is introduced.

A 4 MiB copy on the Zynq can consume more than one 30.72 MS/s frame period, and
consecutive spills can accumulate beyond two periods. Combined mode therefore
keeps three DMA blocks available as ingestion headroom when at least five are
configured. Three- and four-buffer configurations scale that reserve to
`kernel_buffers - 2`, retaining both a head lease and a spillable lease. The
logical descriptor capacity is the configured DMA plus useful RAM capacity
minus this reserved headroom; producer and consumer still run concurrently.

RAM status in combined mode counts real RAM spills and drains rather than all
captured DMA frames. Its target is zero because `direct_async_frames` owns
completion. The existing standalone ring continues to report its ordinary
finite target and positions.

The wire request uses the new
`SPF_DDR_RING_FLAG_DIRECT_EXTENSION` bit and iiOD advertises
`iio,buffer-direct-async-ring=1`. Older implementations reject the unknown
flag instead of silently changing semantics.

Direct mode fails closed unless metadata ABI 3, exactly one receiver,
`iio,buffer-direct-async=1`, 2--64 kernel buffers, and 1--64 finite frames are
available. Combined mode additionally requires at least three kernel buffers,
`iio,buffer-direct-async-ring=1`, a nonzero RAM capacity,
`ddr_ring_frames=0`, and `ddr_ring_continuous=False`. DDR burst cannot be mixed
with either direct mode.

## Source graph

| Component | Branch | Commit | Purpose |
| --- | --- | --- | --- |
| libiio/iiOD | `codex/iq-direct-async-main-refresh-libiio` | `b7303fded264e10473bbbb084afade8f1b1373d1` | direct producer, unified DMA/RAM FIFO, spill accounting, DMA headroom, binding and native tests |
| Buildroot | `codex/iq-direct-async-main-refresh-buildroot` | `4a1e90704706756a6f6062482a070e63f9b27573` | exact libiio pin |
| host | `codex/iq-direct-async-main-refresh-host` | `55e3c08ecf703c2a2f6b5367b3e3d64644c58c1a` | API admission, capability checks, status exposure, finite-ring timestamp handling, tests |

The libiio branch descends from current `origin/master`
`4c6022caf838813c1fc88d6de7a83f2bb5fa8e9f`; the host branch descends from
current `origin/main` `1d1cdb1241ec8dcda7ff0ee68bafcbfd1ddff4a1`.
The proposed immutable source ref remains
`iq-direct-async-ring-v1-rc1-source/libiio-v1`, but neither it nor any branch
has been pushed.

## Software verification

The exact `b7303fd` tree was configured and built independently as native
release, ASan/UBSan, and ARM cross-builds. Fourteen self-contained native C
tests pass in both release and sanitizer builds, including direct transport,
DMA leases, ring core/request/status, metadata batching, sampler coverage,
tandem session, and thread-affinity coverage. The Python libiio suite passes
38 tests.

The final host head passes 1,158 tests with 11 explicit browser, attached-radio,
or transmitter skips and one third-party deprecation warning. Ruff passes and
strict mypy reports no issues in 64 source files.

The ARM32 EABI5 outputs contain the exact `b7303fd` build tag:

- `iiod`: `89c5eae83b7bb517279ebe97e3300615c58efbf3892dc9d6939966429122e01d`
- `libiio.so.0.25`: `8fd0530bd712abe6398f300c17c34052a3e86acfbf374680071869f260921841`

## Radio qualification

Testing used `192.168.1.15`, serial
`104000b29905000e17000800065934759d`, at 30.72 MS/s unless noted. The installed
firmware stayed `v0.40-plutoplus-spf-tandem-agc-v7`. The exact ARM daemon and
library ran only from `/tmp` on port 30432 as `iiod -r 1`; installed files were
not replaced. Context discovery reported metadata ABI 3 and both direct and
RAM-extension capabilities from git tag `b7303fd`.

Each qualification captured 23 frames of 1,048,576 single-receiver CI16
samples, or 96,468,992 IQ bytes. Rates below count those wire-format bytes over
the application `read_block()` loop rather than the expanded NumPy arrays.

### Direct DMA, RAM disabled

The acceptance profile used 15 DMA buffers and no RAM. Three final runs were
all sequential from frame 0 through frame 22 with no missing samples:

| Run | Application rate | Gap frames |
| --- | ---: | ---: |
| 1 | 71.40 MB/s | 0 / 23 |
| 2 | 71.24 MB/s | 0 / 23 |
| 3 | 70.93 MB/s | 0 / 23 |
| **Mean** | **71.19 MB/s** | **0 / 69** |

This satisfies the 70 MB/s acceptance target on the refreshed exact revision.
An intentionally shallower eight-DMA-buffer profile still transported above
70 MB/s but overran after frame 14, confirming that throughput alone is not a
continuity guarantee and that finite queue depth is part of the profile.

### Direct DMA with RAM extension

The combined profile used 10 DMA buffers plus 13 RAM slots at 30.72 MS/s. All
three runs delivered frames 0--22 with zero gaps. RAM produced/consumed/high
water counts were 9/9/9, 9/9/9, and 6/6/6, proving that payloads actually
spilled to RAM, retained their FIFO order, and drained before clean
`target_complete` termination. Application rates were 42.80, 53.27, and
67.91 MB/s. RAM-copy contention makes this safety/capacity mode slower than the
ringless fast path, but continuity remained zero-gap in all 69 frames.

### Standalone finite RAM ring

At 20 MS/s, an 8-DMA/15-RAM standalone profile captured and drained all 23
frames with zero gaps. Ring status closed at 23 produced, 23 consumed, a
15-frame high-water mark, one wrap, and `target_complete`. The wire-equivalent
application rate was 44.53 MB/s. The host retains capture-time counter anchors
while draining a completed finite ring, avoiding invalid post-capture timestamp
fits.

Every run snapshotted and restored sample rate, bandwidth, LO, enabled
channels, gain modes, and gains. The restored state was 30.72 MS/s, 18 MHz
bandwidth, 2.4 GHz RX LO, both RX channels, and `slow_attack` on both channels.

The exact source commits remain local, so a reproducible full firmware image
is intentionally gated on publishing an immutable libiio ref. No release
receipt, tag, remote branch, firmware image, or persistent radio mutation is
created by this prototype.
