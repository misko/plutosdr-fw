# Pluto+ SPF IQ direct-async + RAM queue v1 RC1

Release tag: `v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1`

This hardware-qualified prerelease overlaps single-receiver DMA capture with
iiOD TCP delivery. Optional RAM slots extend the same ordered descriptor FIFO:
they do not create a second capture path, prefill phase, or output queue. With
RAM disabled, the direct path does not allocate or copy IQ into the RAM ring.

Persistent QSPI installation is not qualified or authorized by this RC. Use
the guarded RAM-only profile first and promote persistent installation only
under a separate reviewed policy.

## Required versions

These components are one compatibility set. Do not substitute stock libiio or
a PyPI-only `pylibiio` binding.

| Component | Required version or commit |
| --- | --- |
| firmware build source | `4af2ab74605a62832f7f38a0eefe3b3bc1d492cf` |
| firmware base | `origin/main` commit `4f15c87033e332293711ad679a50af0109c72862` |
| Buildroot | `a929267288a80a31407a3af06345c088979bcc2e`, tag `iq-direct-async-ring-v1-rc1-source/buildroot-v2` |
| radio and host libiio | 0.25 at `b7303fded264e10473bbbb084afade8f1b1373d1`, tag `iq-direct-async-ring-v1-rc1-source/libiio-v1` |
| SPF metadata provider | ABI 3 at `3294365ff44da26b261be4a2ccb241b7896d23ad` |
| Pluto Plus Utils | package 0.1.0, published `main` commit `fd76f6694a60c3edc471be12deee942076d5b216` |
| Vivado | 2022.2 |
| ARM toolchain | Linaro GCC 7.3-2018.05, 7.3.1 |

The host native library and generated Python binding must both come from the
same `b7303fd` source. The radio daemon must run with `iiod -r 1` or the
equivalent supervised `--rw-cpu-affinity 1` setting.

## Release assets

| Asset | SHA-256 |
| --- | --- |
| `plutoplus-spf-iq-direct-async-ring-v1-rc1-4af2ab74605a-pluto.dfu` | `6b29618d186d82c6b8fa02f74073853029b7d081196cb8643b92550e09162391` |
| `plutoplus-spf-iq-direct-async-ring-v1-rc1-4af2ab74605a-pluto.frm` | `5cd286cae15692cd2df917d954c8e50fe86899ab7877d67b8fc3a04c203df617` |
| `plutoplus-spf-iq-direct-async-ring-v1-rc1-4af2ab74605a.tar.gz` | `3045f0f5045693a4599ee3891ec9fa5e027e7f327fccba7d76de858729ce5c6f` |

The DFU and FRM contain the same 12,821,279-byte FIT body, SHA-256
`47e850f4dabb5be58203991f9b4f5fefc45305335d9594210a661791ac0189e9`.
The rootfs SHA-256 is
`fd802e8fde40ba114f5b5ff46023d744f39c45ff26f902f1a19a3c9f1334226e`.
The packaged iiOD SHA-256 is
`cf950bdcdefa56ff90690e90fad8ce64151997c707ae3236b967b4bcfc6e9ec6`;
the packaged `libiio.so.0.25` SHA-256 is
`7333f76edb775ebea3a51911c42dc5f3e45fb1e082676a867b7fa90b5d61168a`.

Protected Actions run
[33360776546](https://github.com/misko/plutosdr-fw/actions/runs/33360776546),
attempt 1, built those exact bytes with a clean source tree. The integrated
routed verdict is `PASS` and `firmware_release_eligible: true`; routed timing
closed at WNS 0.767 ns, WHS 0.019 ns, and WPWS 0.264 ns.

## Hardware results

The exact final image was RAM-booted on local USB serial
`1040007c4a94000211000b009186843ef2`. It reported the exact v0.46 RC1 identity,
AD9361 paired RX, metadata ABI 3, and both direct/RAM-extension capabilities.
It passed:

- direct 5 MS/s, 3- and 10-second cells with zero gaps on the USB-gadget IP
  link;
- direct plus RAM at 10 MS/s for 29 frames with zero gaps, 9 spills, 9 drains,
  and a high-water mark of 8 slots;
- a standalone finite ring with 23/23 produced/consumed frames, 96,468,992 IQ
  bytes, zero gaps, high-water 15, one wrap, and `target_complete`;
- two abrupt 200 MB client-loss cycles, alternating RX0/RX1, followed each time
  by gapless ring and ordinary-IIO probes without an iiOD restart; and
- exact RF-setting restoration, zero active buffers/faults, guarded reboot to
  the unchanged persistent v0.42 image, AD9361/2R2T U-Boot qualification, and a
  successful 5.8 GHz tune/readback/restore probe.

The local radio exposes only a 480 Mb/s USB Ethernet gadget. That link saturated
and reset at higher ladder cells, so it cannot establish the 70 MB/s Ethernet
gate. The exact iiOD and `libiio.so.0.25` extracted from this final rootfs were
therefore staged without replacing installed files on the authorized 1 GbE
radio at `192.168.1.15`, on isolated port 30432. That exact packaged runtime
produced:

| Sample rate | 3 seconds | 10 seconds | Missing frames |
| ---: | ---: | ---: | ---: |
| 5 MS/s | 18.64 MB/s | 19.55 MB/s | 0 / 0 |
| 10 MS/s | 38.47 MB/s | 39.44 MB/s | 0 / 0 |
| 15 MS/s | 58.27 MB/s | 58.17 MB/s | 0 / 0 |
| 25 MS/s | **73.30 MB/s** | **75.17 MB/s** | 7 / 20 |

This satisfies the 70 MB/s+ transport gate. It does not claim gapless sustained
100 MB/s offered payload at 25 MS/s. The counters deliberately report that
loss rather than hiding it behind command success.

The same ladder with 10 DMA buffers and 13 RAM slots remained gapless through
15 MS/s. At 25 MS/s it delivered 67.69 and 67.95 MB/s, spilled/drained 29/29
and 106/106 descriptors, reached high-water 13, and reduced missing frames from
27 ringless to 22. This is direct evidence that RAM adds capacity to the same
FIFO. RAM mode is a queue-depth/continuity option, not the 70 MB/s fast path.

All ladder commands restored the prior RX settings. The staged daemon, port,
and files were removed afterward; the radio returned to its unchanged installed
iiOD. No QSPI write occurred on either radio.

## Install and test

Install Pluto Plus Utils at or after `fd76f6694a60`, then install its native
runtime from the immutable `b7303fd` libiio tag as described in
[`IIO_DIRECT_ASYNC_INSTALL.md`](IIO_DIRECT_ASYNC_INSTALL.md). Verify the asset
hash before using it.

For first use, RAM-boot the DFU with the exact serial/path-scoped profile
`iq-direct-async-ring-v1-rc1-ram`. Do not copy the FRM to mass storage unless a
separate persistent-promotion policy has authorized that exact serial.

The complete ringless speed ladder is one command:

```bash
pluto radio direct-async-ladder RADIO_ADDRESS \
  --transport ip --ip-port 30431 \
  --expect-serial EXPECTED_SERIAL \
  --rates 5M,10M,15M,25M --durations 3,10 \
  --samples 1048576 --kernel-buffers 15
```

To extend that same queue with RAM:

```bash
pluto radio direct-async-ladder RADIO_ADDRESS \
  --transport ip --ip-port 30431 \
  --expect-serial EXPECTED_SERIAL \
  --rates 5M,10M,15M,25M --durations 3,10 \
  --samples 1048576 --kernel-buffers 10 --ram-ring-slots 13
```

Use `--usb-sysfs-path`, `--isolate-usb-route`, and the printed second
confirmation when testing through one of several locally attached USB-gadget
radios. Save evidence with `--report` beneath an owner-only mode-0700 directory.

Detailed component, host-runtime, verification, rollback, and persistent-safety
instructions are in
[`IIO_DIRECT_ASYNC_INSTALL.md`](IIO_DIRECT_ASYNC_INSTALL.md).
