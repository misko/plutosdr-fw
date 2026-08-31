# Direct-async IQ queue with optional RAM extension

This candidate is based directly on firmware `origin/main`
`4f15c87033e332293711ad679a50af0109c72862` as observed on 2026-08-31. It
preserves the minimal direct DMA transport and optionally lets the existing
RAM ring extend that same FIFO. The exact source branches, immutable dependency
tags, and hardware-qualified RC1 assets are published; the firmware remains
unmerged and is not authorized for persistent flash.

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
| Buildroot | `codex/iq-direct-async-main-refresh-buildroot` | `a929267288a80a31407a3af06345c088979bcc2e` | exact libiio pin and archive SHA-256 |
| host | published `main` | `fd76f6694a60c3edc471be12deee942076d5b216` | API admission, capability checks, status exposure, finite-ring timestamp handling, one-command ladder, exact RAM-only RC1 image binding, serial/path-scoped USB route isolation, tests |

The libiio branch descends from its audited `origin/master` base
`4c6022caf838813c1fc88d6de7a83f2bb5fa8e9f`; the host work descends from its
audited `origin/main` base `1d1cdb1241ec8dcda7ff0ee68bafcbfd1ddff4a1`.
The immutable libiio source ref is
`iq-direct-async-ring-v1-rc1-source/libiio-v1`; the matched Buildroot ref is
`iq-direct-async-ring-v1-rc1-source/buildroot-v2`. Both resolve to the exact
commits above and are published. The exact package matrix, submodule pins,
publication order, host runtime procedure, and install/rollback boundary are
maintained in
[`IIO_DIRECT_ASYNC_INSTALL.md`](IIO_DIRECT_ASYNC_INSTALL.md).

## Software verification

The exact `b7303fd` tree was configured and built independently as native
release, ASan/UBSan, and ARM cross-builds. Fourteen self-contained native C
tests pass in both release and sanitizer builds, including direct transport,
DMA leases, ring core/request/status, metadata batching, sampler coverage,
tandem session, and thread-affinity coverage. The Python libiio suite passes
38 tests.

The final host head passes 1,175 tests with 11 explicit browser, attached-radio,
or transmitter skips and one third-party deprecation warning. Ruff passes and
strict mypy reports no issues in 65 source files.

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

### One-command rate/duration ladder

Pluto Plus Utils `37f6c3865` adds a bounded ladder command whose defaults are
the requested 5/10/15/25 MS/s rates and 3/10-second durations:

```bash
pluto radio direct-async-ladder 192.168.1.15 \
  --transport ip --ip-port 30431 \
  --expect-serial 104000b29905000e17000800065934759d
```

The ringless source qualification produced:

| Sample rate | 3 seconds | 10 seconds | Gap events |
| ---: | ---: | ---: | ---: |
| 5 MS/s | 18.65 MB/s | 19.57 MB/s | 0 / 0 |
| 10 MS/s | 38.37 MB/s | 39.03 MB/s | 0 / 0 |
| 15 MS/s | 58.34 MB/s | 58.56 MB/s | 0 / 0 |
| 25 MS/s | 72.50 MB/s | 75.05 MB/s | 8 / 22 |

The command continued through every cell, accounted for missing samples,
restored the RX configuration, and emitted a JSON report with SHA-256
`73682011786c1e55c7d8c3721c17fe82ed7bde9c2716449171dfce6a3e4a9a86`.
Thus the transport clears 70 MB/s at the top rate, but this sustained ladder
also shows that a 15-block finite queue does not make 25 MS/s lossless.

The RAM-extension variant is the same command plus
`--kernel-buffers 10 --ram-ring-slots 13`. All 134 spilled descriptors drained
in order, the high-water mark reached 13, and missing IQ bytes at 25 MS/s fell
from 31,457,280 to 20,971,520. The report SHA-256 is
`4594fe3d573ce063ae105e9fa84e9554456b8b44fbdbddc968886a78cdc8e969`.

Every run snapshotted and restored sample rate, bandwidth, LO, enabled
channels, gain modes, and gains. The restored state was 30.72 MS/s, 18 MHz
bandwidth, 2.4 GHz RX LO, both RX channels, and `slow_attack` on both channels.

The exact dependency tags and host command are published. Trusted build
33360776546 produced the protected version
`v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1`; its DFU SHA-256 is
`6b29618d186d82c6b8fa02f74073853029b7d081196cb8643b92550e09162391`.
That exact image passed guarded RAM boot, combined-queue spill/drain,
standalone-ring, abrupt-client recovery, RF restoration, and guarded return to
the prior persistent firmware on local serial
`1040007c4a94000211000b009186843ef2`.

The local USB-gadget Ethernet link is limited to 480 Mb/s, so the exact
packaged iiOD and library from the final rootfs repeated the full ladder on the
authorized 1 GbE radio at `192.168.1.15` without replacing installed files.
The 25-MS/s cells reached 73.30 and 75.17 MB/s while reporting 7 and 20 missing
frames. RAM reduced total missing frames from 27 to 22 and recorded matching
spill/drain counts. The hardware-qualified RC1 is published as a GitHub
prerelease; persistent QSPI promotion remains unqualified and unauthorized.
