# v0.49 Pluto+ direct-async IQ v4

Release: `v0.49-plutoplus-spf-iq-direct-async-v4`  
Status: **hardware-qualified full release**  
Trusted build: [run 33535095284](https://github.com/misko/plutosdr-fw/actions/runs/33535095284)  
Built source: `bc00edb8c340dd4f9b04361398cbd2c8edcc9cae`

## Outcome

V0.49 makes direct-DMA admission authoritative. Earlier firmware exposed the
number of buffers requested by iiOD, not the number Linux actually allocated.
The frequently described “47-buffer/~200 MB” profile could therefore be only
12 real buffers on a 64 MiB CMA image while every upper layer still printed
47. V0.49 reads the allocated block count from local libiio, refuses direct
async with `ENOSPC` unless it exactly equals the request, exposes that result
to the host, and supplies a 216 MiB CMA pool for a real 200,000,000-byte queue.

The qualified profile is 50 × 1,000,000 single-RX CI16 samples: exactly
200,000,000 IQ payload bytes and 50/50 allocated DMA blocks. RAM slots remain
optional and extend the same FIFO; both release comparison runs used no RAM.

This is a full persistent release, not an RC or RAM-only release. The exact
trusted-build DFU was RAM-booted twice and then installed on serial
`1040007c4a94000211000b009186843ef2`. PPU verified the serial/path return,
AD9361 identity, TX-safe state, `/dev/mtd3` FIT hash, an independent guarded
reboot, a second FIT readback, 216 MiB CMA, iiOD worker affinity, and a
post-reboot 50/50 allocation capture. Radios `192.168.1.20` and `.21` were not
used or changed.

## What changed

- libiio 0.25 adds `iio_buffer_get_allocated_kernel_buffers_count()` and the
  local backend reports its real mapped block count.
- iiOD carries requested and allocated counts separately, supplies the actual
  value to metadata setup, and refuses direct sessions on any mismatch.
- The context advertises
  `iio,buffer-direct-async-exact-kernel-queue=1`; v4 hosts require it.
- PPU reports `DMA requested/allocated`, rejects mismatches, and fails closed
  against every older ABI-3 runtime.
- Linux reserves 216 MiB CMA at one-MiB alignment. Fifty four-MiB mappings use
  200 MiB and retain 16 MiB of CMA headroom.
- The existing direct producer/consumer, RAM extension, drop-backlog,
  preserve-backlog, stale-metadata recovery, and one-session 4,096-frame target
  remain unchanged.

## Exact release stack and assets

The immutable component table and installation order are normative in
[`IIO_DIRECT_ASYNC_V4_INSTALL.md`](IIO_DIRECT_ASYNC_V4_INSTALL.md). Principal
pins are firmware `bc00edb8…`, Buildroot `2e146948…`, libiio `5cb23897…`,
Linux `7176508d…`, metadata provider `3294365f…`, HDL `145bd47e…`, and U-Boot
`1ff0468e…`. The host must use PPU main commit `ec2b3ee85721011c0ffcb1619c85300672413aba`
(profile implementation `35a827c0…`) or later and must report native libiio
`0.25 (5cb2389)`.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| source/evidence bundle | 134,221,620 | `ef3cace7a72c06f4f617bd7bd9a37fb4a68738c14e8d7beb8aa48969809299a7` |
| DFU | 12,825,831 | `f45524f4765d5743144703ff6f4541084ff1ab9b1ce20a77f3f6fa820a1f84b6` |
| FRM | 12,825,848 | `290d1447657a0feb89340767fe26fa85bb3eaa42e27f90ed5acecfbc3a5cda73` |
| DFU/FRM FIT body | 12,825,815 | `77f899610548d486aab2c83c4dc7170532d470b115d2bd0e8fc43e72b3bfca67` |

The routed design passed the integrated release verdict with WNS 0.767 ns and
WHS 0.019 ns. All artifact-internal `SHA256SUMS` and
`PAYLOAD_SHA256SUMS` entries passed.

## Hardware results

The red admission test requested 47 × 1,048,576 IQ samples. Its IQ-only byte
estimate was below 200 MB, but the ABI-3 prefix and one-MiB alignment prevented
the full queue from mapping; v0.49 correctly returned `ENOSPC` instead of
running a partial queue. The green 50 × 1,000,000 request reported 50/50 and
200,000,000 IQ bytes.

Both 40-second 25 MS/s drop-backlog comparisons returned 1,000/1,000 frames in
one session and restored RF settings:

| Profile | Admission | App payload | Gap events | Missing samples | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| default DMA | 15/15, 60 MB | 55.16 MB/s | 79 | 795M | 55.71% |
| exact 200 MB DMA | 50/50, 200 MB | 65.80 MB/s | 11 | 444M | 69.25% |

The true 200 MB queue cut separate gap events by 86.1% and missing samples by
44.2%. It does not add Ethernet bandwidth; it delays queue saturation and
makes drop-backlog events less frequent.

Radio timing for the 4.000 GB exact-200 MB run recorded 56.430091394 seconds
inside `transport_iq`, or **70.884 MB/s TCP IQ payload**. Short application
cells reached 70.12–72.98 MB/s. End-to-end long-run application timing was
lower and variable while the shared host ran unrelated Vivado and release
qualification workloads; the public report records that distinction rather
than presenting host contention as firmware performance.

The comparison JSON, scripts, and three PNG timelines are in Pluto Plus Utils
under `reports/2026-09-01-iq-direct-async-v4-exact-200m/`.

## Persistent qualification

- RAM receipts `307f9873d626443f860eae1d316bac09` and
  `90114b48365c4a52a0734b452763e8bd` returned the exact v0.49/AD9361/TX-safe
  identity without writing QSPI.
- Persistent flash receipt `45737ca6-7e75-400b-aee0-fbf3e053dc15` completed
  write, sync, unmount, eject, disappearance, same-path return, identity, and
  TX-safe phases.
- Read-only reconciliation matched `/dev/mtd3` to FIT `77f899…bfca67`.
- Guarded reboot receipt `f358a00b24164426b79805255176f1cf` returned the
  same serial/path as v0.49/AD9361/TX-safe.
- A newly enrolled post-reboot SSH key and second reconciliation matched the
  same FIT again; post-reboot PPU capture reported 50/50 allocation and zero
  gaps in its three-second smoke cell.

## Compatibility and rollback

V0.49 keeps metadata ABI 3 and IQ layout, but direct async deliberately
requires the new exact-admission capability and matched `5cb2389` host. An
older v0.48 host or radio is not a supported half-upgrade. Ordinary non-direct
IIO use remains compatible.

Keep the hardware-qualified v0.48 DFU and its PPU persistent profile until all
post-install checks pass. Follow
[`IIO_DIRECT_ASYNC_V4_INSTALL.md`](IIO_DIRECT_ASYNC_V4_INSTALL.md) for download,
host installation, PPU flash, ephemeral SSH-key enrollment, QSPI
reconciliation, speed ladder, and exact rollback commands.
