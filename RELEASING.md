# Cutting a full release

A release candidate and a full release differ in one respect that cannot be
fixed after the fact: **the version string is baked into the image at build
time.** `/opt/VERSIONS` records `device-fw`, that is what a radio reports about
itself, and that is what `scripts/verify_release.sh` reads back.

## The failure this procedure exists to prevent

`device-fw` came from `git describe --abbrev=4 --dirty --always --tags`. The
release tag does not exist while the build is running, so the derived string
names the **previous** release. This has shipped twice:

| Release | stamped | should have read |
|---|---|---|
| `...-gain-rssi-fingerprint-v3` | `...-fingerprint-v2-8-gf53d` | `...-fingerprint-v3` |
| `...-gain-series-v4-rc17` | `...-gain-series-v4-rc16-7-g1f3fe` | `...-v4-rc17` |

The second is the worse of the two: RC16 is the release RC17 exists to
supersede, so a fleet audit reading `device-fw` concludes the radios are running
the version with the control-rearm failure.

Both times the wrong string was sitting in the build's own
`packed-VERSIONS.txt`, printed in the validation summary, unread. The v3
manifest even diagnosed it and prescribed the fix — "tagging (annotated) before
building" — which was then not applied.

`verify_release.sh` cannot catch this. It compares the DFU against a manifest
written afterwards *from whatever the DFU says*, so it detects tampering, not
mislabelling.

## The mechanism

`RELEASE_VERSION` states the string instead of deriving it:

- `Makefile` — `VERSION` is `RELEASE_VERSION` when set, `git describe` otherwise.
  Development builds are unchanged.
- `scripts/build_gain_series_candidate.sh` — passes it to `make` on the command
  line, so it beats the Makefile default unconditionally.
- `scripts/ci/package_main_firmware.sh` — **fails the build** if the packaged
  `device-fw` is not exactly `RELEASE_VERSION`. With no pin set it still refuses
  a dirty tree and prints a note when the string is not an exact tag.
- `.github/workflows/firmware-main.yml` — `workflow_dispatch` input
  `release_version`, and the stamped string appears in the job summary.

## Procedure

1. **Decide the name.** The line runs `gain-rssi-v2` →
   `gain-rssi-fingerprint-v1/v2/v3` → `gain-series-v4`. Drop the `-rcNN`; keep
   the `v0.38` upstream base.

2. **Dispatch the build** with `release_version` set to the exact name. Do not
   tag first — if the build or its testing fails you would have to move a
   version tag, and tagging is not what makes the string correct.

   A manual dispatch may target **any branch**, so a release candidate can be
   built and hardware-tested before it is merged. Prefer that order: RC17 was
   merged to main and qualified afterwards, which is how main came to carry a
   candidate that had never been on a radio.

   ```sh
   gh workflow run firmware-main.yml --ref <branch> \
     -f release_version=v0.38-plutoplus-spf-gain-series-v5-rc1
   ```

3. **Verify the stamp.** The job summary shows `device-fw`. To confirm from the
   artifact itself:

   ```sh
   gh release download <tag> -p '*rootfs.cpio.gz' -D /tmp/rf
   ( cd /tmp/rf && gzip -dc *rootfs.cpio.gz | cpio -idm --quiet && cat opt/VERSIONS )
   ```

4. **Hardware-qualify these exact bytes.** A rebuild for the name change is
   byte-different from the RC that was qualified, so the RC's campaign does not
   transfer literally. When the only delta is the version string, a confirmation
   pass — boot, TX2 loopback on both radios, one protocol-v3 stream run — covers
   the real risk, which is build-environment drift rather than a code change.

5. **Tag, annotated, on the built commit.** Annotated, not lightweight: `rc16`
   is lightweight and `rc17` is not, and the inconsistency is worth ending.

   ```sh
   git tag -a v0.38-plutoplus-spf-gain-series-v4 <commit> -m '...'
   git push origin v0.38-plutoplus-spf-gain-series-v4
   ```

6. **Publish the exact artifacts** from step 2 as a non-prerelease. Never
   rebuild between qualification and publication.

7. **Write the release manifest**, `manifests/<name>.yaml`, with the five fields
   `verify_release.sh` requires: `release_tag`, `asset_name`, `image_url`,
   `image_sha256`, `device_fw`. Take `device_fw` from the extracted rootfs, not
   from what you expect it to say. These manifests are immutable — a new release
   gets a new file.

8. **Verify against the published asset**, not the local build:

   ```sh
   scripts/verify_release.sh manifests/<name>.yaml
   ```
