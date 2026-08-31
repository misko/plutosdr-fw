# Direct-async IQ source and installation requirements

This document is the compatibility and installation record for the
`iq-direct-async-ring-v1-rc1-source` hardware-qualified prerelease. It supplements
[`flashing.md`](flashing.md); the safety rules in that guide still apply.

## Current status

The implementation, exact source runtime, and version-stamped image are
hardware-qualified as a prerelease:

- the protected firmware identity is
  `v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1`;
- trusted build 33360776546 produced the checksum-verified published
  `pluto.frm`, `pluto.dfu`, and provenance bundle;
- the immutable libiio and Buildroot tags are published;
- Pluto Plus Utils `main` at `fd76f6694a60` contains the matched host API,
  ladder command, and exact local-USB route isolation;
- the firmware branch remains unmerged;
- the final image passed RAM-only functional, ring, recovery, RF restoration,
  and persistent-return qualification;
- the exact packaged runtime passed the 70 MB/s+ gate over 1 GbE; and
- persistent QSPI installation has not been authorized.

Do not flash an ordinary branch build. Use only the published assets and their
checksums. The 1 GbE performance test staged the iiOD and shared library
extracted from the final release rootfs under a unique `/tmp` directory,
leaving the installed firmware and system library unchanged. The complete
final image was independently RAM-booted and functionally qualified on a local
USB radio.

## Required component matrix

The commits below are a matched set. Substituting upstream libiio, a different
Python binding, or an older ABI-3 runtime is unsupported.

| Layer | Package/version | Required ref or commit | Why it is pinned |
| --- | --- | --- | --- |
| firmware integration | PlutoSDR firmware source; protected RC1 identity `v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1` | built source `4af2ab74605a62832f7f38a0eefe3b3bc1d492cf` on `codex/iq-direct-async-main-refresh`; implementation ancestor `a5253497d15613831055dbfb543ca5a9936bd2c6` | pins the Buildroot graph, records the qualified interface, and supplies the protected source manifest |
| firmware base | `origin/main` as of 2026-08-31 | `4f15c87033e332293711ad679a50af0109c72862` | current-main rebase point used for qualification |
| Buildroot | PlutoSDR Buildroot fork | `a929267288a80a31407a3af06345c088979bcc2e` / `iq-direct-async-ring-v1-rc1-source/buildroot-v2` | selects the exact radio-side libiio and metadata provider and pins the fetched archive hash |
| radio iiOD/libiio | libiio API/SONAME line 0.25 | `b7303fded264e10473bbbb084afade8f1b1373d1` on `codex/iq-direct-async-main-refresh-libiio` | unified DMA/RAM FIFO and three-period spill headroom |
| immutable libiio ref | published source tag | `iq-direct-async-ring-v1-rc1-source/libiio-v1` resolving exactly to `b7303fded264e10473bbbb084afade8f1b1373d1` | required by the receipt-writing host installer |
| libiio source archive | GitHub commit archive | SHA-256 `67364f519619afb1c7f12d35ea35e605e00d01d23fc470f16dc903c5b5cdd49a` | required by Buildroot before extraction; independently reproduced twice |
| metadata provider | SPF metadata ABI 3 / strict `RadioMetadataV6` | `3294365ff44da26b261be4a2ccb241b7896d23ad` | frame counter, gap, gain, and RSSI provider compiled into iiOD |
| host application | `pluto-plus-utils` package 0.1.0, Python 3.11 or newer | published `main` commit `fd76f6694a60c3edc471be12deee942076d5b216`; RC binding ancestor `65dd2c8b6184838b9147df917fbf3fbf3439ac99` | API, fail-closed admission, status parsing, finite-ring anchor handling, one-command ladder, exact RAM-only RC1 binding, and serial/path-scoped local USB route isolation |
| host native library | libiio 0.25 | the same `b7303fded264e10473bbbb084afade8f1b1373d1` | implements the host side of `READBUFMA` and ring-extension request |
| host Python binding | generated `pylibiio` from libiio 0.25 | the same `b7303fded264e10473bbbb084afade8f1b1373d1` | exposes the exact `MetadataBuffer(..., direct_async_frames=...)` signature |

The complete firmware gitlink set at the qualified integration commit is:

| Firmware component | Commit |
| --- | --- |
| Buildroot | `a929267288a80a31407a3af06345c088979bcc2e` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a` |

The firmware Makefile requires Vivado 2022.2. Its x86-64 Buildroot path uses
the pinned Linaro 2018.05 `arm-linux-gnueabihf` toolchain. Do not silently
replace either toolchain in a release build.

## Trusted prerelease image identities

Protected workflow run
[33360776546](https://github.com/misko/plutosdr-fw/actions/runs/33360776546)
built firmware source `4af2ab74605a62832f7f38a0eefe3b3bc1d492cf`.
The run is successful, hardware-qualified, and published as a GitHub
prerelease. Its exact bytes remain RAM-first; persistent QSPI promotion is a
separate gate.

| Object | Exact identity |
| --- | --- |
| Actions artifact | `plutoplus-main-4af2ab74605a62832f7f38a0eefe3b3bc1d492cf-33360776546-1` |
| deployment bundle | `plutoplus-spf-iq-direct-async-ring-v1-rc1-4af2ab74605a.tar.gz`; SHA-256 `3045f0f5045693a4599ee3891ec9fa5e027e7f327fccba7d76de858729ce5c6f` |
| DFU | `plutoplus-spf-iq-direct-async-ring-v1-rc1-4af2ab74605a-pluto.dfu`; SHA-256 `6b29618d186d82c6b8fa02f74073853029b7d081196cb8643b92550e09162391` |
| FIT body | 12,821,279 bytes; SHA-256 `47e850f4dabb5be58203991f9b4f5fefc45305335d9594210a661791ac0189e9` |
| FRM | `plutoplus-spf-iq-direct-async-ring-v1-rc1-4af2ab74605a-pluto.frm`; SHA-256 `5cd286cae15692cd2df917d954c8e50fe86899ab7877d67b8fc3a04c203df617` |
| rootfs | SHA-256 `fd802e8fde40ba114f5b5ff46023d744f39c45ff26f902f1a19a3c9f1334226e` |
| packaged iiOD | SHA-256 `cf950bdcdefa56ff90690e90fad8ce64151997c707ae3236b967b4bcfc6e9ec6` |
| packaged `libiio.so.0.25` | SHA-256 `7333f76edb775ebea3a51911c42dc5f3e45fb1e082676a867b7fa90b5d61168a` |

Download and verify the exact published assets into a new private directory:

```bash
candidate_dir="$(mktemp -d /tmp/pluto-direct-async-rc1.XXXXXX)"
chmod 0700 "$candidate_dir"
gh release download v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1 \
  --repo misko/plutosdr-fw --dir "$candidate_dir"
(
  cd "$candidate_dir"
  sha256sum -c iq-direct-async-ring-v1-rc1-SHA256SUMS
)
```

The full tarball is the retained workflow artifact. After safe extraction,
require both `sha256sum -c SHA256SUMS` and
`sha256sum -c PAYLOAD_SHA256SUMS` to pass. The packaged `/opt/VERSIONS` must
name the exact v0.46 RC1 and Buildroot v2. The integrated verdict must be
`PASS` and `firmware_release_eligible: true`.

## Runtime compatibility contract

The radio and host must agree on all of the following:

| Contract item | Required value |
| --- | --- |
| libiio protocol/API line | 0.25, git tag `b7303fd` |
| metadata ABI | `iio,buffer-metadata=3` |
| scan layouts | `00000003:1:4:2,0000000c:1:4:2,0000000f:2:8:1` |
| direct capability | `iio,buffer-direct-async=1` |
| RAM-extension capability | `iio,buffer-direct-async-ring=1` |
| RAM-ring base capabilities | `iio,buffer-ddr-ring=1`, modes `finite,continuous`, metadata status 1, and a positive advertised maximum |
| direct capture topology | exactly one selected receiver |
| finite target owner | `direct_async_frames`, 1 through 64 |
| combined RAM target | `ddr_ring_frames=0`, `ddr_ring_continuous=False` |
| DMA depth | at least 2 without RAM; at least 3 with RAM |
| incompatible mode | `ddr_burst_bytes` must be zero |
| qualified network daemon setting | `iiod -r 1` |

The 70 MB/s result is conditional on `-r 1` and adequate queue depth. The
qualified direct profile used 15 DMA buffers for 23 frames. Eight DMA buffers
still moved bytes above 70 MB/s but lost five whole frames, so it is not an
acceptable installation profile.

The pinned Buildroot startup script supplies `--rw-cpu-affinity 1`, the
long-form equivalent of `-r 1`, to the supervised production iiOD. Final-image
qualification must verify that exact live command line. Do not run a second
iiOD against the same IIO device while the supervised service owns it.

## Verify the source graph

Run these checks in the four existing worktrees before building:

```bash
FW_SRC=/ABSOLUTE/PATH/TO/plutosdr-fw-iq-direct-async-main-refresh
BUILDROOT_SRC=/ABSOLUTE/PATH/TO/plutosdr-buildroot-iq-direct-async-main-refresh
LIBIIO_SRC=/ABSOLUTE/PATH/TO/libiio-iq-direct-async-main-refresh
HOST_SRC=/ABSOLUTE/PATH/TO/pluto-plus-utils-iq-direct-async-main-refresh

git -C "$FW_SRC" merge-base --is-ancestor 4f15c87033e332293711ad679a50af0109c72862 HEAD
git -C "$FW_SRC" ls-tree HEAD buildroot

git -C "$BUILDROOT_SRC" rev-parse HEAD
sed -n 's/^LIBIIO_VERSION[[:space:]]*=[[:space:]]*//p' "$BUILDROOT_SRC/package/libiio/libiio.mk"
sed -n 's/^SPF_METADATA_SOURCE_VERSION[[:space:]]*=[[:space:]]*//p' "$BUILDROOT_SRC/package/spf_metadata_source/spf_metadata_source.mk"

git -C "$LIBIIO_SRC" rev-parse HEAD
git -C "$HOST_SRC" rev-parse HEAD
```

Expected values are Buildroot `a9292672...`, libiio `b7303fde...`,
metadata provider `3294365f...`, and host commit `fd76f669...` (or a descendant)
on published `main`. Host commit `65dd2c8b...` is the minimum RC binding, but
`fd76f669...` is required when multiple local Pluto USB routes exist. A later
documentation-only descendant is acceptable; changing any implementation pin
requires rebuilding and repeating the qualification.

## Publication and firmware build order

The order matters:

1. Verify the published immutable libiio tag resolves exactly to
   `b7303fded264e10473bbbb084afade8f1b1373d1` and the published Buildroot v2 tag
   resolves exactly to `a929267288a80a31407a3af06345c088979bcc2e`.
2. Verify Pluto Plus Utils `main` contains exact commit `fd76f6694a60` and
   install its receipt-bound native runtime from the immutable libiio tag.
3. Validate `manifests/iq-direct-async-ring-v1-rc1-source.yaml` and the
   protected candidate packaging route.
4. Build the exact firmware source graph with Vivado 2022.2 and the pinned
   Buildroot toolchain, using the clone-depth and architecture rules in
   [`BUILD.md`](BUILD.md).
5. Supply the exact protected firmware version
   `v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1` through
   `RELEASE_VERSION`. Do not use `a5253497d` as the on-radio `device-fw` value.
6. Verify the packaged `/opt/VERSIONS`, source manifest, image checksums, and
   exact libiio identity.
7. RAM-boot the final version-stamped image and repeat the direct, combined,
   standalone-ring, recovery, and RF-restoration gates. RC1 passed this gate on
   serial `1040007c4a94000211000b009186843ef2`.
8. Confirm the packaged iiOD/libiio pair crosses 70 MB/s on adequate Ethernet.
   RC1 delivered 73.30 and 75.17 MB/s in the 25-MS/s cells on 1 GbE.
9. Publish the exact qualified bytes. Persistent flashing remains a separate
   approval after prerelease publication.

After the protected environment has resolved and checked the exact gitlinks,
the firmware-partition build entry point is:

```bash
cd /ABSOLUTE/PATH/TO/plutosdr-fw-iq-direct-async-main-refresh
RELEASE_VERSION=v0.46-plutoplus-spf-iq-direct-async-ring-v1-rc1 \
  make build/pluto.dfu
```

The protected workflow rejects any other version for this manifest. Follow
[`RELEASING.md`](RELEASING.md) for the source-lock, packaging, and provenance
gates.

## Install the matched host runtime

The immutable libiio ref is published, so the receipt-writing installation
procedure is now usable. It must fail rather than fall back to another commit.

```bash
cd /ABSOLUTE/PATH/TO/pluto-plus-utils-iq-direct-async-main-refresh
uv sync --extra hardware

scripts/install_native_libiio.sh \
  --uv-bin /ABSOLUTE/PATH/TO/NON-SYMLINK/uv \
  --metadata-abi 3 \
  --python /ABSOLUTE/PATH/TO/pluto-plus-utils-iq-direct-async-main-refresh/.venv/bin/python \
  --prefix /ABSOLUTE/PATH/TO/pluto-plus-utils-iq-direct-async-main-refresh/.venv
```

The installer clones the immutable ref, checks the full commit, builds native
libiio and its generated binding together, and writes
`.venv/share/pluto-plus-utils/metadata-runtime.json`. It must record:

- `metadata_abi: 3`;
- source ref `iq-direct-async-ring-v1-rc1-source/libiio-v1`;
- source commit `b7303fded264e10473bbbb084afade8f1b1373d1`;
- the installed native library's absolute path and SHA-256;
- the installed Python binding's absolute path and SHA-256; and
- a `MetadataBuffer` constructor ending in `direct_async_frames`.

Do not install `pylibiio` from PyPI afterward. Do not combine a wheel, native
library, or receipt from different commits. A system libiio may coexist, but
the application must preload the receipt-bound library inside its release
environment.

Verify the host installation:

```bash
cd /ABSOLUTE/PATH/TO/pluto-plus-utils-iq-direct-async-main-refresh
uv run pluto environment --format json

.venv/bin/python - <<'PY'
import inspect
import iio

assert iio.version == (0, 25, "b7303fd")
assert tuple(inspect.signature(iio.MetadataBuffer.__init__).parameters)[-1] == (
    "direct_async_frames"
)
print(iio.__file__, iio.version)
PY
```

## Verify the installed radio and host together

After a final firmware image exists and has been RAM-booted, use the
receipt-bound tools to inspect the intended serial-pinned URI:

```bash
.venv/bin/iio_info -u ip:RADIO_ADDRESS | sed -n '1,40p'
```

Require all of these observations before capture:

- the expected final `fw_version`, not the old installed firmware;
- the intended hardware serial;
- frontend and backend libiio version 0.25, git tag `b7303fd`;
- `iio,buffer-metadata: 3`;
- `iio,buffer-direct-async: 1`;
- `iio,buffer-direct-async-ring: 1`; and
- the exact ABI-3 scan-layout string.

The release acceptance profiles are:

| Mode | Sample rate | DMA buffers | RAM slots | Frames | Required result |
| --- | ---: | ---: | ---: | ---: | --- |
| direct DMA | 30.72 MS/s | 15 | 0 | 23 | at least 70 MB/s and zero gaps |
| DMA with RAM extension | 30.72 MS/s | 10 | 13 | 23 | zero gaps, nonzero spill/drain counts, clean completion |
| standalone finite RAM ring | 20 MS/s | 8 | 15 | 23 | zero gaps, 23 produced/consumed, clean completion |

RAM-extension application throughput is not required to reach 70 MB/s. Its
acceptance purpose is extra FIFO capacity with preserved ordering and exact
status.

The guarded volatile transition is bound by Pluto Plus Utils ancestor
`65dd2c8b6` and present in the required `fd76f6694a60` head as profile
`iq-direct-async-ring-v1-rc1-ram`. It accepts only the DFU/FIT identity above
and has no persistent counterpart. First run the command without
`--execute` and review the serial, direct USB sysfs path, current firmware,
candidate version, and confirmation phrase. Execution uses the same arguments
plus `--execute --confirm 'RAM BOOT EXPECTED_SERIAL'`:

```bash
pluto firmware ram-boot /ABSOLUTE/PATH/TO/EXACT_RC1.dfu \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_DIRECT_PATH \
  --profile iq-direct-async-ring-v1-rc1-ram \
  --ssh-known-hosts-file /ABSOLUTE/PRIVATE/PATH/EXPECTED_SERIAL.known_hosts
```

The exact final image was RAM-booted on directly attached serial
`1040007c4a94000211000b009186843ef2` at `/sys/bus/usb/devices/3-8`. The guarded
receipt attested the candidate identity and unchanged QSPI. After qualification,
the same guarded utility rebooted it to its prior persistent
`v0.42-plutoplus-spf-ddr-burst-v2`; a bounded dual-RX refill, AD9361/2R2T tuple,
and 5.8 GHz tune/readback/restore probe passed. RC1 was never persistently
written.

The sustained release ladder is one Pluto Plus Utils command. Its defaults are
the required `5M,10M,15M,25M` rates, `3,10` second durations, 1,048,576 samples
per block, and 15 DMA buffers:

```bash
pluto radio direct-async-ladder RADIO_ADDRESS \
  --transport ip --ip-port 30431 \
  --expect-serial EXPECTED_SERIAL
```

Repeat it with RAM extending the same queue:

```bash
pluto radio direct-async-ladder RADIO_ADDRESS \
  --transport ip --ip-port 30431 \
  --expect-serial EXPECTED_SERIAL \
  --kernel-buffers 10 --ram-ring-slots 13
```

Both commands must execute all eight cells and restore the pre-test RX
settings. Require no command/protocol/readback/capture failures;
evaluate reported gap and missing-sample counts as measurements rather than
hiding them behind a successful exit. The ringless 25-MS/s cells must exceed
70 MB/s. RAM mode must show nonzero and equal aggregate spill/drain counts
with a high-water mark no greater than 13. A sustained-rate cell is gapless
only when its reported gap events, missing samples, and overflow count are all
zero.

The exact final image's 480 Mb/s USB-gadget link passed the 5-MS/s ladder cells
but could not carry the higher rates and reset under pressure. That is a host
link limit, not 70 MB/s evidence. On the 1 GbE radio at `192.168.1.15`, the
exact packaged iiOD and `libiio.so.0.25` extracted from the final rootfs ran on
an isolated port without replacing installed files. The ringless 25-MS/s cells
delivered 73.30 and 75.17 MB/s. They also reported 7 and 20 missing frames, so
RC1 claims 70 MB/s+ transport but not gapless continuously offered 25 MS/s.

The corresponding RAM-extension ladder spilled/drained 29/29 and 106/106
descriptors in the 25-MS/s cells, reached its configured 13-slot high-water
mark, and reduced missing frames from 27 to 22. Final-image local qualification
separately delivered a 29-frame, 10-MS/s run with zero gaps, 9 spills, 9 drains,
and high-water 8. Together these measurements prove that RAM extends the same
ordered queue.

For release evidence, add `--format table --report ABSENT_REPORT_PATH`. The
report path must be new and beneath an operator-owned mode-0700 directory; the
command deliberately refuses an existing path or a less-private parent.

For exact reproducibility, the explicit form of the defaults is:

```bash
pluto radio direct-async-ladder RADIO_ADDRESS \
  --transport ip --ip-port 30431 \
  --expect-serial EXPECTED_SERIAL \
  --rates 5M,10M,15M,25M --durations 3,10 \
  --samples 1048576 --kernel-buffers 15
```

## Qualification binary identities

The volatile qualification used these ARM32 EABI5 files built from exact
`b7303fd`:

| File | SHA-256 |
| --- | --- |
| `iiod` | `89c5eae83b7bb517279ebe97e3300615c58efbf3892dc9d6939966429122e01d` |
| `libiio.so.0.25` | `8fd0530bd712abe6398f300c17c34052a3e86acfbf374680071869f260921841` |

These hashes identify the earlier independent source cross-build only. The
published release contains its own packaged iiOD and library hashes in the
asset table above; do not interchange the two binary pairs.

## Rollback and recovery

For a volatile test, stop only the exact temporary iiOD process, ensure the DMA
buffer and control register are clear, remove its explicit temporary directory,
and restore the original supervised iiOD command. Recheck installed
`/usr/sbin/iiod` and `/usr/lib/libiio.so.0.25` hashes and restore all RF
settings.

For a published persistent image, use only the firmware-partition recovery
methods in [`flashing.md`](flashing.md). Never install or roll back with a
full firmware ZIP on Pluto+. Keep the previous hardware-qualified
`pluto.frm` or `pluto.dfu`, its checksums, serial-scoped preflight record,
and the matching host-runtime package available until the new release passes
cold-boot and recovery qualification.
