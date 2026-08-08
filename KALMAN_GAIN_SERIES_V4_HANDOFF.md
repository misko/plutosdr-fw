# Kalman handoff: build and publish the gain-series v4 candidate

This document is the runbook for an agent working on `kalman`, an x86-64
machine with Vivado 2022.2 but **no Pluto hardware**. Its job is to compile the
pinned FPGA and firmware sources, validate everything that can be validated
offline, and publish an immutable **release candidate** for hardware testing.

The candidate adds protocol-v3 gain observations and GNSS-free frame timing.
The frame carries the exact 64-bit RX sample counter. The same counter's low
word is exposed coherently to the Pluto ARM at `0x800000B8`, allowing USB and
IP time-anchor requests to map sample boundaries onto the Pi monotonic clock.

## Authority boundary

Kalman can prove that:

- the published source graph is complete and pinned;
- the counter clock-domain crossing passes simulation;
- Vivado builds the intended block design and bitstream;
- Buildroot cross-compiles the USB and IP gadgets;
- the DFU is structurally sound and contains the expected files;
- the exact candidate bytes and provenance are published without alteration.

Kalman cannot prove that:

- register `0x800000B8` advances on a PlutoPlus;
- the register low word agrees with the inline 64-bit frame counter;
- USB or IP timing uncertainty is at most 5 ms;
- IQ layout, gain observations, throughput, restart recovery, or dual-radio
  operation work on hardware;
- the image is safe for persistent QSPI deployment.

Therefore, publish a GitHub **prerelease candidate**, not a production release.
Do not update SPF rover configurations, do not mark the release `latest`, and
do not call the candidate rover-approved. Hardware promotion is a separate
gate described at the end of this document.

## Authoritative source graph

The complete hashes live in
`manifests/gain-series-v4-source.yaml`. The expected component heads are:

| Component | Commit |
|---|---|
| Buildroot | `e57349dce9d67e0dc4b7a9f9dd23bbc0fad082d1` |
| USB/common gadget | `518e35914195136e20c9f7261b21ee063b41d994` |
| IP gadget | `032c830c76cb291c2ed0a32b455ed81d1dfd2540` |
| ADI HDL | `4e9d712403afda1393873228e2df3834073d663d` |
| Quantulum timestamp HDL | `e663136ed7f21e1596c38305cd34745019123d05` |
| Linux | `d798b0d821b85ebd51ecffbfa68d8e4d69b77132` |
| U-Boot | `1ff0468e9bea29b0a768a7bf52db8d025c521b9a` |

Build the head of `codex/firmware-gain-series-v4`. Record its full commit in
the provenance file; do not substitute `master`, the old timestamp branch, or
an older released XSA.

## 1. Check the host

Vivado 2022.2 is already installed on Kalman. Start a clean shell and verify
the architecture and tool version:

```bash
uname -m
source /opt/Xilinx/Vivado/2022.2/settings64.sh
vivado -version
ldconfig -p | grep 'libtinfo\.so\.5'
```

Pass conditions:

- `uname -m` prints `x86_64`;
- the first Vivado line contains `Vivado v2022.2`;
- `libtinfo.so.5` resolves successfully.

Vitis/XSCT is not required to build `pluto.dfu`. Do not broaden the task into
building or flashing bootloader partitions.

Install missing open-source build dependencies if preflight reports them:

```bash
sudo apt-get update
sudo apt-get install -y \
  bc bison build-essential ccache cmake cpio device-tree-compiler dfu-util \
  fakeroot flex git gzip iverilog libaio-dev libiio-dev libncurses-dev libssl-dev \
  mtools patch perl python3 rsync u-boot-tools unzip wget zip
```

Use at least 40 GiB of free local disk. Build in a local filesystem rather
than directly in a network-mounted artifact directory.

## 2. Create an isolated candidate checkout

Do not build in Kalman's existing `main` checkout. It may contain a prior XSA,
Buildroot output, or `local.mk` source override, and switching it would disturb
other work. Keep `main` where it is and create a separate Git worktree.

### Preferred path when the repository already exists on Kalman

From the existing clone, first confirm that its current work is left alone:

```bash
cd /path/to/the/existing/plutosdr-fw
git status --short --branch
git remote -v
```

Do not clean, reset, stash, or switch that checkout. Fetch the candidate into a
dedicated remote-tracking reference and create a detached worktree:

```bash
git fetch https://github.com/misko/plutosdr-fw.git \
  codex/firmware-gain-series-v4:refs/remotes/misko/codex/firmware-gain-series-v4

mkdir -p "$HOME/gits"
git worktree add --detach "$HOME/gits/plutosdr-fw-gain-series-v4" \
  refs/remotes/misko/codex/firmware-gain-series-v4

cd "$HOME/gits/plutosdr-fw-gain-series-v4"
git submodule sync --recursive
git submodule update --init --recursive
```

Detached HEAD is intentional for a build workspace. It prevents the build
agent from accidentally advancing or pushing a local branch. The later release
tag is created explicitly at the recorded source commit.

### Alternative when no checkout exists

Only use a fresh clone if Kalman does not already have the repository:

```bash
mkdir -p "$HOME/gits"
cd "$HOME/gits"
git clone --branch codex/firmware-gain-series-v4 --recurse-submodules \
  https://github.com/misko/plutosdr-fw.git plutosdr-fw-gain-series-v4
cd plutosdr-fw-gain-series-v4
git submodule sync --recursive
git submodule update --init --recursive
```

Record the exact source before doing anything else:

```bash
git rev-parse HEAD
git status --short --branch
git submodule status --recursive
```

Pass conditions:

- `HEAD` equals the remote `codex/firmware-gain-series-v4` commit;
- the tracked worktree is clean;
- no submodule status line starts with `-`, `+`, or `U`;
- the component hashes match the table above and the source manifest.

Verify the first condition without relying on a local branch name:

```bash
test "$(git rev-parse HEAD)" = "$(git ls-remote \
  https://github.com/misko/plutosdr-fw.git \
  refs/heads/codex/firmware-gain-series-v4 | awk '{print $1}')"
```

Never use `git submodule update --remote`; it changes the pinned source graph.

## 3. Run source and HDL simulation gates

Create an artifact directory outside the checkout so logs do not dirty the
firmware tree:

```bash
export SPF_FW_ARTIFACT_ROOT="$HOME/firmware-artifacts/gain-series-v4-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$SPF_FW_ARTIFACT_ROOT"
set -euo pipefail
scripts/build_gain_series_candidate.sh source-check \
  2>&1 | tee "$SPF_FW_ARTIFACT_ROOT/source-check.log"
scripts/build_gain_series_candidate.sh preflight \
  2>&1 | tee "$SPF_FW_ARTIFACT_ROOT/preflight.log"
TMPDIR="$SPF_FW_ARTIFACT_ROOT" scripts/test_gain_series_hdl.sh \
  2>&1 | tee "$SPF_FW_ARTIFACT_ROOT/hdl-simulation.log"
```

Pass conditions:

- source check ends with `SOURCE GRAPH OK`;
- the HDL simulation reports `PASS` and at least 20 coherent counter updates;
- preflight reports the expected manifest and all host-side dependencies;
- `git status --porcelain --untracked-files=no` remains empty.

The `image` gate checks Vivado 2022.2 immediately before the FPGA build. The
plain `preflight` mode deliberately does not invoke Vivado.

Stop on any failure. Do not edit generated IP checksums, source pins, or the
manifest merely to make a check pass.

## 4. Build the FPGA and DFU

The image command cleans and rebuilds the pinned Pluto HDL, copies the newly
generated `system_top.xsa`, and then builds `build/pluto.dfu`:

```bash
source /opt/Xilinx/Vivado/2022.2/settings64.sh
time scripts/build_gain_series_candidate.sh image \
  2>&1 | tee "$SPF_FW_ARTIFACT_ROOT/image-build.log"
```

Do not pass `XSA_URL` and do not copy in the XSA from
`v0.38_plutoplus_with_timestamping`. That older bitstream does not expose the
counter to the ARM and causes protocol v3 to fail closed.

Required outputs:

```text
hdl/projects/pluto/pluto.sdk/system_top.xsa
build/system_top.xsa
build/system_top.bit
build/rootfs.cpio.gz
build/pluto.dfu
```

The two XSA paths must contain the same bytes:

```bash
sha256sum \
  hdl/projects/pluto/pluto.sdk/system_top.xsa \
  build/system_top.xsa
cmp \
  hdl/projects/pluto/pluto.sdk/system_top.xsa \
  build/system_top.xsa
test -s build/system_top.bit
test -s build/rootfs.cpio.gz
test -s build/pluto.dfu
```

Pass conditions:

- Vivado does not report an error, locked IP, stale
  `util_cpack2_timestamp`, or missing `timestamp_cpu` port;
- `cpack_timestamp/timestamp_cpu` connects to
  `axi_ad9361/up_adc_gpio_in`;
- implementation completes and timing constraints are met;
- every required output exists and is non-empty;
- the build command exits zero.

Preserve all Vivado logs. A convenient bundle is:

```bash
tar -C hdl/projects/pluto -czf \
  "$SPF_FW_ARTIFACT_ROOT/vivado-logs.tar.gz" \
  vivado.log vivado.jou pluto.runs
```

Warnings must be reviewed in context. Do not suppress CDC, timing, IP-lock, or
unconnected-port warnings involving the timestamp block.

## 5. Validate the package without hardware

Copy artifacts under candidate-specific names:

```bash
export SPF_FW_RC=rc1
export SPF_FW_STEM="plutoplus-spf-gain-series-v4-${SPF_FW_RC}"
cp build/pluto.dfu "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-pluto.dfu"
cp build/system_top.xsa "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-system_top.xsa"
cp build/rootfs.cpio.gz "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-rootfs.cpio.gz"
dfu-suffix -c "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-pluto.dfu"
dumpimage -l "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-pluto.dfu" \
  | tee "$SPF_FW_ARTIFACT_ROOT/fit-layout.txt"
unzip -l "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-system_top.xsa" \
  | tee "$SPF_FW_ARTIFACT_ROOT/xsa-layout.txt"
unzip -p "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-system_top.xsa" system_top.bit \
  | sha256sum | tee "$SPF_FW_ARTIFACT_ROOT/system-top-bit.sha256"
```

The DFU suffix must report vendor `0x0456`, product `0xB673`, and length 16.
The FIT must contain three device trees, one FPGA image, one Linux kernel, and
one gzip ramdisk. The XSA must contain `system_top.bit`.

Extract the packaged root filesystem rather than trusting the build directory:

```bash
mkdir -p "$SPF_FW_ARTIFACT_ROOT/rootfs-check"
ramdisk_index="$(awk '$1 == "Image" && $3 == "(ramdisk@1)" {print $2}' \
  "$SPF_FW_ARTIFACT_ROOT/fit-layout.txt")"
test -n "$ramdisk_index"
dumpimage -T flat_dt -p "$ramdisk_index" \
  -o "$SPF_FW_ARTIFACT_ROOT/packed-rootfs.cpio.gz" \
  "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-pluto.dfu"
(
  cd "$SPF_FW_ARTIFACT_ROOT/rootfs-check"
  gzip -dc ../packed-rootfs.cpio.gz | cpio -idm
)
cat "$SPF_FW_ARTIFACT_ROOT/rootfs-check/opt/VERSIONS" \
  | tee "$SPF_FW_ARTIFACT_ROOT/packed-VERSIONS.txt"
file \
  "$SPF_FW_ARTIFACT_ROOT/rootfs-check/usr/sbin/sdr_usb_gadget" \
  "$SPF_FW_ARTIFACT_ROOT/rootfs-check/usr/sbin/sdr_ip_gadget"
```

Both gadget binaries must be 32-bit ARM EABI executables. `opt/VERSIONS` must
identify the candidate superproject and the pinned HDL, Linux, U-Boot, and
Buildroot sources. Keep its exact text; hardware acceptance uses it as
provenance.

Create checksums only after every file has its final name:

```bash
(
  cd "$SPF_FW_ARTIFACT_ROOT"
  sha256sum \
    "${SPF_FW_STEM}-pluto.dfu" \
    "${SPF_FW_STEM}-system_top.xsa" \
    "${SPF_FW_STEM}-rootfs.cpio.gz" \
    vivado-logs.tar.gz \
    > SHA256SUMS
  sha256sum -c SHA256SUMS
)
```

## 6. Record provenance

Produce a plain-text sidecar that remains readable without a custom parser:

```bash
{
  echo "release_state=candidate"
  echo "hardware_tested=false"
  echo "source_branch=codex/firmware-gain-series-v4"
  echo "firmware_source=$(git rev-parse HEAD)"
  echo "build_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "builder_host=$(hostname)"
  echo "builder_arch=$(uname -m)"
  vivado -version | sed -n '1,3p'
  echo
  echo '[submodules]'
  git submodule status --recursive
  echo
  echo '[artifacts]'
  cat "$SPF_FW_ARTIFACT_ROOT/SHA256SUMS"
  echo "system_top.bit $(awk '{print $1}' "$SPF_FW_ARTIFACT_ROOT/system-top-bit.sha256")"
  echo
  echo '[packaged /opt/VERSIONS]'
  cat "$SPF_FW_ARTIFACT_ROOT/packed-VERSIONS.txt"
} | tee "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-provenance.txt"
```

Also save the clean-tree proof:

```bash
git status --short --branch \
  | tee "$SPF_FW_ARTIFACT_ROOT/git-status.txt"
test -z "$(git status --porcelain --untracked-files=no)"
```

## 7. Publish an immutable prerelease candidate

Authenticate without placing a token in the repository or logs:

```bash
gh auth status
gh auth setup-git
export SPF_FW_PUBLISH_REPO="https://github.com/misko/plutosdr-fw.git"
```

Use a new RC number if `rc1` already exists. Never overwrite or delete an RC
whose bytes were handed to hardware testing.

```bash
export SPF_FW_TAG="v0.38-plutoplus-spf-gain-series-v4-${SPF_FW_RC}"
if git ls-remote --exit-code --tags "$SPF_FW_PUBLISH_REPO" \
  "refs/tags/${SPF_FW_TAG}" >/dev/null 2>&1; then
  echo "Tag already exists; choose a new RC number" >&2
  exit 1
fi
```

Create release notes containing this warning at the top:

```text
UNPROMOTED RELEASE CANDIDATE — RAM BOOT ONLY

This image was compiled and validated offline on Kalman. No Pluto hardware was
available. It must not be written to QSPI or selected by rover production
configuration until the SPF two-radio hardware promotion campaign passes.
```

Write those notes, plus the exact source and DFU hash, to the file consumed by
the release command:

```bash
cat >"$SPF_FW_ARTIFACT_ROOT/release-notes.md" <<EOF
UNPROMOTED RELEASE CANDIDATE — RAM BOOT ONLY

This image was compiled and validated offline on Kalman. No Pluto hardware was
available. It must not be written to QSPI or selected by rover production
configuration until the SPF two-radio hardware promotion campaign passes.

Firmware source: $(git rev-parse HEAD)
DFU SHA-256: $(sha256sum "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-pluto.dfu" | awk '{print $1}')

See the attached provenance file, SHA256SUMS, and Vivado logs. Hardware status:
UNTESTED.
EOF
```

Then tag the exact source that produced the bytes and create a draft
prerelease:

```bash
git tag -a "$SPF_FW_TAG" "$(git rev-parse HEAD)" \
  -m "Gain-series v4 ${SPF_FW_RC} hardware-test candidate"
git push "$SPF_FW_PUBLISH_REPO" "$SPF_FW_TAG"

gh release create "$SPF_FW_TAG" \
  --repo misko/plutosdr-fw \
  --verify-tag \
  --draft \
  --prerelease \
  --title "PlutoPlus SPF gain-series v4 ${SPF_FW_RC} (RAM-test candidate)" \
  --notes-file "$SPF_FW_ARTIFACT_ROOT/release-notes.md" \
  "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-pluto.dfu" \
  "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-system_top.xsa" \
  "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-rootfs.cpio.gz" \
  "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-provenance.txt" \
  "$SPF_FW_ARTIFACT_ROOT/SHA256SUMS" \
  "$SPF_FW_ARTIFACT_ROOT/vivado-logs.tar.gz"
```

Review the draft asset names and hashes. Download into a new directory and
compare every downloaded asset to the local candidate before publishing the
draft:

```bash
VERIFY_DIR="$(mktemp -d)"
gh release download "$SPF_FW_TAG" --repo misko/plutosdr-fw --dir "$VERIFY_DIR"
cmp "$SPF_FW_ARTIFACT_ROOT/SHA256SUMS" "$VERIFY_DIR/SHA256SUMS"
cmp \
  "$SPF_FW_ARTIFACT_ROOT/${SPF_FW_STEM}-provenance.txt" \
  "$VERIFY_DIR/${SPF_FW_STEM}-provenance.txt"
(
  cd "$VERIFY_DIR"
  sha256sum -c SHA256SUMS
)
```

Only after this comparison passes, make it a visible prerelease while keeping
it non-latest:

```bash
gh release edit "$SPF_FW_TAG" \
  --repo misko/plutosdr-fw \
  --draft=false \
  --prerelease
```

Publishing the candidate is not production promotion. Do not create or edit a
production manifest and do not modify SPF capture configurations from Kalman.

## 8. Handoff back to the hardware agent

Report all of the following:

- GitHub prerelease URL and tag;
- firmware source commit;
- DFU filename, byte size, and SHA-256;
- XSA and bitstream SHA-256;
- exact `opt/VERSIONS` contents;
- Vivado version;
- implementation timing result, including WNS;
- any critical warnings and their disposition;
- total build duration;
- `SHA256SUMS` and provenance sidecar.

The hardware agent must download by tag, verify SHA-256, and run from the SPF
repository:

```bash
tests/radio_hardware/run_gain_series_v3_candidate.sh \
  /absolute/path/to/plutoplus-spf-gain-series-v4-rc1-pluto.dfu \
  DIRECT_IP_HOST
```

That campaign RAM-boots exactly two radios and checks protocol-v2
compatibility, protocol-v3 USB, the common IP frame, exact counter identity,
time uncertainty, a 100-frame V7 Zarr, and dual-radio operation. QSPI promotion
and rover pin changes occur only after the RAM campaign and restart soak pass.

## Failure policy

- If source, simulation, Vivado, timing, packaging, or checksum verification
  fails, do not publish an asset.
- If a draft was created but downloaded bytes do not match, leave it as a
  draft, record the failure, and diagnose it. Do not use `--clobber`.
- If hardware later rejects an RC, retain the release and mark it rejected in
  its notes. Create a new RC for changed bytes.
- Never force-push the candidate branch or move a published tag.
- Never claim UTC accuracy: the protocol maps samples to the Pi clocks and
  reports uncertainty; it has no GNSS or PPS reference.
