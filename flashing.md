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

## Install the host-side libiio extension

Flashing v5 installs the radio-side libiio/iiOD 0.25 implementation as part of
the firmware. It does **not** install anything on the computer that controls
the radio.

The normal libiio buffer API and IQ byte layout remain compatible with an
unmodified host. Reading v5's capture index, sample sequence/time, gain
history, gain endpoints, and RSSI endpoints requires both parts of the matching
SPF host extension:

1. the patched native `libiio` C library; and
2. the patched Python `pylibiio` binding containing `iio.MetadataBuffer`.

Installing only `pylibiio` from PyPI is insufficient because it does not
contain the modified C protocol implementation.

### Supported host versions

Use 0.25 unless an existing application specifically requires 0.26.

| Host line | Immutable source tag | Commit | Use |
|---|---|---|---|
| 0.25 | `spf-frame-metadata-source/v0.25-final-v3` | `c26258bfa33098c2b215e19cf85d448e89499b1a` | Recommended; matches the radio's libiio line |
| 0.26 | `spf-frame-metadata-source/v0.26-final-v3` | `d5695c3eaa9cec99cc6f7b2c91565555044b907a` | Supported host alternative |

Both lines were hardware-qualified with v5 over USB and standard libiio
`ip:`/TCP. Do not install an arbitrary development branch.

### Recommended package installation

SPF's package workflow produces a native Debian 12 package and a Python wheel:

- `arm64` supports Pi 4 and Pi 5 running 64-bit Debian 12 or Raspberry Pi OS
  12;
- `amd64` supports standard x86-64 Debian 12 hosts; and
- the `py3-none-any` wheel is shared by both architectures.

First check whether an immutable `libiio-artifacts-*` release has been
published in `misko/spf`:

```bash
gh release list --repo misko/spf --limit 50
```

If a release for the desired line exists, download the two native packages,
wheel, and checksum file from that one release. The installer chooses the
local architecture, while `SHA256SUMS` verifies the complete release set:

```bash
host_release=libiio-artifacts-v0.25-spfmeta3.1  # replace with listed tag
host_bundle="$(mktemp -d /tmp/spf-libiio.XXXXXX)"

gh release download "$host_release" \
  --repo misko/spf \
  --pattern 'spf-libiio_*.deb' \
  --pattern 'pylibiio-*.whl' \
  --pattern 'SHA256SUMS' \
  --dir "$host_bundle"

git clone https://github.com/misko/spf.git
cd spf
python3 -m venv ~/spf-virtualenv
~/spf-virtualenv/bin/python -m pip install --upgrade pip
~/spf-virtualenv/bin/python -m pip install -e .

./install_spf_libiio_artifacts.sh \
  --bundle "$host_bundle" \
  --python ~/spf-virtualenv/bin/python
```

Do not combine a `.deb`, wheel, and checksum file from different releases. If
no matching `libiio-artifacts-*` release is listed, use the source-build method
below; a successful CI build artifact is not automatically a published host
release.

### Source-build installation

The SPF installer clones and verifies the immutable source tag, builds the
local, USB, and network backends, installs the native library and tools under
`/usr/local`, runs `ldconfig`, and installs the generated Python binding into
the selected environment.

Install build dependencies:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  git cmake make pkg-config flex bison python3-dev python3-venv \
  libxml2-dev libaio-dev libusb-1.0-0-dev
```

Install SPF first, then install the patched binding last so a later installation
of unmodified PyPI `pylibiio` cannot replace it:

```bash
git clone https://github.com/misko/spf.git
cd spf
python3 -m venv ~/spf-virtualenv
~/spf-virtualenv/bin/python -m pip install --upgrade pip
~/spf-virtualenv/bin/python -m pip install -e .

./install_spf_libiio.sh \
  --series 0.25 \
  --python ~/spf-virtualenv/bin/python
```

For the supported 0.26 host line, change only the series:

```bash
./install_spf_libiio.sh \
  --series 0.26 \
  --python ~/spf-virtualenv/bin/python
```

Only one series should be installed in `/usr/local` at a time. Advanced
side-by-side testing can use `--prefix /opt/libiio-spf-0.25`, but every process
then needs that prefix's `lib` or `lib64` directory in `LD_LIBRARY_PATH`.

The authoritative host installation guide and packaging details live in
[`misko/spf`](https://github.com/misko/spf/blob/main/docs/libiio_frame_metadata_install.md).

### Verify the host and radio together

For the recommended 0.25 line:

```bash
~/spf-virtualenv/bin/python - <<'PY'
import iio

print("binding:", iio.__file__)
print("version:", iio.version)
print("MetadataBuffer:", hasattr(iio, "MetadataBuffer"))
assert iio.version == (0, 25, "c26258b")
assert hasattr(iio, "MetadataBuffer")
PY

/usr/local/bin/iio_info --version
/usr/local/bin/iio_info -S
```

For 0.26, the expected tuple is `(0, 26, "d5695c3")`.

Finally, select the intended radio URI and verify that v5 advertises the
metadata capability. Examples:

```bash
# Direct USB: obtain the exact URI from iio_info -S.
/usr/local/bin/iio_attr -T 2000 \
  -u 'usb:BUS.DEVICE.5' -C iio,buffer-metadata

# Standard libiio network/TCP transport.
/usr/local/bin/iio_attr -T 2000 \
  -u 'ip:RADIO_ADDRESS' -C iio,buffer-metadata
```

The value must be `1`. An older or upstream radio can still use ordinary
buffers, but it cannot provide v5 `MetadataBuffer` records. Run host commands
from the selected virtual environment, and avoid a global `PYTHONPATH` pointing
at a libiio build directory; that can silently mix the Python binding with a
different native library.

## Method 1: persistent update through USB mass storage

This is the preferred normal Pluto+ method. It uses `pluto.frm`, which the
running radio validates before writing only the `mtd3` firmware partition.

### Obtain `pluto.frm`

A local full build produces `build/pluto.frm`. Tandem AGC v8 releases publish
the attested `pluto.frm` directly; use that release asset for this method.
Older DFU-only release assets can be converted without rebuilding because
`pluto.dfu` and `pluto.frm` wrap the same FIT image:

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

First record the current boot identity, then request SPI-flash mode from the
running radio:

```bash
pre_boot_id="$(ssh root@192.168.2.1 \
  'cat /proc/sys/kernel/random/boot_id')"
test -n "$pre_boot_id"
ssh root@192.168.2.1 '/usr/sbin/device_reboot sf'
```

Wait for DFU enumeration and inspect every alternate:

```bash
dfu-util -l -d 0456:b673,0456:b674
```

With exactly one intended radio connected, write only `firmware.dfu` and reset:

```bash
sudo dfu-util \
  -d 0456:b673,0456:b674 \
  -a firmware.dfu \
  -D "$dfu_image"
sudo dfu-util \
  -d 0456:b673,0456:b674 \
  -a firmware.dfu \
  -e
```

Here DFU detach (`-e`) exits DFU mode after `firmware.dfu` has written the
persistent firmware partition; it is not a RAM boot. Do not substitute `-R`
for this step. After the radio re-enumerates, require a new boot identity and
the exact installed release identity:

```bash
expected_firmware_version='REPLACE_WITH_EXACT_RELEASE_VERSION'
post_boot_id="$(ssh root@192.168.2.1 \
  'cat /proc/sys/kernel/random/boot_id')"
installed_firmware_version="$(ssh root@192.168.2.1 \
  "awk '\$1 == \"device-fw\" {print \$2; exit}' /opt/VERSIONS")"
test -n "$post_boot_id"
test "$post_boot_id" != "$pre_boot_id"
test "$installed_firmware_version" = "$expected_firmware_version"
```

If more than one radio is present, do not run an ambiguous command. Disconnect
the others or select the intended USB path using `dfu-util -p` after checking
`dfu-util -l` and the corresponding sysfs serial.

Never select `boot.dfu` or `uboot-env.dfu` during a routine Pluto+ update.

## Method 3: volatile RAM boot for testing

RAM boot runs a candidate without changing QSPI. A power cycle returns the
radio to its persistently installed firmware.

Do not use a raw `dfu-util -R` recipe for this transition. The RC4 hardware
record found that USB reset returned a tested Pluto+ to its persistent image,
while download followed by DFU detach entered the RAM image. Because the old
guide and helper disagreed with that result, raw RAM boot is quarantined until
the transition has a reviewed, exact-serial proof.

Use the guarded deployer. Its default mode is an offline plan: it validates the
exact candidate index, source manifest, DFU/FIT bytes, harness and evidence
inventories, requested serial, receipt namespace, and optional captured USB
inventory without opening USB or running SSH/DFU.
`candidate_archive` below is the directory containing the candidate index; its
serial-named receipt directory must already exist and the receipt file itself
must be absent.

```bash
scripts/deploy_tandem_agc_ram_hardware.sh \
  --radio-serial "$serial" \
  --artifact "$absolute_dfu" \
  --artifact-sha256 "$dfu_sha256" \
  --artifact-index "$absolute_candidate_index" \
  --artifact-index-sha256 "$candidate_index_sha256" \
  --expected-current-firmware "$current_device_fw" \
  --receipt "$candidate_archive/$serial/ram-boot-receipt.json" \
  --known-hosts "$absolute_known_hosts" \
  --known-hosts-sha256 "$known_hosts_sha256"
```

If the `-R` versus `-e` behavior still needs to be reproduced for a radio, add
`--sequence-experiment-plan`. That output is deliberately non-executable and
contains the isolated-radio preconditions and required observations, but no
DFU command.

Actual execution additionally requires a reviewed mode-`0600` transition proof
and its hash, an owned mode-`0600` known-hosts file, an exact serial-bound
confirmation, and `--execute`:

```bash
scripts/deploy_tandem_agc_ram_hardware.sh \
  --radio-serial "$serial" \
  --artifact "$absolute_dfu" \
  --artifact-sha256 "$dfu_sha256" \
  --artifact-index "$absolute_candidate_index" \
  --artifact-index-sha256 "$candidate_index_sha256" \
  --expected-current-firmware "$current_device_fw" \
  --receipt "$candidate_archive/$serial/ram-boot-receipt.json" \
  --known-hosts "$absolute_known_hosts" \
  --known-hosts-sha256 "$known_hosts_sha256" \
  --transition-proof "$absolute_transition_proof" \
  --transition-proof-sha256 "$transition_proof_sha256" \
  --operator-confirmation "RAM BOOT $serial" \
  --execute
```

The executor permits only `firmware.dfu` download on the serial's unique USB
topology followed by DFU detach. It rejects USB reset, SPI-flash/QSPI, boot and
environment alternates, full ZIP/FRM files, and raw MTD targets. It publishes a
passing receipt only after the same serial returns with a new boot ID, the
candidate firmware identity, and verified TX/DDS/DAC/tandem safe state.
Before and after the RAM transition it also reads SHA-256 over the exact
`qspi-linux` `/dev/mtdblock3` partition. The receipt's `persistent_flash`
record must identify the same partition/size and equal digests; any change
blocks receipt publication.

`download_and_test.sh` is now quarantined and points to this guarded entry
point. The legacy `make dfu-ram` target is not an authorized candidate or
release procedure because it cannot carry the required serial, artifact-index,
proof, and receipt bindings.

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
