# SPF direct-USB stability v3

This document records the source graph, failure evidence, build procedure, and
promotion gate for the supervised direct-USB firmware. `master` remains the
rollback baseline until every hardware condition below passes.

## Pinned source graph

The repository intentionally contains independent histories for the firmware,
Buildroot, and USB gadget. They are connected by exact commit pins, not by
merging the Buildroot or gadget branches into firmware `master`.

| Layer | Branch | Commit | Relationship |
|---|---|---|---|
| USB gadget | `codex/gadget-stability-v3` | `2072e1d0823ef6db3bc141dd733a90d76e23fc33` | Buildroot package SHA |
| Buildroot | `codex/buildroot-gadget-supervisor-v3` | `d36f2d93` | Firmware `buildroot` gitlink |
| Firmware | `codex/firmware-stability-v3` | `43354e64` | Candidate source |

The Buildroot pin is verified without `local.mk` or another source override.
Buildroot fetches the gadget commit directly from this GitHub repository and
embeds the full SHA as the gadget build ID.

## Root cause and design

The original restart experiment killed `sdr_usb_gadget`, after which the whole
Pluto composite USB device disappeared and did not return. The host remained
healthy and reported no undervoltage.

The pinned Linux 5.15 FunctionFS implementation explains this behavior. With a
normal FunctionFS mount, closing the last endpoint descriptor resets the
FunctionFS state and unregisters the configfs gadget. A userspace supervisor
cannot reliably reconstruct only one function after that kernel teardown.

Linux provides `no_disconnect=1` for this exact composition case. The v3
candidate therefore:

1. mounts only `sdr_gadget_ffs` with `no_disconnect=1`;
2. leaves the standard IIO FunctionFS mount unchanged;
3. restarts only the `sdr_usb_gadget` child;
4. waits for an explicit, flushed `Ready :-)` line;
5. never writes the composite gadget's UDC attribute during child recovery.

When the direct-USB child closes its descriptors, the function becomes
deactivated while USB-IIO and the rest of the composite device stay registered.
Opening `ep0` in the replacement process resets and reactivates the function.

## Reproducible build

From a recursive checkout of firmware commit `43354e64`:

```sh
make -C buildroot sdr_usb_gadget-dirclean
make -C buildroot \
  BUSYBOX_CONFIG_FILE="$PWD/buildroot/board/pluto/busybox-1.25.0.config" \
  all
cp buildroot/output/images/rootfs.cpio.gz build/rootfs.cpio.gz
u-boot-xlnx/tools/mkimage -f scripts/pluto.its build/pluto.itb
cp build/pluto.itb build/pluto.itb.tmp
dfu-suffix -a build/pluto.itb.tmp -v 0x0456 -p 0xb673
mv build/pluto.itb.tmp build/pluto.dfu
```

The development checkout used an already-built, source-identical `mkimage`
binary because the sparse local U-Boot checkout could not rebuild that host
tool. Kernel, device-tree, and FPGA inputs were unchanged from the tagged v2
firmware. The root filesystem and gadget were rebuilt from the published pins.

Current RAM-only candidate:

```text
build/pluto.dfu
SHA-256 de5264c23ae57fc52fe874541ed9a58891654ac89acf3d2e0d90c93a8026576e
```

Embedded versions:

```text
device-fw v0.38-plutoplus-spf-gain-rssi-fingerprint-v2-5-g4335
buildroot d36f2d
gadget 2072e1d0823ef6db3bc141dd733a90d76e23fc33
```

## Validation record

Source checks:

- USB gadget native tests: 10/10 passed.
- Buildroot supervisor red test: proved the old UDC-rebind design violated the
  required no-disconnect contract.
- Buildroot supervisor green test: passed with the direct FunctionFS isolation
  mount and no UDC writes.
- ARM cross-build: passed after fetching gadget `2072e1d0` from GitHub.

Hardware evidence before the final design:

- one-radio production-size capture gate: 4 passed, 2 dual-radio tests skipped;
- deliberate child crash: failed because the old design lost the composite USB
  device, confirming that candidate must not be promoted.

Hardware evidence for SHA-256 `de5264...` is pending a physical power cycle of
the externally powered test radios.

## Promotion gate

The candidate may be proposed for `master` only after all of the following pass:

- both expected radios enumerate by serial and physical path;
- standard USB-IIO and direct USB coexist on both radios;
- simultaneous production-size finite capture passes without loss;
- killing each direct-USB child produces a new process nonce;
- USB-IIO stays present through each recovery;
- three consecutive recovery cycles pass per radio;
- post-recovery IQ frames have continuous sequences and valid metadata;
- the Pi reports no undervoltage or throttling;
- QSPI remains unchanged and rollback is verified.

Until then, load this image into RAM only. Do not publish it as a release asset
or change the firmware consumed by Rover boot.
