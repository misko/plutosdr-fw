# Direct-async IQ v3 installation and compatibility

This is the normative host-runtime, installation, verification, and acceptance
guide for full release `v0.48-plutoplus-spf-iq-direct-async-v3`. It supplements
[`flashing.md`](flashing.md); every Pluto+ bootloader safety rule there still
applies.

## Release status

Protected run
[33481347855](https://github.com/misko/plutosdr-fw/actions/runs/33481347855)
built exact merged `main` commit
`e3078376a6e1a8c6ea841dc69966b3880e020c70`. The exact bytes passed the routed
design gate, four-radio RAM boot and smoke gate, long-session issue #72
recovery, physical-1-GbE 70 MB/s+ tests, RAM/drop policy matrix, guarded
persistent installation, QSPI FIT readback, guarded reboot, repeated readback,
TX safety, and a post-reboot direct capture.

This release is authorized for persistent installation through Pluto Plus
Utils (PPU) profile `iq-direct-async-v3-release-persistent-promotion`. The
separate `iq-direct-async-v3-release-ram` profile remains volatile-only and can
never imply permission to write QSPI.

Full evidence is in
[`RELEASE_IQ_DIRECT_ASYNC_V3.md`](RELEASE_IQ_DIRECT_ASYNC_V3.md). The release
is persistent-reboot qualified. It does not claim an all-power-removed cold
boot; v0.47 remains the independently cold-boot-qualified rollback release.

## Exact matched component set

Substituting stock libiio, an unmodified PyPI-only `pylibiio`, a different
firmware asset, or an older PPU checkout is unsupported.

| Layer | Required version, ref, or commit |
| --- | --- |
| firmware identity | `v0.48-plutoplus-spf-iq-direct-async-v3` |
| protected firmware source | `e3078376a6e1a8c6ea841dc69966b3880e020c70` |
| recovery implementation | `322b67f9580d215c1f8362735c877f7c5ee2f89e`; tag `iq-direct-async-v3-source/fw-v1` |
| Buildroot | `1c337a0b8d8126c9d1ed785607bc5ea52e7fed22`; tag `iq-direct-async-v3-source/buildroot-v1` |
| radio and host libiio | 0.25 at `0d323080a0a1067da8c7adbadfd03ee186a40ec2`; tag `iq-direct-async-v3-source/libiio-v1` |
| libiio archive | SHA-256 `66ccc7230ebe75c477c4dfc147aa86289c3f896c0a0d6b3b6c964e152d89c266` |
| metadata provider | ABI 3 / `RadioMetadataV6` at `3294365ff44da26b261be4a2ccb241b7896d23ad` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; `ddr-burst-v1-rc4-source/hdl-v1` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7`; `ddr-burst-v1-rc3-source/linux-v1` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`; `gain-series-v4-rc2-source/u-boot-xlnx` |
| Pluto Plus Utils | package 0.1.0, Python 3.11+; `main` at `246ead24fd9c9052a978340a0905408afcb3b8aa` or later |
| PPU v3 profiles | RAM `1287462dca2dfd6d06ca192e3c8c37eabb64181a`; persistent `0a21ce250b44006a7880ae35dc30d11673fd2180` |
| Vivado | 2022.2 build 3671981 |
| ARM toolchain | Linaro GCC 7.3-2018.05, GCC 7.3.1 |

The packaged `/opt/VERSIONS` must be exactly:

```text
device-fw v0.48-plutoplus-spf-iq-direct-async-v3
hdl ddr-burst-v1-rc4-source/hdl-v1
buildroot iq-direct-async-v3-source/buildroot-v1
linux ddr-burst-v1-rc3-source/linux-v1
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
```

The radio-side iiOD is supervised with R/W-worker affinity on CPU 1. That is
the packaged equivalent of the historical prototype command `iiod -r 1`; an
operator does not launch another iiOD process after boot.

## Download and verify

Create a new private directory and download only the named release:

```bash
release_dir="$(mktemp -d /tmp/pluto-direct-async-v3.XXXXXX)"
chmod 0700 "$release_dir"
gh release download v0.48-plutoplus-spf-iq-direct-async-v3 \
  --repo misko/plutosdr-fw --dir "$release_dir"
(
  cd "$release_dir"
  sha256sum -c iq-direct-async-v3-SHA256SUMS
)
```

The release checksum inventory is:

| Object | Bytes | SHA-256 |
| --- | ---: | --- |
| `plutoplus-spf-iq-direct-async-v3-e3078376a6e1.tar.gz` | 134,226,947 | `4839ef4e97b2c7d2f56363219184ec48db8fbdab67f1b6d8388f531ca79836fd` |
| `plutoplus-spf-iq-direct-async-v3-e3078376a6e1-pluto.dfu` | 12,825,587 | `cc87c36a3aad609a64b45f4a02eecf916b99a3099fa523eed1bf4526ed98995a` |
| `plutoplus-spf-iq-direct-async-v3-e3078376a6e1-pluto.frm` | 12,825,604 | `98341f4d5e926684c092b2addc283852a56f999ba57b4e89ea30a306785e81e0` |
| `iq-direct-async-v3-source.yaml` | 2,596 | `8f9b4aa76958a63aee3927ca7a4d57bbec18b3c9afacca4dbe46dd64a7ce9b22` |
| `iq-direct-async-v3.yaml` | release manifest | `512605dfa998d354c1de3ecc5057ce8e22ce20d70d99a42dcd950cf0b208ea5d` |
| DFU/FRM FIT body | 12,825,571 | `db777ac93d5c6f0be0cf2799808a4d06fe39264ee1e99e76001509394d75f1df` |

If using the tar bundle, extract it into another private directory and require
both internal inventories to pass:

```bash
bundle_dir="$(mktemp -d /tmp/pluto-direct-async-v3-bundle.XXXXXX)"
tar -xzf "$release_dir/plutoplus-spf-iq-direct-async-v3-e3078376a6e1.tar.gz" \
  -C "$bundle_dir"
(
  cd "$bundle_dir"
  sha256sum -c SHA256SUMS
  sha256sum -c PAYLOAD_SHA256SUMS
)
```

Stop if any checksum, size, asset name, or version differs.

## Install the matched host runtime

Install PPU from the required `main` commit or later. Its installer builds the
native library and generated Python binding from the same immutable libiio
tree and writes a content-bound runtime receipt:

```bash
git clone https://github.com/misko/pluto-plus-utils.git
cd pluto-plus-utils
git checkout 246ead24fd9c9052a978340a0905408afcb3b8aa
uv sync --extra hardware

scripts/install_native_libiio.sh \
  --uv-bin /ABSOLUTE/PATH/TO/NON-SYMLINK/uv \
  --metadata-abi 3 \
  --python "$PWD/.venv/bin/python" \
  --prefix "$PWD/.venv"
```

Do not install `pylibiio` from PyPI afterward and do not mix the native
library, binding, or receipt from different commits. Verify:

```bash
uv run pluto environment --format json

LD_LIBRARY_PATH="$PWD/.venv/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  .venv/bin/python - <<'PY'
import inspect
import iio

assert iio.version == (0, 25, "0d32308")
parameters = tuple(inspect.signature(iio.MetadataBuffer.__init__).parameters)
assert "direct_async_frames" in parameters
assert "drop_backlog_on_overrun" in parameters
print(iio.__file__, iio.version)
PY
```

`pluto environment` must report native libiio `0.25 (0d32308)` and healthy
local/XML/IP/USB backends. PPU rejects a different loaded library even when its
version text looks similar.

## Runtime contract

Require every item below before starting a direct capture:

| Contract item | Required value |
| --- | --- |
| metadata ABI | `iio,buffer-metadata=3` |
| direct mode | `iio,buffer-direct-async=1` |
| RAM extension | `iio,buffer-direct-async-ring=1` |
| overrun modes | `iio,buffer-direct-async-overrun-policies=drop-backlog,preserve-backlog` |
| default overrun mode | `iio,buffer-direct-async-default-overrun-policy=drop-backlog` |
| RAM capacity | `iio,buffer-ddr-ring-max-iq-bytes=200000000` |
| RAM modes | `iio,buffer-ddr-ring-modes=finite,continuous` |
| topology | exactly one selected receiver |
| finite target | 1 through 4,096 frames in one request |
| incompatible mode | `ddr_burst_bytes=0` |
| host/radio libiio | exact `0d32308` tree on both sides |

RAM slots extend the same ordered descriptor FIFO. With RAM disabled, direct
mode allocates and copies no RAM-ring IQ. A frame already entering TCP is never
retired by either overrun policy. Drop-backlog is the default because it
minimizes separate timeline breaks and stale-data latency after sustained
pressure; use preserve when ordered delivery of the backlog is preferred.

## Guarded local-USB persistent installation

Pluto+ installation updates only the `qspi-linux` firmware partition. Never
use a full firmware ZIP, `boot.frm`, `boot.dfu`, or `uboot-env.dfu` for this
operation.

Inventory all attached radios and record the exact serial, sysfs path, and host
interface:

```bash
uv run pluto radio inventory --format json
```

Stop every process using the selected radio. Create a private receipt directory
and run the flash without `--execute`:

```bash
install -d -m 0700 /ABSOLUTE/PRIVATE/PATH/flash-receipts
uv run pluto firmware flash \
  "$release_dir/plutoplus-spf-iq-direct-async-v3-e3078376a6e1-pluto.dfu" \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v3-release-persistent-promotion \
  --receipt-directory /ABSOLUTE/PRIVATE/PATH/flash-receipts
```

The plan must show the intended serial/path and all of:

- DFU SHA `cc87c36a…9995a`;
- FIT SHA `db777ac9…5f1df`, size 12,825,571;
- metadata ABI 3 and tandem capability;
- target `v0.48-plutoplus-spf-iq-direct-async-v3`; and
- profile `iq-direct-async-v3-release-persistent-promotion`.

If any field differs, stop. Execute only with the exact serial phrase printed
by the plan:

```bash
uv run pluto firmware flash \
  "$release_dir/plutoplus-spf-iq-direct-async-v3-e3078376a6e1-pluto.dfu" \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v3-release-persistent-promotion \
  --receipt-directory /ABSOLUTE/PRIVATE/PATH/flash-receipts \
  --execute --confirm 'FLASH EXACT_SERIAL'
```

Keep the durable receipt. Do not retry an uncertain operation after updater
dispatch or media eject; reconcile that receipt read-only.

### Ephemeral SSH key handling

The radio generates a new SSH host key after every reboot. This is expected.
Do not disable host-key checking, reuse an old key, or install a fleet-wide
static exception. PPU first attests the exact USB path and IIOD serial, then
pins the current key into a new serial-specific file.

Use a new absent path and include the exact interface isolation phrase:

```bash
uv run pluto firmware enroll-usb-ssh EXACT_SERIAL \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --password-file /ABSOLUTE/PRIVATE/PATH/radio.password \
  --ssh-host 192.168.2.1 \
  --isolate-usb-route \
  --isolation-confirm 'ISOLATE USB SSH EXACT_INTERFACE'
```

Review the dry-run identity, then repeat with:

```text
--execute --confirm 'TRUST USB SSH EXACT_SERIAL'
```

PPU temporarily removes competing identical Pluto routes, verifies the selected
route, performs the bounded action, and restores the host network in a `finally`
path. Re-enroll into another new file after every reboot.

Verify active identity, TX-safe state, and the exact FIT length/hash in
`/dev/mtd3`:

```bash
uv run pluto firmware reconcile-local RECEIPT_ID \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v3-release-persistent-promotion \
  --ssh-known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --ssh-password-file /ABSOLUTE/PRIVATE/PATH/radio.password \
  --ssh-host 192.168.2.1 \
  --receipt-directory /ABSOLUTE/PRIVATE/PATH/flash-receipts \
  --isolate-usb-route \
  --isolation-confirm 'ISOLATE USB SSH EXACT_INTERFACE'
```

Success is `reconciled_verified` with FIT
`db777ac93d5c6f0be0cf2799808a4d06fe39264ee1e99e76001509394d75f1df`.

## Guarded network-only installation

Network flashing is supported only through PPU's serial-attested LAN workflow.
First bind the literal private address to the exact IIOD serial and enroll the
current ephemeral key:

```bash
uv run pluto firmware enroll-lan-ssh EXACT_SERIAL \
  --host 192.168.1.20 \
  --known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.lan.known_hosts \
  --profile iq-direct-async-v3-release \
  --execute --use-default-password \
  --confirm 'TRUST LAN SSH EXACT_SERIAL 192.168.1.20'
```

Run the exact flash once without `--execute`:

```bash
uv run pluto firmware flash-lan \
  "$release_dir/plutoplus-spf-iq-direct-async-v3-e3078376a6e1-pluto.dfu" \
  --serial EXACT_SERIAL --host 192.168.1.20 \
  --profile iq-direct-async-v3-release-persistent-promotion \
  --ssh-known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.lan.known_hosts \
  --ssh-password-file /ABSOLUTE/PRIVATE/PATH/radio.password
```

Review serial, address, prior/target firmware, hashes, profile, and TX-safe
preflight. Execute with the exact phrase printed by PPU:

```text
--execute --confirm 'FLASH LAN EXACT_SERIAL 192.168.1.20'
```

After updater dispatch, PPU waits for IIOD—not the old SSH key—to return,
requires the exact serial/v0.48 capabilities, and only then rotates the pinned
key. A post-dispatch uncertainty must be reconciled, never blindly retried.

## PPU-only acceptance ladders

On a newly flashed physical-1-GbE radio, the exact 70 MB/s gate is:

```bash
install -d -m 0700 /ABSOLUTE/PRIVATE/PATH/reports
uv run pluto radio direct-async-ladder RADIO_IP \
  --transport ip --expect-serial EXACT_SERIAL \
  --rates 25M --durations 3,10,60 \
  --channels rx0 --samples 1048576 \
  --kernel-buffers 47 --ram-ring-slots 0 \
  --drop-backlog-on-overrun \
  --tandem-mode hold --iq-decoder pyadi \
  --format json \
  --report /ABSOLUTE/PRIVATE/PATH/reports/25m-k47-drop.json
```

The final release produced 73.57/74.09/72.82 MB/s at 3/10/60 seconds. Every
cell must return its exact requested frame count, one capture segment, no
terminal failures, and restored settings. Counter-observed gaps are valid
measured evidence at 25 MS/s; `passed=false` for a cell means it was not
gapless, not that the command failed to complete.

Run the RAM extension matrix with:

```bash
uv run pluto radio direct-async-ladder RADIO_IP \
  --transport ip --expect-serial EXACT_SERIAL \
  --rates 5M,10M,15M,20M,25M --durations 3,20 \
  --channels rx0 --samples 1048576 \
  --kernel-buffers 11 --ram-ring-slots 32 \
  --drop-backlog-on-overrun \
  --tandem-mode hold --iq-decoder pyadi \
  --format json \
  --report /ABSOLUTE/PRIVATE/PATH/reports/ram32-drop.json
```

For the matched 2×2 comparison, repeat only 25 MS/s/20 seconds with RAM slots
0 and 32 and with both `--drop-backlog-on-overrun` and
`--preserve-backlog-on-overrun`. Never reuse a report path; reports are
absent-only and stored under a mode-0700 parent.

For one local USB gadget among several radios sharing `192.168.2.1`, keep
`--transport ip` and add:

```text
--usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
--isolate-usb-route \
--isolation-confirm 'ISOLATE USB SSH EXACT_INTERFACE'
```

This still measures TCP/IP over the selected gadget. `--transport usb` is a
different libiio backend and cannot substitute for physical-1-GbE performance.

## Interpreting gaps and coverage

PPU reports delivered IQ bytes, application payload rate, requested/observed
frames, FPGA-counter gap events, exact missing samples, overflow events, and
RAM spill/drain/drop/high-water counters. Source coverage is:

```text
100 × delivered_sample_positions /
      (delivered_sample_positions + missing_sample_positions)
```

A 25 MS/s CI16 stream offers 100 MB/s. The measured network consumer is about
73 MB/s in the ringless performance profile, so buffers can postpone loss but
cannot make an arbitrarily long run lossless. Drop-backlog normally produces
fewer, larger discontinuities and returns to fresher RF time. Preserve-backlog
normally produces more separate discontinuities but can retain a higher
fraction of the source timeline.

## Post-install acceptance

Before production use, require:

- exact v0.48 firmware, AD9361 live identity, four RX scan elements, metadata
  ABI 3, direct/RAM/overrun capabilities, and default drop-backlog;
- exact host native/binding receipt for libiio `0d32308`;
- QSPI reconciliation to FIT `db777a…d1df` after reboot;
- all requested frames and zero terminal failures in the relevant ladder;
- zero gaps at sustainable 5/10/15 MS/s cells;
- `spilled = drained + dropped` and bounded RAM high-water when RAM is used;
- ordinary dual-RX capture and exact RF-setting restoration;
- TX gains muted, TX scan elements disabled, and DDS outputs zero; and
- guarded 5.8 GHz tune/readback/restore if that capability is required.

## Source-build verification

The protected artifact is the supported release. To audit or reproduce its
source graph, compare the checkout and every submodule to
[`manifests/iq-direct-async-v3.yaml`](manifests/iq-direct-async-v3.yaml) and
[`manifests/iq-direct-async-v3-source.yaml`](manifests/iq-direct-async-v3-source.yaml).
The source manifest embedded in the release tarball is byte-identical to the
repository file and has SHA-256 `8f9b4aa…e9b22`.

## Rollback

V0.47 is the rollback target. Rollback is another guarded persistent update,
not a raw MTD write. Use the exact v0.47 asset, its PPU persistent profile and
receipt, then install its matching libiio `8f66f353…` host runtime. Never mix
v0.47 and v0.48 native libraries or Python bindings.
