# Direct-async IQ + RAM queue v1 installation and compatibility

This is the normative compatibility, installation, and acceptance record for
full release `v0.46-plutoplus-spf-iq-direct-async-ring-v1`. It supplements
[`flashing.md`](flashing.md); every Pluto+ bootloader safety rule in that guide
still applies.

## Release status

The exact non-RC image is qualified for guarded persistent installation:

- protected build 33408049625 built clean merged firmware `main` at
  `f182a8fa0811d2e70186b8f75d06ff4d5d896140`;
- the integrated routed result is `PASS` and
  `firmware_release_eligible: true`;
- the final image passed RAM boot, physical-1-GbE throughput, direct DMA,
  combined DMA/RAM, standalone ring, client-loss recovery, and RF restoration;
- guarded persistent installation, user power-cycle, exact `/dev/mtd3` FIT
  attestation, and all post-cold-boot functional checks passed; and
- three 23-frame direct-DMA runs delivered 71.05, 72.12, and 71.76 MB/s with
  zero gaps.

Do not flash an ordinary branch or CI artifact. Download only the named release
assets and verify the release checksum file before using them.

## Exact matched component set

Substituting stock libiio, an unmodified PyPI `pylibiio`, or an older ABI-3
runtime is unsupported.

| Layer | Required version, ref, or commit |
| --- | --- |
| firmware identity | `v0.46-plutoplus-spf-iq-direct-async-ring-v1` |
| firmware binary source | `f182a8fa0811d2e70186b8f75d06ff4d5d896140`; immutable tag `iq-direct-async-ring-v1-source/fw-v1` |
| original refreshed base | `origin/main` at `4f15c87033e332293711ad679a50af0109c72862` |
| Buildroot | `a929267288a80a31407a3af06345c088979bcc2e`; immutable tag `iq-direct-async-ring-v1-rc1-source/buildroot-v2` |
| radio and host libiio | API/SONAME 0.25 at `b7303fded264e10473bbbb084afade8f1b1373d1`; immutable tag `iq-direct-async-ring-v1-rc1-source/libiio-v1` |
| SPF metadata provider | ABI 3 / strict `RadioMetadataV6` at `3294365ff44da26b261be4a2ccb241b7896d23ad` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba`; tag `ddr-burst-v1-rc4-source/hdl-v1` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7`; tag `ddr-burst-v1-rc3-source/linux-v1` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a`; tag `gain-series-v4-rc2-source/u-boot-xlnx` |
| Pluto Plus Utils | package 0.1.0, Python 3.11+; published `main` at `d3e5cfeb1bae07357c711e4277053bb97fd5cee7` or later |
| host qualification/promotion implementation | `605384fc1095196e5a5946bc08e633394675c0c1` |
| Vivado | 2022.2, build 3671981 |
| ARM toolchain | Linaro GCC 7.3-2018.05, GCC 7.3.1 |

The `rc1-source` dependency tags are historical immutable source-lock names.
The full release deliberately reuses those exact hardware-qualified dependency
bytes; its firmware version and release tag are non-RC.

The packaged `/opt/VERSIONS` must be exactly:

```text
device-fw v0.46-plutoplus-spf-iq-direct-async-ring-v1
hdl ddr-burst-v1-rc4-source/hdl-v1
buildroot iq-direct-async-ring-v1-rc1-source/buildroot-v2
linux ddr-burst-v1-rc3-source/linux-v1
u-boot-xlnx gain-series-v4-rc2-source/u-boot-xlnx
```

## Release asset identities

Protected Actions run
[33408049625](https://github.com/misko/plutosdr-fw/actions/runs/33408049625),
attempt 1, produced these exact objects:

| Object | SHA-256 |
| --- | --- |
| `plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811.tar.gz` | `c91ab1fdd68fd66ca6f871d190c994417012bc6957f2b242ada680a9edab086e` |
| `plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.dfu` | `ac51893dac8a914621aa8eb6f5c65d324ae8f09812033aa4880dc1dad8e6d739` |
| `plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.frm` | `8a18aa951ba4d0e24534d2e15eec624587b07c92be991b0cb7f0d1669cad241e` |
| `iq-direct-async-ring-v1-rc1-source.yaml` | `7be350c946ef9cfe8c80e18ef74e30c78342bb4e5ae3484ba51f925dc80fabf0` |
| rootfs | `d80bbd7d8f4c9f997b318f815cd1664e5d8b97580bac5478e532bf117aa6d09b` |
| FIT body, 12,821,527 bytes | `8dc973cd808a49392d26e69336c3b5c32dbece6903f69b30698873caa1bf79c5` |
| packaged `/usr/sbin/iiod` | `cf950bdcdefa56ff90690e90fad8ce64151997c707ae3236b967b4bcfc6e9ec6` |
| packaged `libiio.so.0.25` | `7333f76edb775ebea3a51911c42dc5f3e45fb1e082676a867b7fa90b5d61168a` |

The exact protected build-input manifest deliberately keeps its historical
RC1 name and values. It pins the reused dependency graph; the final binary
source is merged firmware `main` at `f182a8fa...`, independently locked by
`iq-direct-async-ring-v1-source/fw-v1` and recorded in the bundle provenance.

Download and verify into a new private directory:

```bash
candidate_dir="$(mktemp -d /tmp/pluto-direct-async-v1.XXXXXX)"
chmod 0700 "$candidate_dir"
gh release download v0.46-plutoplus-spf-iq-direct-async-ring-v1 \
  --repo misko/plutosdr-fw --dir "$candidate_dir"
(
  cd "$candidate_dir"
  sha256sum -c iq-direct-async-ring-v1-SHA256SUMS
)
```

If using the retained deployment bundle, also require its internal
`SHA256SUMS` and `PAYLOAD_SHA256SUMS` checks to pass before inspecting or using
any member.

## Runtime contract

The radio and host must agree on every item below:

| Contract item | Required value |
| --- | --- |
| libiio line | 0.25, git build tag `b7303fd` |
| metadata ABI | `iio,buffer-metadata=3` |
| scan layouts | `00000003:1:4:2,0000000c:1:4:2,0000000f:2:8:1` |
| direct capability | `iio,buffer-direct-async=1` |
| RAM-extension capability | `iio,buffer-direct-async-ring=1` |
| standalone RAM capabilities | `iio,buffer-ddr-ring=1`, finite and continuous modes, metadata status, and a positive maximum |
| direct topology | exactly one selected receiver |
| direct finite target | `direct_async_frames`, 1 through 64 per request |
| combined RAM target | `ddr_ring_frames=0`, `ddr_ring_continuous=False` |
| DMA depth | 2 through 64 without RAM; at least 3 with RAM |
| incompatible mode | `ddr_burst_bytes=0` |
| radio daemon | `iiod -r 1`, or supervised equivalent `--rw-cpu-affinity 1` |

RAM extension contributes overflow slots to the same ordered DMA descriptor
FIFO. It is not a second capture, prefill, or output queue. With RAM disabled,
the direct path allocates and copies no ring IQ.

## Install the matched host runtime

Use Pluto Plus Utils `main` at `d3e5cfeb1bae07357c711e4277053bb97fd5cee7`
or later. The native library and generated Python binding must both be built
from exact libiio `b7303fd`:

```bash
git clone https://github.com/misko/pluto-plus-utils.git
cd pluto-plus-utils
git checkout d3e5cfeb1bae07357c711e4277053bb97fd5cee7
uv sync --extra hardware

scripts/install_native_libiio.sh \
  --uv-bin /ABSOLUTE/PATH/TO/NON-SYMLINK/uv \
  --metadata-abi 3 \
  --python "$PWD/.venv/bin/python" \
  --prefix "$PWD/.venv"
```

The installer must write
`.venv/share/pluto-plus-utils/metadata-runtime.json` naming metadata ABI 3,
the immutable libiio ref, full source commit, installed library/binding hashes,
and a `MetadataBuffer` constructor ending in `direct_async_frames`.

Do not install `pylibiio` from PyPI afterward. Do not mix a wheel, native
library, Python binding, or receipt from different commits. Verify the result:

```bash
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

## Guarded persistent installation

For Pluto+, update only the `qspi-linux` firmware partition. Never use a full
firmware ZIP, `boot.frm`, `boot.dfu`, or `uboot-env.dfu`.

Identify one directly attached radio by exact USB serial and sysfs topology,
stop every process using it, and run the flash command once without `--execute`:

```bash
uv run pluto firmware flash \
  /absolute/path/plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.dfu \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-ring-v1-release-persistent-promotion
```

The plan must show the intended serial, exact DFU SHA-256 `ac51893d...`, FIT
SHA-256 `8dc973cd...`, target v0.46 identity, qualified prior-version policy,
and firmware-partition-only operation. If any value differs, stop.

Execute that same plan only with its exact confirmation phrase:

```bash
uv run pluto firmware flash \
  /absolute/path/plutoplus-spf-iq-direct-async-ring-v1-f182a8fa0811-pluto.dfu \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-ring-v1-release-persistent-promotion \
  --execute --confirm 'FLASH EXACT_SERIAL'
```

Keep the durable receipt. Do not retry an uncertain post-eject operation. After
the radio returns, pin its SSH host key and use the read-only reconciliation
command to attest the active identity and hash exactly the recorded FIT length
from `/dev/mtd3`:

```bash
uv run pluto firmware reconcile-local RECEIPT_ID \
  --usb-sysfs-path /sys/bus/usb/devices/EXACT_PATH \
  --profile iq-direct-async-ring-v1-release-persistent-promotion \
  --ssh-known-hosts-file /absolute/private/path/radio.known_hosts \
  --ssh-host RADIO_ADDRESS
```

Reconciliation never writes QSPI, changes RF state, or reboots. A mismatch is
a stop condition, not permission to replay the flash.

## Functional ladder and acceptance tests

The one-command ringless speed matrix uses the requested 5/10/15/25 MS/s rates
for 3 and 10 seconds:

```bash
uv run pluto radio direct-async-ladder RADIO_ADDRESS \
  --transport ip --expect-serial EXACT_SERIAL \
  --rates 5M,10M,15M,25M --durations 3,10 \
  --samples 1048576 --kernel-buffers 15 \
  --iq-decoder raw-complex64 \
  --format json --report /ABSOLUTE/PRIVATE/PATH/ringless-ladder.json
```

Run the same matrix with 13 RAM slots extending a 10-descriptor DMA queue:

```bash
uv run pluto radio direct-async-ladder RADIO_ADDRESS \
  --transport ip --expect-serial EXACT_SERIAL \
  --rates 5M,10M,15M,25M --durations 3,10 \
  --samples 1048576 --kernel-buffers 10 --ram-ring-slots 13 \
  --iq-decoder raw-complex64 \
  --format json --report /ABSOLUTE/PRIVATE/PATH/ram-extension-ladder.json
```

The ladder must execute all eight cells, restore the complete RX configuration,
and report counter-observed gaps rather than conceal them. Sustained 25 MS/s
offers 100 MB/s and outruns this 1-GbE path, so gaps in those duration cells are
expected. The separate hard throughput/continuity gate is three independent
finite 23-frame captures at 30.72 MS/s, 1,048,576 samples per frame, 15 DMA
buffers, RAM disabled, and `raw-complex64`; require at least 70 MB/s and zero
counter gaps in every run.

Also require:

- combined direct mode actually spills and drains RAM frames in equal counts;
- standalone finite ring reaches its requested target, drains completely, and
  preserves frame order across a wrap;
- two deliberate large-ring client losses recover without Linux or iiOD
  restart and leave zero buffers/faults with DDS off and TX at -80 dB; and
- 5.8 GHz LO tune/readback succeeds on AD9361 and restores the exact prior LO.

The exact hardware results and limitations are recorded in
[`RELEASE_IQ_DIRECT_ASYNC_RING_V1.md`](RELEASE_IQ_DIRECT_ASYNC_RING_V1.md).

## Source-build verification

Before reproducing the protected build, verify the pins:

```bash
git -C /PATH/TO/plutosdr-fw rev-parse HEAD
git -C /PATH/TO/plutosdr-fw ls-tree HEAD buildroot
git -C /PATH/TO/plutosdr-buildroot rev-parse HEAD
git -C /PATH/TO/libiio rev-parse HEAD
git -C /PATH/TO/pluto-plus-utils rev-parse HEAD
```

Expected firmware binary source is `f182a8fa...`; Buildroot is `a9292672...`;
libiio is `b7303fde...`; and host `main` contains `d3e5cfeb...`. Build with
Vivado 2022.2 and the pinned Linaro toolchain, supplying the exact protected
identity:

```bash
cd /PATH/TO/plutosdr-fw
RELEASE_VERSION=v0.46-plutoplus-spf-iq-direct-async-ring-v1 \
  make build/pluto.dfu
```

Any implementation-pin change requires a new protected build and complete
hardware requalification.

## Rollback

Retain the previous hardware-qualified DFU/FRM and its checksum/profile until
all post-install tests pass. Roll back only the firmware partition using that
release's own exact guarded persistent profile. Never rewrite the Pluto+
bootloader or U-Boot environment as part of a routine firmware rollback.
