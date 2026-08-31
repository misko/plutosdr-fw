# Minimal direct-async IQ prototype

This worktree isolates the smallest reviewed no-RAM-ring path from the earlier
DDR-ring and zero-copy experiments. It is a prototype based on firmware main
`4f15c87033e332293711ad679a50af0109c72862`; it is not merged, published, or
authorized for persistent flash.

## Scope

The only new data-plane mode is one finite request:

```python
with radio.begin_metadata_capture(
    1_048_576,
    kernel_buffers=12,
    direct_async_frames=23,
    ddr_ring_bytes=0,
) as capture:
    blocks = [capture.read_block() for _ in range(23)]
```

The host sends one bounded `READBUFMA` request. On the radio, a producer owns
the next DMA block while the existing network worker transmits the current
block. The producer queue contains metadata and DMA-block leases only; IQ is
never copied into a DDR/RAM ring. A DMA block is released only after all of its
IQ bytes have been accepted by the existing TCP transport.

Direct mode fails closed unless all of these conditions hold:

- metadata ABI 3 and exactly one receiver;
- `iio,buffer-direct-async=1` is advertised;
- 2--64 kernel buffers and 1--64 finite direct frames;
- DDR burst and DDR ring storage are both disabled.

Generic host prequeue controls, DDR-ring pipeline controls, `sendfile`,
`splice`, cached-ring zero-copy, and firmware/FPGA changes are deliberately
excluded.

## Source graph

| Component | Branch | Commit | Change |
| --- | --- | --- | --- |
| libiio | `codex/iq-direct-async-main-refresh-libiio` | `c3fb64580fd2a48cf71fa9ebf60c2555d6c252ed` | bounded DMA leases, one direct wire command, async producer, capability, Python binding, tests |
| Buildroot | `codex/iq-direct-async-main-refresh-buildroot` | `f17bd6e2a0853e975c3f5a86e14f096bc16fe05c` | pin the exact libiio prototype |
| host | `codex/iq-direct-async-main-refresh-host` | `a7ceeae9a1a8c44a81c9f58518a0200ef8837d89` | expose `direct_async_frames`, fail-closed admission, runtime attestation, tests |

The refreshed libiio series descends from current `origin/master`
`4c6022caf838813c1fc88d6de7a83f2bb5fa8e9f`.  `git range-diff` reports all
nine prerequisite/direct patches as unchanged, and the refreshed final tree is
identical to the previously measured `393cd218` tree.  The refreshed host
commit descends from current `origin/main`
`1d1cdb1241ec8dcda7ff0ee68bafcbfd1ddff4a1` and therefore retains its ABI-4
DMA-gap accounting.

The libiio implementation adds 892 non-test lines across 15 files. The old
accumulated experimental branch changed roughly 3,955 lines and included DDR
ring and rejected zero-copy work.

The libiio commit and proposed immutable source ref are local only. The ARM
cross-build and hardware deployment use this exact local commit; a reproducible
full firmware image intentionally remains blocked until publication is
separately authorized. No branch, tag, or artifact was pushed.

## Verification

Clean native release, ASan/UBSan, and ARM cross-builds pass. The native and
sanitized builds each pass `test_buffer_block_lease`,
`test_direct_async_transport`, `test_metadata_batch_core`,
`test_iiod_command_batch`, and `test_thread_pool_affinity`. The libiio Python
binding suite passes 33 tests. The complete refreshed host suite passes 1,157
tests with 11 explicit browser, hardware, or transmitter skips; Ruff and
strict mypy over 64 source files also pass.

The ARM build used the firmware-main Linux UAPI and the exact metadata provider
from firmware commit `3294365ff44da26b261be4a2ccb241b7896d23ad`. Its outputs
are ARM32 EABI5 and have these SHA-256 digests:

- `iiod`: `40f22164440fd12d6692846e5d8d41a7f1bbad36785c7502eda7da628902ff90`
- `libiio.so.0.25`: `9a00dcecbe1bb156fd622849558adc0fcda57b2f2e2d28b9fcbf7f443bd8112e`

Hardware testing was nonpersistent and used radio `192.168.1.15`, serial
`104000b29905000e17000800065934759d`. The installed firmware remained
`v0.40-plutoplus-spf-tandem-agc-v7`; its system iiOD and library were not
replaced. The exact cross-built daemon and library ran from a temporary
directory on port 30432, with `iiod -r 1`. Context discovery reported libiio
commit `c3fb645`, metadata ABI 3, `iio,buffer-direct-async=1`, and R/W worker
affinity 1.

The workload was 23 frames of 1,048,576 single-RX CI16 samples: 96,468,992
wire IQ bytes. The radio was at 30.72 MS/s with 12 kernel buffers. Direct runs
set `direct_async_frames=23`, left DDR burst and DDR/RAM ring storage disabled,
and were confirmed as `direct=1 ring=0` by iiOD timing records. Each table value
is the mean of three alternating ordinary/direct runs.

### Low-level host drain

| Mode | Read loop | Full buffer setup + loop | Steady after first frame | Gap frames |
| --- | ---: | ---: | ---: | ---: |
| ordinary | 68.09 MB/s | 49.35 MB/s | 68.77 MB/s | 0 / 69 |
| direct async, no ring | 72.63 MB/s | 51.64 MB/s | 73.53 MB/s | 0 / 69 |
| improvement | +6.67% | +4.63% | +6.92% | -- |

### Application `read_block()` with default PyADI decoding

| Mode | 23-block read loop | Capture setup + loop | Steady after first frame | Gap frames |
| --- | ---: | ---: | ---: | ---: |
| ordinary | 55.71 MB/s | 42.56 MB/s | 56.31 MB/s | 9 / 69 |
| direct async, no ring | 71.97 MB/s | 51.29 MB/s | 73.48 MB/s | 0 / 69 |
| improvement | +29.19% | +20.50% | +30.49% | gaps eliminated |

The application retained all 23 complex64 arrays, totaling 192,937,984 host
bytes. Rates count the 96,468,992 CI16 bytes transferred on the wire, not the
expanded NumPy representation. The direct application runs reported no missing
samples over all 69 frames; ordinary mode reported 12,582,912 missing samples.

The volatile daemon was then deliberately restarted and both layers were
rechecked. The low-level refill loop reached 73.67 MB/s and the complete
`read_block()` loop reached 71.15 MB/s, both with zero gaps. An investigation
also found that pinning the host process to an otherwise idle CPU in the
machine's lower-frequency core group reduced throughput. Qualification values
therefore use the normal unpinned scheduler configuration; concurrent
lower-priority production workers were left running.

All RF and channel settings were snapshotted and exactly restored after every
hardware run. The temporary daemon was stopped after testing, the temporary
radio files were removed, port 30432 was closed, the DMA buffer was disabled,
and the original system iiOD and installed-file hashes were rechecked.

Because the refreshed libiio commit remains local, the hardware test injected
the exact local native and Python modules into the refreshed host adapter after
hash/build verification. It did not fabricate a release receipt. Publishing an
immutable source ref and then producing a full firmware/release image remain
separate authorization gates.
