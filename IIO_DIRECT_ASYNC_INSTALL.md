# Direct-async IQ source and installation requirements

This document is the compatibility and installation record for the
`iq-direct-async-ring-v1-rc1-source` candidate. It supplements
[`flashing.md`](flashing.md); the safety rules in that guide still apply.

## Current status

The implementation is source- and hardware-qualified, but it is not an
installable firmware release yet:

- no firmware release version has been assigned;
- no version-stamped `pluto.frm` or `pluto.dfu` exists;
- the proposed immutable libiio tag has not been published;
- the branches and commits remain local and unmerged; and
- persistent QSPI installation has not been authorized.

Do not flash an ordinary branch build. The hardware qualification used an
exact ARM iiOD and shared library from `/tmp`, leaving the installed firmware
and system library unchanged. Those volatile binaries proved the source but
are not a release package.

## Required component matrix

The commits below are a matched set. Substituting upstream libiio, a different
Python binding, or an older ABI-3 runtime is unsupported.

| Layer | Package/version | Required ref or commit | Why it is pinned |
| --- | --- | --- | --- |
| firmware integration | PlutoSDR firmware source; release version unassigned | implementation commit `a5253497d15613831055dbfb543ca5a9936bd2c6` on `codex/iq-direct-async-main-refresh` | pins the Buildroot graph and records the qualified interface |
| firmware base | `origin/main` as of 2026-08-31 | `4f15c87033e332293711ad679a50af0109c72862` | current-main rebase point used for qualification |
| Buildroot | PlutoSDR Buildroot fork | `4a1e90704706756a6f6062482a070e63f9b27573` on `codex/iq-direct-async-main-refresh-buildroot` | selects the exact radio-side libiio and metadata provider |
| radio iiOD/libiio | libiio API/SONAME line 0.25 | `b7303fded264e10473bbbb084afade8f1b1373d1` on `codex/iq-direct-async-main-refresh-libiio` | unified DMA/RAM FIFO and three-period spill headroom |
| immutable libiio ref | proposed source tag | `iq-direct-async-ring-v1-rc1-source/libiio-v1` resolving exactly to `b7303fded264e10473bbbb084afade8f1b1373d1` | required by the receipt-writing host installer; currently unpublished |
| metadata provider | SPF metadata ABI 3 / strict `RadioMetadataV6` | `3294365ff44da26b261be4a2ccb241b7896d23ad` | frame counter, gap, gain, and RSSI provider compiled into iiOD |
| host application | `pluto-plus-utils` package 0.1.0, Python 3.11 or newer | implementation commit `55e3c08ecf703c2a2f6b5367b3e3d64644c58c1a` on `codex/iq-direct-async-main-refresh-host` | API, fail-closed admission, status parsing, and finite-ring anchor handling |
| host native library | libiio 0.25 | the same `b7303fded264e10473bbbb084afade8f1b1373d1` | implements the host side of `READBUFMA` and ring-extension request |
| host Python binding | generated `pylibiio` from libiio 0.25 | the same `b7303fded264e10473bbbb084afade8f1b1373d1` | exposes the exact `MetadataBuffer(..., direct_async_frames=...)` signature |

The complete firmware gitlink set at the qualified integration commit is:

| Firmware component | Commit |
| --- | --- |
| Buildroot | `4a1e90704706756a6f6062482a070e63f9b27573` |
| HDL | `145bd47e55d5c5537e0ba49d53cb25a5393f66ba` |
| HDL Quantulum | `364b3dc7e770c3971d1f41a75c00e6cae76e2e6d` |
| Linux | `93174a1c049ca6ee42f042dbe93f0fb06fbc9cd7` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a` |

The firmware Makefile requires Vivado 2022.2. Its x86-64 Buildroot path uses
the pinned Linaro 2018.05 `arm-linux-gnueabihf` toolchain. Do not silently
replace either toolchain in a release build.

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

The current Pluto USB startup script does not itself encode `-r 1`. A final
release must either integrate that option into the intended network iiOD
service or document and qualify a separate managed service. Do not run a
second iiOD against the same IIO device while the stock service owns it.

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

Expected values are Buildroot `4a1e9070...`, libiio `b7303fde...`,
metadata provider `3294365f...`, and a host tree containing implementation
commit `55e3c08e...`. A later documentation-only descendant is acceptable;
changing any implementation pin requires rebuilding and repeating the
qualification.

## Publication and firmware build order

The order matters:

1. Publish the immutable libiio source ref and verify that it resolves exactly
   to `b7303fded264e10473bbbb084afade8f1b1373d1`.
2. Make that commit fetchable by the Buildroot recipe. Until it is reachable
   from `misko/libiio`, a clean Buildroot download is expected to fail.
3. Add and review a source-lock manifest for this exact graph and a matching
   protected packaging route. The current release script has no
   `iq-direct-async-ring-v1-rc1-source` route and must reject it.
4. Build the exact firmware source graph with Vivado 2022.2 and the pinned
   Buildroot toolchain, using the clone-depth and architecture rules in
   [`BUILD.md`](BUILD.md).
5. Assign a new, reviewed firmware version through `RELEASE_VERSION`. Do not
   use `a5253497d` or the feature name as the on-radio `device-fw` value.
6. Verify the packaged `/opt/VERSIONS`, source manifest, image checksums, and
   exact libiio identity.
7. RAM-boot the final version-stamped image and repeat the direct, combined,
   standalone-ring, recovery, and RF-restoration gates.
8. Publish an image only after those final bytes pass. Persistent flashing is
   a separate approval.

After the protected environment has resolved and checked the exact gitlinks,
the firmware-partition build entry point is:

```bash
cd /ABSOLUTE/PATH/TO/plutosdr-fw-iq-direct-async-main-refresh
RELEASE_VERSION=REVIEWED_EXACT_VERSION make build/pluto.dfu
```

`REVIEWED_EXACT_VERSION` is deliberately a placeholder. No release version
was selected by this work. Follow [`RELEASING.md`](RELEASING.md) for the
source-lock, packaging, and provenance gates.

## Install the matched host runtime

This procedure becomes usable only after the immutable libiio ref is
published. Before that point, the installer must fail rather than fall back to
another commit.

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

## Qualification binary identities

The volatile qualification used these ARM32 EABI5 files built from exact
`b7303fd`:

| File | SHA-256 |
| --- | --- |
| `iiod` | `89c5eae83b7bb517279ebe97e3300615c58efbf3892dc9d6939966429122e01d` |
| `libiio.so.0.25` | `8fd0530bd712abe6398f300c17c34052a3e86acfbf374680071869f260921841` |

These hashes are evidence for the source qualification only. A future firmware
release must publish its own image, FIT-body, rootfs, manifest, and component
hashes; do not copy these two values into a release asset manifest.

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
