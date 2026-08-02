# SPF direct-USB stability v3

This document records the source graph, failure evidence, build procedure, and
release gate for the supervised direct-USB firmware. The source is published on
`master`, while the generated image remains RAM-test-only until every hardware
condition below passes.

## Pinned source graph

The repository intentionally contains independent histories for the firmware,
Buildroot, and USB gadget. They are connected by exact commit pins, not by
merging the Buildroot or gadget branches into firmware `master`.

| Layer | Branch | Commit | Relationship |
|---|---|---|---|
| USB gadget | `codex/gadget-stability-v3` | `2072e1d0823ef6db3bc141dd733a90d76e23fc33` | Buildroot package SHA |
| Buildroot | `codex/buildroot-gadget-supervisor-v3` | `f37fe105` | Firmware `buildroot` gitlink |
| Firmware | `master` | `f53dd006` | Candidate source |

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

Linux provides `no_disconnect=1` to defer teardown after the last FunctionFS
descriptor closes. Inspection of the pinned Linux 5.15 implementation and a
hardware crash test exposed an important second step: reopening `ep0` from the
deactivated state resets and unregisters the FunctionFS configfs item. Doing
that while the UDC remains bound makes the whole radio disappear. The v3
candidate therefore:

1. mounts only `sdr_gadget_ffs` with `no_disconnect=1`;
2. leaves the standard IIO FunctionFS mount unchanged;
3. unbinds the composite UDC only after a child failure;
4. starts a fresh `sdr_usb_gadget` child while the UDC is unbound;
5. waits for an explicit, flushed `Ready :-)` line;
6. rebinds the UDC with bounded retries.

The host sees a short, explicit re-enumeration after a process crash. The radio
must return with the same serial and physical USB path, a fresh process nonce,
working standard USB-IIO, and working direct USB. Normal capture start/stop does
not invoke this path or re-enumerate the device.

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

Previous rejected RAM-only candidate:

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

Current RAM-only candidate:

```text
build/pluto.dfu
SHA-256 86f2115eb344efcbd3d59af02caf80d396291cb9e20dcb01651cacf7e0334191
```

Embedded versions:

```text
device-fw v0.38-plutoplus-spf-gain-rssi-fingerprint-v2-8-gf53d
buildroot f37f
gadget 2072e1d0823ef6db3bc141dd733a90d76e23fc33
```

## Validation record

Source checks:

- USB gadget native tests: 10/10 passed.
- Buildroot supervisor test: enforces `no_disconnect`, UDC unbind before every
  replacement launch, explicit child readiness, and UDC rebind afterward.
- ARM cross-build: passed after fetching gadget `2072e1d0` from GitHub.

Hardware evidence before the final design:

- one-radio production-size capture gate: 4 passed, 2 dual-radio tests skipped;
- deliberate child crash: failed because the old design lost the composite USB
  device, confirming that candidate must not be promoted.

Hardware evidence for SHA-256 `de5264...` rejected that candidate: normal
simultaneous dual-radio capture passed, but killing the first direct-USB child
removed that radio from the host indefinitely. A controlled experiment on the
second radio proved that unbind, restart-to-readiness, and rebind returns the
same serial and path with both interfaces. A replacement image using that
sequence is being rebuilt and remains RAM-test-only.

## Release and field-deployment gate

The candidate must not become a release asset or Rover boot image until all of
the following pass:

- both expected radios enumerate by serial and physical path;
- standard USB-IIO and direct USB coexist on both radios;
- simultaneous production-size finite capture passes without loss;
- killing each direct-USB child produces a new process nonce;
- USB-IIO returns after the bounded recovery re-enumeration;
- three consecutive recovery cycles pass per radio;
- post-recovery IQ frames have continuous sequences and valid metadata;
- the Pi reports no undervoltage or throttling;
- QSPI remains unchanged and rollback is verified.

Until then, load this image into RAM only. Do not publish it as a release asset
or change the firmware consumed by Rover boot.
