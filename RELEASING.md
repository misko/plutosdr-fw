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

## Current tandem RC4 gate

RC2 exposed two release blockers: a closed tandem session could report IDLE
while leaving event records inaccessible in the FPGA FIFO, and the synchronous
host metadata request/response cadence could lose a full 65,536-sample frame
without a device-overflow indication. RC3 advanced the Linux RELEASE cleanup,
the bounded libiio batch transport, and the matching Buildroot recipe pin, but
hardware qualification found a top-level RTL request/pulse handoff bug at zero
cooldown. RC4 retains RC3's external component pins and corrects that tracked
top-level RTL. It cannot inherit RC3's failed hardware result. Its exact source
graph is `manifests/tandem-agc-v8-rc4-source.yaml`; its trusted build branch is
`codex/firmware-tandem-agc-v8-rc4`; and its requested device string is
`v0.41-plutoplus-spf-tandem-agc-v8-rc4`.

Protected dependency source locks must exist before the build so CI can resolve
and pack them. They are not release tags. Do not create the annotated
`v0.41-plutoplus-spf-tandem-agc-v8-rc4` release tag until the exact attested RC4
artifact completes the full four-radio RAM qualification. Never move or reuse
the failed RC3 source lock, an existing candidate lock, or a release tag.

## Procedure

1. **Decide the name.** Drop the candidate's `-rcNN`, keep the intended
   upstream-version prefix, and verify that neither the tag nor release already
   exists. For the current tandem promotion the exact name is
   `v0.41-plutoplus-spf-tandem-agc-v8`.

2. **Dispatch the build** from `main` with `release_version` set to the exact
   name. Do not tag first — if the build or its testing fails you would have to
   move a version tag, and tagging is not what makes the string correct.

3. **Download and verify the Actions artifact.** No GitHub release exists yet;
   qualification must use the artifact from the exact workflow run in step 2,
   never `gh release download`. Record the intended 40-character `main` commit,
   the run ID, and the run attempt. Confirm that the run's `headSha` is that
   commit, then verify the bundle sidecar, internal checksums, attestation, and
   packed `/opt/VERSIONS`:

   ```sh
   release_run_id=<run-id>
   release_commit=<40-character-main-commit>
   release_attempt=<attempt>
   release_artifact="plutoplus-main-${release_commit}-${release_run_id}-${release_attempt}"
   release_work=$(mktemp -d)

   test "$(gh run view "$release_run_id" --repo misko/plutosdr-fw \
     --json headSha --jq .headSha)" = "$release_commit"
   gh run download "$release_run_id" --repo misko/plutosdr-fw \
     --name "$release_artifact" --dir "$release_work"
   (
     cd "$release_work"
     sha256sum -c ./*.tar.gz.sha256
     mkdir extracted
     tar -xzf ./*.tar.gz -C extracted
     cd extracted
     sha256sum -c SHA256SUMS
     mkdir rootfs
     cd rootfs
     gzip -dc ../*-rootfs.cpio.gz | cpio -idm --quiet opt/VERSIONS
     cat opt/VERSIONS
   )
   gh attestation verify "$release_work"/*.tar.gz \
     --repo misko/plutosdr-fw
   ```

   The printed `device-fw` must equal the requested release name. The four
   packed component identities must equal the `versions_*` values in the source
   manifest.

4. **Hardware-qualify these exact bytes.** A rebuild for the name change is
   byte-different from the RC that was qualified, so the RC's campaign does not
   transfer literally. When the only delta from a fully qualified RC is the
   version string, a confirmation pass — boot, TX2 loopback on every
   release-gate radio, and one protocol-v3 stream run — covers the real risk,
   which is build-environment drift. RC4 is not such a candidate: it carries
   RC3's Linux cleanup and libiio batch transport plus the corrected tandem RTL,
   so it requires the full campaign before merge. Only the subsequent final
   build may use the reduced confirmation pass if its sole functional delta
   from qualified RC4 is the stamped version.

5. **Tag, annotated, on the built commit.** Annotated, not lightweight: `rc16`
   is lightweight and `rc17` is not, and the inconsistency is worth ending.

   ```sh
   git tag -a v0.41-plutoplus-spf-tandem-agc-v8 <commit> -m '...'
   git push origin v0.41-plutoplus-spf-tandem-agc-v8
   ```

6. **Publish the exact artifacts** from step 2 as a non-prerelease. Never
   rebuild between qualification and publication.

7. **Write the release manifest**, `manifests/<name>.yaml`, from the exact
   published asset. `scripts/verify_release.sh` currently requires exactly
   these 17 non-empty fields:

   - release identity: `release_tag`, `asset_name`, `image_url`,
     `image_sha256`, `device_fw`;
   - source identity: `firmware_source`, `gadget_source`,
     `submodule_buildroot`, `submodule_linux`, `submodule_u_boot_xlnx`;
   - packed identities: `versions_hdl`, `versions_buildroot`,
     `versions_linux`, `versions_u_boot_xlnx`; and
   - shipped structure: `fpga_bitstream_md5`, `ramdisk_md5`,
     `fit_description`.

   Current manifests also record repository URLs and refs, libiio, HDL,
   timestamp-HDL and IP-gadget pins, bundle/FIT/rootfs SHA-256 values, the CI
   run, and hardware-qualification evidence. Those additional provenance
   fields are expected for a new release even though the verifier does not yet
   consume all of them. Take `device_fw` and every hash from the
   built/published bytes, not from expected values. These manifests are
   immutable — a new release gets a new file.

8. **Verify against the published asset**, not the local build:

   ```sh
   scripts/verify_release.sh manifests/<name>.yaml
   ```
