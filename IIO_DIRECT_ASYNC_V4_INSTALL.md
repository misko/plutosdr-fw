# Direct-async IQ v4 installation and compatibility

This is the normative installation guide for full release
`v0.49-plutoplus-spf-iq-direct-async-v4`. Pluto+ bootloader rules in
[`flashing.md`](flashing.md) still apply. Install only with Pluto Plus Utils
(PPU); do not copy a full firmware ZIP, `boot.frm`, `boot.dfu`, or
`uboot-env.dfu` to a Pluto+.

## Required component set

The radio, native host library, generated Python binding, and PPU must be a
matched set. Stock libiio or a PyPI-only `pylibiio` cannot attest exact DMA
admission.

| Layer | Required immutable version |
| --- | --- |
| firmware/release | `v0.49-plutoplus-spf-iq-direct-async-v4` |
| protected firmware source | `bc00edb8c340dd4f9b04361398cbd2c8edcc9cae`; tag `iq-direct-async-v4-source/fw-v1` |
| trusted build | GitHub Actions run `33535095284` |
| Buildroot/rootfs | `2e146948a52eaf7c7f675c5e6ac746eeff4aacac`; tag `iq-direct-async-v4-source/buildroot-v1` |
| radio and host libiio | 0.25 at `5cb2389719d46d12463daa0371d1fda19eb25fa7`; tag `iq-direct-async-v4-source/libiio-v1` |
| libiio source archive | SHA-256 `1f38c05259c846b9f6ef327eb8feab293564a615d940336a8b4491c79e403212` |
| Linux/CMA | `7176508dd84bde78c62d8790bbd17957fdda12d7`; tag `iq-direct-async-v4-source/linux-v1` |
| metadata provider | ABI 3 / `RadioMetadataV6`, `3294365ff44da26b261be4a2ccb241b7896d23ad` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; `ddr-burst-v1-rc4-source/hdl-v1` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`; `gain-series-v4-rc2-source/u-boot-xlnx` |
| PPU host release | tag `iq-direct-async-v4-host-v1`, main commit `ec2b3ee85721011c0ffcb1619c85300672413aba` |
| PPU implementation/profile | `35a827c0f8d6255fa29646c75ea191492e403b69` |
| Vivado | 2022.2 build 3671981 |
| ARM toolchain | Linaro GCC 7.3-2018.05, GCC 7.3.1 |

The packaged `/opt/VERSIONS` must be exactly:

```text
device-fw v0.49-plutoplus-spf-iq-direct-async-v4
hdl ddr-burst-v1-rc4-source/hdl-v1
buildroot iq-direct-async-v4-source/buildroot-v1
linux iq-direct-async-v4-source/linux-v1
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
```

iiOD is started automatically as:

```text
/usr/sbin/iiod -D -n 3 -F /dev/iio_ffs --rw-cpu-affinity 1
```

Do not launch a second iiOD. `--rw-cpu-affinity 1` is the long-form packaged
equivalent of the historical `iiod -r 1` shorthand.

## Download and verify

```bash
release_dir="$(mktemp -d /tmp/pluto-direct-async-v4.XXXXXX)"
chmod 0700 "$release_dir"
gh release download v0.49-plutoplus-spf-iq-direct-async-v4 \
  --repo misko/plutosdr-fw --dir "$release_dir"
(
  cd "$release_dir"
  sha256sum -c iq-direct-async-v4-SHA256SUMS
)
```

| Object | Bytes | SHA-256 |
| --- | ---: | --- |
| `plutoplus-spf-iq-direct-async-v4-bc00edb8c340.tar.gz` | 134,221,620 | `ef3cace7a72c06f4f617bd7bd9a37fb4a68738c14e8d7beb8aa48969809299a7` |
| `plutoplus-spf-iq-direct-async-v4-bc00edb8c340-pluto.dfu` | 12,825,831 | `f45524f4765d5743144703ff6f4541084ff1ab9b1ce20a77f3f6fa820a1f84b6` |
| `plutoplus-spf-iq-direct-async-v4-bc00edb8c340-pluto.frm` | 12,825,848 | `290d1447657a0feb89340767fe26fa85bb3eaa42e27f90ed5acecfbc3a5cda73` |
| DFU/FRM FIT body | 12,825,815 | `77f899610548d486aab2c83c4dc7170532d470b115d2bd0e8fc43e72b3bfca67` |
| `iq-direct-async-v4-source.yaml` | 2,542 | `6986c9c8975d801b8e99582843e87ea8b146648b08f9cab38c58c28747479476` |

If using the tar bundle, extract it into another private directory and require
both internal checksum inventories to pass:

```bash
bundle_dir="$(mktemp -d /tmp/pluto-direct-async-v4-bundle.XXXXXX)"
tar -xzf "$release_dir/plutoplus-spf-iq-direct-async-v4-bc00edb8c340.tar.gz" \
  -C "$bundle_dir"
(
  cd "$bundle_dir"
  sha256sum -c SHA256SUMS
  sha256sum -c PAYLOAD_SHA256SUMS
)
```

Stop if any name, size, checksum, or version differs.

## Install the matched host runtime

```bash
git clone https://github.com/misko/pluto-plus-utils.git
cd pluto-plus-utils
git checkout ec2b3ee85721011c0ffcb1619c85300672413aba
uv sync --extra hardware

scripts/install_native_libiio.sh \
  --uv-bin /ABSOLUTE/PATH/TO/NON-SYMLINK/uv \
  --metadata-abi 3 \
  --python "$PWD/.venv/bin/python" \
  --prefix "$PWD/.venv"

uv run pluto environment --format json
```

The environment result must be healthy, list local/XML/IP/USB backends, and
report `libiio 0.25 (5cb2389)` from this checkout's `.venv/lib`. Do not install
another `pylibiio` afterward. PPU verifies a content-bound runtime receipt and
rejects the older v0.48 `0d32308` tree even though both advertise metadata ABI
3.

## Runtime contract

Before direct capture, require:

| Context item | Required value |
| --- | --- |
| metadata | `iio,buffer-metadata=3` |
| direct async | `iio,buffer-direct-async=1` |
| authoritative admission | `iio,buffer-direct-async-exact-kernel-queue=1` |
| RAM extension | `iio,buffer-direct-async-ring=1` |
| overrun policies | `drop-backlog,preserve-backlog` |
| default policy | `drop-backlog` |
| RAM limit/modes | `200000000`; `finite,continuous` |
| host/radio libiio | exact `5cb2389` tree on both sides |

The recommended exact 200 MB DMA geometry is 1,000,000 IQ samples/frame and
50 kernel buffers. This is 200,000,000 IQ bytes and fifty exact four-MiB CMA
mappings after the ABI-3 prefix. PPU reports both `requested` and `allocated`;
they must read `50/50`. Do not substitute 47 × 1,048,576: the metadata prefix
and one-MiB alignment make that shape larger than its IQ-only arithmetic, and
v0.49 correctly fails it with `ENOSPC` if the exact queue cannot be admitted.

## Guarded persistent installation

Inventory and identify one exact attached radio:

```bash
uv run pluto radio inventory --network --format json
install -d -m 0700 /ABSOLUTE/PRIVATE/PATH/flash-receipts
```

Plan first:

```bash
uv run pluto firmware flash \
  "$release_dir/plutoplus-spf-iq-direct-async-v4-bc00edb8c340-pluto.dfu" \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v4-release-persistent-promotion \
  --receipt-directory /ABSOLUTE/PRIVATE/PATH/flash-receipts
```

Require the exact serial/path, DFU/FIT hashes above, target v0.49, metadata ABI
3, and `will_write: false`. Execute only with the exact phrase PPU prints:

```bash
uv run pluto firmware flash \
  "$release_dir/plutoplus-spf-iq-direct-async-v4-bc00edb8c340-pluto.dfu" \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v4-release-persistent-promotion \
  --receipt-directory /ABSOLUTE/PRIVATE/PATH/flash-receipts \
  --execute --confirm 'FLASH EXACT_SERIAL'
```

Keep the receipt. Never retry an uncertain post-eject attempt; reconcile it
read-only.

## SSH keys after reboot and QSPI reconciliation

Pluto generates a new SSH key after each reboot. Re-enroll a new absent,
serial-specific file through PPU; never disable host-key checking:

```bash
uv run pluto firmware enroll-usb-ssh EXACT_SERIAL \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --password-file /ABSOLUTE/PRIVATE/PATH/radio.password \
  --isolate-usb-route \
  --isolation-confirm 'ISOLATE USB SSH EXACT_INTERFACE'
```

Review, then repeat with
`--execute --confirm 'TRUST USB SSH EXACT_SERIAL'`. Reconcile the flash receipt:

```bash
uv run pluto firmware reconcile-local RECEIPT_ID \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v4-release-persistent-promotion \
  --ssh-known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --ssh-password-file /ABSOLUTE/PRIVATE/PATH/radio.password \
  --receipt-directory /ABSOLUTE/PRIVATE/PATH/flash-receipts \
  --isolate-usb-route \
  --isolation-confirm 'ISOLATE USB SSH EXACT_INTERFACE'
```

The result must be `reconciled_verified`, TX safe, and show FIT
`77f899…bfca67` read from `/dev/mtd3`.

## PPU-only speed and exact-admission check

```bash
uv run pluto radio direct-async-ladder RADIO_IP \
  --transport ip --expect-serial EXACT_SERIAL \
  --rates 25M --durations 3,10 \
  --channels rx0 --samples 1000000 --kernel-buffers 50 \
  --ram-ring-slots 0 --drop-backlog-on-overrun \
  --tandem-mode hold --iq-decoder raw-complex64 --format json
```

The top-level result must report `allocated_kernel_buffers: 50`. A 25 MS/s
source offers 100 MB/s, so long captures may have counter-reported overruns;
that does not shorten the finite request or re-arm the DMA session. For the
retained 40-second default/200 MB comparison and PNGs, see the PPU report
`reports/2026-09-01-iq-direct-async-v4-exact-200m/`.

## Rollback

Retain the v0.48 DFU and PPU profile
`iq-direct-async-v3-release-persistent-promotion` until v0.49 post-install
checks pass. Rollback uses the same PPU flash/reconcile procedure and only the
exact hardware-qualified v0.48 bytes; do not mix its `0d32308` host runtime
with a v0.49 radio.
