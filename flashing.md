# Flashing Pluto and Pluto+ firmware

This guide covers the supported ways to load firmware from this repository:

| Method | Persistent? | Image | Recommended use |
|---|---:|---|---|
| USB mass-storage updater | Yes | `pluto.frm` | Safest normal Pluto+ installation |
| U-Boot DFU, SPI-flash mode | Yes | `pluto.dfu` | Headless installation with one unambiguous radio |
| U-Boot DFU, RAM mode | No | `pluto.dfu` | Candidate testing and hardware qualification |
| JTAG bootstrap | Depends | recovery artifacts | Board bring-up or recovery only |

The firmware payload contains the Linux kernel, FPGA bitstream, device tree, and
root filesystem. On Pluto+, normal persistent installation must update only the
`qspi-linux` firmware partition (`mtd3`).

## Pluto+ safety boundary

> **For routine Pluto+ updates, flash only `pluto.frm` or `pluto.dfu` to the
> `firmware.dfu` target. Never install `boot.frm`, `boot.dfu`,
> `uboot-env.dfu`, or a full `*-fw-*.zip`.**

`pluto.frm` is handled by the on-device updater and writes only
`/dev/mtdblock3`. A full firmware ZIP also contains bootloader images and can
rewrite `mtd0` and `mtd1`. Incompatible FSBL/U-Boot images have historically
bricked Pluto+ boards.

Do not write an ordinary branch or `main` CI artifact persistently merely
because it built successfully. Use persistent flashing only for a release that
explicitly says it is hardware-qualified. Test other images with the volatile
RAM procedure first.

## Prerequisites

The examples use Linux and the GitHub CLI:

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends dfu-util gh openssh-client
gh auth status
```

The Pluto runtime SSH address is normally `192.168.2.1`, with user `root` and
the device's configured password. Factory images commonly use `analog`; change
the default password on network-accessible equipment.

Disconnect or stop software that may be using IIO before rebooting or ejecting
a radio. With multiple radios attached, identify every radio by USB serial and
topology. The safest manual DFU procedure is to leave only the intended radio
connected.

## Find and download a release

List releases, newest first:

```bash
gh release list --repo misko/plutosdr-fw --limit 20
```

Show the release GitHub currently designates as latest:

```bash
gh release view --repo misko/plutosdr-fw
```

Capture its tag and URL:

```bash
release_tag="$(
  gh release view --repo misko/plutosdr-fw \
    --json tagName --jq .tagName
)"
gh release view "$release_tag" --repo misko/plutosdr-fw \
  --json url --jq .url
```

Read the release notes before downloading. "Latest" means newest published
release; it does not by itself prove that an image is approved for a particular
radio or deployment. Require an explicit hardware-qualified statement and
check the supported board, host libiio version, and known limitations.

Download the DFU image and checksums into a new directory:

```bash
artifact_dir="$(mktemp -d /tmp/plutosdr-release.XXXXXX)"
gh release download "$release_tag" \
  --repo misko/plutosdr-fw \
  --pattern '*-pluto.dfu' \
  --pattern 'SHA256SUMS' \
  --dir "$artifact_dir"

find "$artifact_dir" -maxdepth 1 -type f -printf '%f\n'
dfu_image="$(find "$artifact_dir" -maxdepth 1 -type f \
  -name '*-pluto.dfu' -print -quit)"
test -n "$dfu_image"
(
  cd "$artifact_dir"
  grep -F "$(basename "$dfu_image")" SHA256SUMS | sha256sum -c -
)
dfu-suffix -c "$dfu_image"
```

Stop if the checksum or DFU suffix check fails.

### Download the hardware-qualified v5 release directly

The frame-metadata v5 release is
`v0.38-plutoplus-spf-libiio-metadata-v5`:

```bash
release_tag=v0.38-plutoplus-spf-libiio-metadata-v5
artifact_dir="$(mktemp -d /tmp/pluto-v5.XXXXXX)"
gh release download "$release_tag" \
  --repo misko/plutosdr-fw \
  --pattern '*-pluto.dfu' \
  --pattern 'SHA256SUMS' \
  --pattern 'libiio-frame-metadata-v5.yaml' \
  --dir "$artifact_dir"

dfu_image="$artifact_dir/plutoplus-spf-libiio-metadata-v5-d7c87a9a2809-pluto.dfu"
(
  cd "$artifact_dir"
  grep -F "$(basename "$dfu_image")" SHA256SUMS | sha256sum -c -
)
```

The expected v5 DFU SHA-256 is:

```text
948b46506febacb087f3955be86015e074f8c0e3370a9dfc6a942e735d97f882
```

## Method 1: persistent update through USB mass storage

This is the preferred normal Pluto+ method. It uses `pluto.frm`, which the
running radio validates before writing only the `mtd3` firmware partition.

### Obtain `pluto.frm`

A local full build produces `build/pluto.frm`. Releases from this repository
currently publish `pluto.dfu`; both formats wrap the same FIT image. Convert a
downloaded DFU without rebuilding:

```bash
test -n "${dfu_image:-}" && test -f "$dfu_image"
frm_image="$artifact_dir/pluto.frm"
itb_image="$artifact_dir/pluto.itb"

cp -- "$dfu_image" "$itb_image"
dfu-suffix -D "$itb_image"
printf '%s\n' "$(md5sum "$itb_image" | awk '{print $1}')" \
  > "$artifact_dir/pluto.frm.md5"
cat "$itb_image" "$artifact_dir/pluto.frm.md5" > "$frm_image"

body_md5="$(head -c -33 "$frm_image" | md5sum | awk '{print $1}')"
trailer_md5="$(tail -c 33 "$frm_image" | tr -d '\n')"
test "$body_md5" = "$trailer_md5"
grep -aq 'ITB PlutoSDR (ADALM-PLUTO)' "$frm_image"
```

### Identify and mount one radio

Inspect block devices before choosing a target:

```bash
lsblk -o NAME,PATH,TRAN,MODEL,SERIAL,LABEL,FSTYPE,MOUNTPOINTS
```

The following example deliberately requires an explicit partition. Replace
`/dev/sdX1` only after matching it to the intended Pluto serial:

```bash
pluto_partition=/dev/sdX1
pluto_disk=/dev/sdX
mount_point="$(mktemp -d /tmp/pluto-msd.XXXXXX)"

sudo mount "$pluto_partition" "$mount_point"
test -f "$mount_point/info.html"
sudo cp -- "$frm_image" "$mount_point/pluto.frm"
sync
sudo umount "$mount_point"
rmdir "$mount_point"
sudo eject "$pluto_disk"
```

Ejecting triggers the updater. The radio disconnects, writes QSPI, resets, and
re-enumerates. Do not remove power during the write.

Desktop file managers use the same mechanism: copy **only** `pluto.frm` to the
Pluto volume, wait for the copy to finish, and safely eject the volume.

## Method 2: persistent firmware-only DFU update

This loads `pluto.dfu` through U-Boot's SPI-flash DFU mode. It is equivalent in
scope to the mass-storage method when—and only when—the selected alternate is
`firmware.dfu`.

First request SPI-flash mode from the running radio:

```bash
ssh root@192.168.2.1 '/usr/sbin/device_reboot sf'
```

Wait for DFU enumeration and inspect every alternate:

```bash
dfu-util -l -d 0456:b673,0456:b674
```

With exactly one intended radio connected, write only `firmware.dfu` and reset:

```bash
sudo dfu-util -R \
  -d 0456:b673,0456:b674 \
  -a firmware.dfu \
  -D "$dfu_image"
```

If more than one radio is present, do not run an ambiguous command. Disconnect
the others or select the intended USB path using `dfu-util -p` after checking
`dfu-util -l` and the corresponding sysfs serial.

Never select `boot.dfu` or `uboot-env.dfu` during a routine Pluto+ update.

## Method 3: volatile RAM boot for testing

RAM boot runs a candidate without changing QSPI. A power cycle returns the
radio to its persistently installed firmware.

```bash
ssh root@192.168.2.1 '/usr/sbin/device_reboot ram'
dfu-util -l -d 0456:b673,0456:b674
sudo dfu-util -R \
  -d 0456:b673,0456:b674 \
  -a firmware.dfu \
  -D "$dfu_image"
```

The repository also provides `download_and_test.sh` and the `dfu-ram` Make
target for a locally built `build/pluto.dfu`. They perform this same volatile
sequence.

An important trap: while a RAM image is active, `/opt/VERSIONS` describes that
RAM image—not the image stored in QSPI. Reboot or power-cycle back to QSPI
before deciding whether a persistent update can be skipped.

## Verify a persistent installation

A successful transfer is not proof of persistence. Remove power completely,
reconnect the radio, and then read the version from the cold-booted system:

```bash
ssh root@192.168.2.1 'grep "^device-fw " /opt/VERSIONS'
```

Or query it through libiio, selecting the URI for the intended radio:

```bash
iio_info -s
iio_attr -T 2000 -u 'usb:BUS.DEVICE.5' -C fw_version
```

For v5, the expected value is:

```text
v0.38-plutoplus-spf-libiio-metadata-v5
```

Production verification should additionally check the hardware serial, gadget
build identity, expected IIO devices, and an RX smoke capture. A soft reboot is
insufficient proof after a RAM-boot campaign; use a full power cycle.

## Flash a locally built image

See [BUILD.md](BUILD.md) for the reproducible build requirements. The useful
firmware outputs are:

```text
build/pluto.dfu    DFU RAM or firmware-partition image
build/pluto.frm    mass-storage firmware-partition image
```

Build only the firmware payload when that is all you need:

```bash
make build/pluto.dfu
make build/pluto.frm
```

Use the RAM method first. Do not persist a new local build until its source
graph, FPGA timing, functional tests, and target hardware gates have passed.

## GitHub Actions build artifacts

The trusted `main` workflow builds a deployment bundle containing the DFU,
XSA, root filesystem, checksums, validation reports, and provenance. Actions
artifacts are retained for 90 days and can be downloaded from the relevant run:

```bash
gh run list --repo misko/plutosdr-fw \
  --workflow 'Kalman main firmware build' --limit 10
gh run view RUN_ID --repo misko/plutosdr-fw
gh run download RUN_ID --repo misko/plutosdr-fw --dir /tmp/plutosdr-ci
```

A successful `main` build is offline-validated but hardware-untested. Treat it
as RAM-only until it is promoted into an explicitly hardware-qualified GitHub
release. Release assets are the permanent, operator-facing artifacts.

## Full ZIP, bootloader DFU, and JTAG

These paths exist for upstream board provisioning and recovery, but are not
normal Pluto+ firmware-update methods:

- A full `*-fw-*.zip` may contain `boot.frm` and update FSBL/U-Boot as well as
  the firmware payload. Do not use it for routine Pluto+ updates.
- `boot.frm`, `boot.dfu`, and `uboot-env.dfu` modify boot-critical partitions.
  Do not use them unless following a board-specific recovery procedure with a
  known-compatible bootloader.
- `scripts/run.tcl`, `scripts/run-xsdb.tcl`, and the `jtag-bootstrap` target are
  for initial flash programming or recovery by experienced operators. They are
  intentionally outside the release-install procedure.
- Directly writing `/dev/mtdblock*` over SSH bypasses updater validation and is
  not a supported installation path.

If a firmware-only update fails but the bootloader still enters DFU, recover by
reinstalling a known-good `pluto.dfu` to `firmware.dfu`. Bootloader damage may
require the Pluto+ recovery jumper and JTAG/DFU board-recovery procedure.
