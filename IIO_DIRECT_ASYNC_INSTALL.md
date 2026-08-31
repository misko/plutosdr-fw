# Direct-async IQ v2 installation and compatibility

This is the normative compatibility, host-runtime, installation, and
acceptance guide for full release
`v0.47-plutoplus-spf-iq-direct-async-v2`. It supplements
[`flashing.md`](flashing.md); every Pluto+ bootloader safety rule there still
applies.

## Release status

Protected run
[33440908273](https://github.com/misko/plutosdr-fw/actions/runs/33440908273)
built exact merged firmware `main` commit
`2bab87dcd9b18c8f957ae781603e88160c8509cc`. Those bytes passed the integrated
route gate, RAM boot, 5/10/15/25 MS/s ladders, sustained 70 MB/s, direct DMA,
200 MB RAM extension, both v2 overrun policies, single-session 1 GB timelines,
abrupt-client recovery, ordinary dual-RX, TX-safe, 5.8 GHz tune/restore,
persistent write, and exact QSPI FIT verification.

The all-power-removed cold-boot gate passed on the exact persistent bytes. Full
evidence is recorded in
[`RELEASE_IQ_DIRECT_ASYNC_V2.md`](RELEASE_IQ_DIRECT_ASYNC_V2.md).

## Exact matched component set

Substituting stock libiio, an unmodified PyPI `pylibiio`, a different firmware
asset, or an older Pluto Plus Utils checkout is unsupported.

| Layer | Required version, ref, or commit |
| --- | --- |
| firmware identity | `v0.47-plutoplus-spf-iq-direct-async-v2` |
| firmware binary source | `2bab87dcd9b18c8f957ae781603e88160c8509cc`; tag `iq-direct-async-v2-source/fw-v1` |
| Buildroot | `3e1dd15acf361cc06e202e9e59e907dd379a13c3`; tag `iq-direct-async-v2-source/buildroot-v1` |
| radio and host libiio | 0.25 at `8f66f353c9a70a5524988ceb588b0e9271c2390d`; tag `iq-direct-async-v2-source/libiio-v1` |
| metadata provider | ABI 3 / `RadioMetadataV6` at `3294365ff44da26b261be4a2ccb241b7896d23ad` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; `ddr-burst-v1-rc4-source/hdl-v1` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7`; `ddr-burst-v1-rc3-source/linux-v1` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`; `gain-series-v4-rc2-source/u-boot-xlnx` |
| Pluto Plus Utils | package 0.1.0, Python 3.11+; `main` at `9f9a2bd6d059833bc7d9259a48eabff8e20642ad` or later |
| PPU long-session/overrun implementation | merge `d5435901dd7a37619d71db9fdd0d0f1fb368b0bd` |
| PPU persistent v2 promotion / repeat read-only reconciliation | `cb7c81127688e00dc0990e7b9d7cea3d05b7b936` / `a6c0ae65cb6818afbd3e0e20be457868e87f50f6` |
| Vivado | 2022.2, build 3671981 |
| ARM toolchain | Linaro GCC 7.3-2018.05, GCC 7.3.1 |

The packaged `/opt/VERSIONS` must be exactly:

```text
device-fw v0.47-plutoplus-spf-iq-direct-async-v2
hdl ddr-burst-v1-rc4-source/hdl-v1
buildroot iq-direct-async-v2-source/buildroot-v1
linux ddr-burst-v1-rc3-source/linux-v1
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
```

## Download and verify

Create a new private directory and download only the named release:

```bash
candidate_dir="$(mktemp -d /tmp/pluto-direct-async-v2.XXXXXX)"
chmod 0700 "$candidate_dir"
gh release download v0.47-plutoplus-spf-iq-direct-async-v2 \
  --repo misko/plutosdr-fw --dir "$candidate_dir"
(
  cd "$candidate_dir"
  sha256sum -c iq-direct-async-v2-SHA256SUMS
)
```

The release checksum inventory is:

| Object | SHA-256 |
| --- | --- |
| `plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1.tar.gz` | `04866f2d3e420326f70184f654d28e4a42d4251c0a97765a3eae3b367c63d8eb` |
| `plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1-pluto.dfu` | `b97564524058b4b57e73ccfa60cdf1acbefaac05f90b16ccd460b0a8bb6c307d` |
| `plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1-pluto.frm` | `e56728f87fea150d0f0b057deed2f1878ecb830bab3e81ddaba84dc8a7449451` |
| `iq-direct-async-v2-source.yaml` | `8686c67e6cb19d7f75ef9cc171a4f1598430b8e1f39fa346bc41b9856cad414b` |
| `iq-direct-async-v2.yaml` | `f534ca8a7d08535409c846f350c266d76d5525d284158e43030f82a700974d56` |
| DFU/FRM FIT body, 12,826,107 bytes | `7a198f961cd6765ebd831c21314baac0f962650541af671911c23e76db33cbc2` |

If using the tar bundle, extract it into another private directory and require
both of its checksum inventories to pass before using a member:

```bash
bundle_dir="$(mktemp -d /tmp/pluto-direct-async-v2-bundle.XXXXXX)"
tar -xzf "$candidate_dir/plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1.tar.gz" \
  -C "$bundle_dir"
(
  cd "$bundle_dir"
  sha256sum -c SHA256SUMS
  sha256sum -c PAYLOAD_SHA256SUMS
)
```

## Install the matched host runtime

Install Pluto Plus Utils from the required `main` or later, then use its
repository installer. The native library and generated Python binding are
built from the same immutable libiio tree:

```bash
git clone https://github.com/misko/pluto-plus-utils.git
cd pluto-plus-utils
git checkout 9f9a2bd6d059833bc7d9259a48eabff8e20642ad
uv sync --extra hardware

scripts/install_native_libiio.sh \
  --uv-bin /ABSOLUTE/PATH/TO/NON-SYMLINK/uv \
  --metadata-abi 3 \
  --python "$PWD/.venv/bin/python" \
  --prefix "$PWD/.venv"
```

The installer pins `iq-direct-async-v2-source/libiio-v1` at full commit
`8f66f353c9a70a5524988ceb588b0e9271c2390d`. Do not install `pylibiio` from
PyPI afterward. Do not mix the native library, Python binding, or runtime
receipt from different commits.

Verify the installed environment:

```bash
uv run pluto environment --format json

LD_LIBRARY_PATH="$PWD/.venv/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  .venv/bin/python - <<'PY'
import inspect
import iio

assert iio.version == (0, 25, "8f66f35")
parameters = tuple(inspect.signature(iio.MetadataBuffer.__init__).parameters)
assert "direct_async_frames" in parameters
assert "drop_backlog_on_overrun" in parameters
print(iio.__file__, iio.version)
PY
```

The radio uses the same libiio source and supervises iiOD with R/W worker CPU
affinity 1, equivalent to `iiod -r 1`.

## Runtime contract

Require every item below before starting a capture:

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
| direct target | 1 through 4,096 frames in one request |
| incompatible mode | `ddr_burst_bytes=0` |
| host/radio libiio | exact `8f66f35` tree on both sides |

RAM slots extend the same FIFO and preserve frame order. With RAM disabled,
the direct path allocates and copies no RAM-ring IQ. The frame already entering
TCP is never retired by either overrun policy.

## Guarded local-USB persistent installation

Pluto+ installation updates only the `qspi-linux` firmware partition. Never
use a full firmware ZIP, `boot.frm`, `boot.dfu`, or `uboot-env.dfu`.

Identify one directly attached radio by exact USB serial and sysfs path. Stop
every process using it. First run the command without `--execute`:

```bash
uv run pluto firmware flash \
  "$candidate_dir/plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1-pluto.dfu" \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v2-release-persistent-promotion
```

The dry run must show the intended serial/path, DFU SHA `b9756452...`, FIT SHA
`7a198f96...`, FIT size 12,826,107, metadata ABI 3, tandem capability, and
target v0.47. If any field differs, stop. Execute only with the exact phrase
printed by that plan:

```bash
uv run pluto firmware flash \
  "$candidate_dir/plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1-pluto.dfu" \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v2-release-persistent-promotion \
  --execute --confirm 'FLASH EXACT_SERIAL'
```

Keep the durable receipt. Do not retry an uncertain post-eject operation;
reconcile it read-only.

### Ephemeral SSH key handling

The radio generates a new SSH host key after reboot. Do not disable host-key
checking and do not keep a fleet-wide static trust exception. Enroll the
current key only after PPU attests the exact USB path, IIOD serial, and selected
route:

```bash
uv run pluto firmware enroll-usb-ssh EXACT_SERIAL \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --password-file /ABSOLUTE/PRIVATE/PATH/radio.password \
  --isolate-usb-route
```

Review the dry run, then repeat with:

```text
--execute --confirm 'TRUST USB SSH EXACT_SERIAL' \
  --isolation-confirm 'ISOLATE USB SSH EXACT_INTERFACE'
```

Re-enroll after every reboot. PPU temporarily isolates competing Pluto routes,
binds the trust action to one serial/path, and restores the host network in a
`finally` path.

Use the new key to verify active identity, TX-safe state, and the exact FIT
length and hash in `/dev/mtd3`:

```bash
uv run pluto firmware reconcile-local RECEIPT_ID \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-v2-release-persistent-promotion \
  --ssh-known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --ssh-password-file /ABSOLUTE/PRIVATE/PATH/radio.password \
  --isolate-usb-route \
  --isolation-confirm 'ISOLATE USB SSH EXACT_INTERFACE'
```

Then remove every power source for at least 10 seconds. After reconnect, enroll
the newly rotated key again and repeat reconciliation, doctor, ordinary RX,
5.8 GHz tune/restore, and TX-safe checks. A software reboot or USB detach while
the board remains powered is not a cold-boot qualification.

## Guarded network-only installation

Network flashing is supported only with PPU's serial-attested LAN workflow.
First pin the current ephemeral key through read-only IIOD identity:

```bash
uv run pluto firmware enroll-lan-ssh EXACT_SERIAL \
  --host 192.168.1.20 \
  --known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --profile iq-direct-async-v2-release \
  --execute --use-default-password \
  --confirm 'TRUST LAN SSH EXACT_SERIAL 192.168.1.20'
```

Run the exact flash once without `--execute`:

```bash
uv run pluto firmware flash-lan \
  "$candidate_dir/plutoplus-spf-iq-direct-async-v2-2bab87dcd9b1-pluto.dfu" \
  --serial EXACT_SERIAL --host 192.168.1.20 \
  --profile iq-direct-async-v2-release-persistent-promotion \
  --ssh-known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXACT_SERIAL.known_hosts \
  --ssh-password-file /ABSOLUTE/PRIVATE/PATH/radio.password
```

After reviewing the serial, host, hashes, profile, and prior firmware, execute
with `--execute --confirm 'FLASH LAN EXACT_SERIAL 192.168.1.20'`. The workflow
attests IIOD disappearance/return, verifies v0.47 and its release-specific
capabilities, mutes TX, rotates the ephemeral SSH key only after exact return,
and emits a durable receipt. Repeat independently for another address; never
reuse the first radio's serial or known-hosts file.

## Functional ladder and acceptance

The release matrix is one PPU command. Its defaults are the 5/10/15/25 MS/s by
3/10-second ladder, but the explicit form is recommended for evidence:

```bash
uv run pluto radio direct-async-ladder 192.168.1.15 \
  --transport ip --expect-serial EXACT_SERIAL \
  --rates 5M,10M,15M,25M --durations 3,10 \
  --samples 1048576 --kernel-buffers 15 \
  --iq-decoder raw-complex64 \
  --drop-backlog-on-overrun \
  --format json --report /ABSOLUTE/PRIVATE/PATH/ringless-ladder.json
```

Run a matched 200 MB extension with one-million-sample frames, 12 DMA
descriptors, and 50 RAM slots:

```bash
uv run pluto radio direct-async-ladder 192.168.1.15 \
  --transport ip --expect-serial EXACT_SERIAL \
  --rates 5M,10M,15M,25M --durations 3,10 \
  --samples 1000000 --kernel-buffers 12 --ram-ring-slots 50 \
  --iq-decoder raw-complex64 \
  --drop-backlog-on-overrun \
  --format json --report /ABSOLUTE/PRIVATE/PATH/ram200-ladder.json
```

Use `--preserve-backlog-on-overrun` for the control policy. Every supported
cell is one finite DMA session; there is no periodic 64-frame re-arm. The
duration is requested source time, not a wall-clock deadline. Counter-observed
gaps are reported results; protocol, cleanup, restoration, or readback failures
make the command exit nonzero.

For a local gadget among several radios sharing `192.168.2.1`, add the exact
`--usb-sysfs-path`, `--isolate-usb-route`, and confirmation phrase. This still
tests TCP/IP; `--transport usb` is a different path and cannot substitute for
the 1-GbE performance gate.

Acceptance requires:

- all eight ladder cells complete and restore settings;
- ringless sustained 25 MS/s exceeds 70 MB/s on the qualified physical-1-GbE
  host;
- 5, 10, and 15 MS/s cells have zero counter gaps;
- RAM mode reports exact `spilled = drained + evicted`, valid high-water/wrap,
  and clean target completion;
- a 250-frame/1 GB request reports one capture segment and zero host re-arms;
- abrupt client loss recovers without Linux or iiOD restart;
- ordinary dual-RX refill, zero active buffers/faults, TX mute, and exact RX
  settings restoration pass; and
- AD9361/2R2T setup and 5.8 GHz tune/readback/exact prior-LO restoration pass.

At 25 MS/s, CI16 offers 100 MB/s. Buffers can defer loss but cannot make a
slower steady consumer lossless forever. `drop-backlog` minimizes stale-data
latency and gap-event count; it does not promise the highest source coverage.

## Source-build verification

Before reproducing the protected build, verify every pin:

```bash
git -C /PATH/TO/plutosdr-fw rev-parse HEAD
git -C /PATH/TO/plutosdr-fw ls-tree HEAD buildroot hdl hdl-quantulum linux u-boot-xlnx
git -C /PATH/TO/libiio rev-parse HEAD
git -C /PATH/TO/pluto-plus-utils rev-parse HEAD
```

Expected values are firmware `2bab87d...`, Buildroot `3e1dd15...`, HDL
`145bd47...`, HDL Quantulum `364b3dc...`, Linux `93174a1...`, U-Boot
`1ff0468...`, libiio `8f66f35...`, and PPU `9f9a2bd...` or later. Build with
Vivado 2022.2 and the pinned Linaro toolchain:

```bash
cd /PATH/TO/plutosdr-fw
RELEASE_VERSION=v0.47-plutoplus-spf-iq-direct-async-v2 \
  make build/pluto.dfu
```

Any source-pin change produces different bytes and requires a new protected
build and complete hardware qualification.

## Rollback

Retain the previous hardware-qualified v0.46 DFU, checksum file, and its own
PPU persistent profile until all post-install tests pass. Roll back only the
`qspi-linux` firmware partition using
`iq-direct-async-ring-v1-release-persistent-promotion`. Never rewrite the
Pluto+ bootloader or U-Boot environment during a routine upgrade or rollback.
