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

## Current tandem v8 gate

RC2 exposed two release blockers: a closed tandem session could report IDLE
while leaving event records inaccessible in the FPGA FIFO, and the synchronous
host metadata request/response cadence could lose a full 65,536-sample frame
without a device-overflow indication. RC3 advanced the Linux RELEASE cleanup,
the bounded libiio batch transport, and the matching Buildroot recipe pin, but
hardware qualification found a top-level RTL request/pulse handoff bug at zero
cooldown. RC4 retained RC3's external component pins and corrected that tracked
top-level RTL.

RC4 is no longer promotable as the final v8 source. After its protected
firmware source lock at `557a08749d9c0c34fe8096099b5be9d2b2a1b24f`, the
release branch added stale-small-ADC-latch recovery. RC5 locked that recovery
at `af2e1821436996188fd32cc1cf8a0f8a41f31fc1`, but its trusted integrated
build failed placement by 17 slices before producing an artifact. The RC5
branch and `refs/tags/tandem-agc-v8-rc5-source/firmware-v1` are immutable failed
history and must never move.

RC6 locked that fit refactor at
`fb1cb04085fda4854f964481d5d5427b6934d58b`. Trusted run `32944830787`
placed 4,399 of 4,400 slices, used 74 of 80 DSPs, routed all 32,908 nets, and
closed timing at WNS `+0.645 ns`, WHS `+0.022 ns`, and minimum bus skew
`+8.606 ns`. The post-route validator then rejected stale report-state, DSP,
and CDC policy assumptions. Only failure diagnostics were uploaded: there was
no deployment bundle, candidate index, or DFU. The RC6 branch and
`refs/tags/tandem-agc-v8-rc6-source/firmware-v1` are therefore immutable failed
history and must never move.

The active candidate is RC7. It retains RC6's placed, fully routed,
timing-clean RTL and corrects the report validator rather than changing the
firmware behavior. Its exact candidate source lock is
`refs/tags/tandem-agc-v8-rc7-source/firmware-v1`. The later final build uses the
different exact lock `refs/tags/tandem-agc-v8-source/firmware-v1`; candidate and
final evidence must reject a cross-stage substitution of those refs.

The remaining gates, in order, are:

1. Commit the complete source and run the routed block-level OOC gate from a
   clean tree. Its PASS is useful fit/timing/CDC evidence but explicitly records
   `firmware_release_eligible=false`.
2. Create the exact RC7 firmware source lock and explicit trusted build route.
   Keep RC4/RC5/RC6's external component pins only if source-graph checks prove
   they remain exact.
3. Build and route the complete Pluto FPGA design from that exact candidate;
   retain integrated timing, CDC, DRC, methodology, utilization, and build
   provenance. Block-level OOC evidence cannot replace this step.
4. Build the candidate firmware with its exact `device-fw` string, verify the
   indexed bundle, checksums, and packed component identities, and RAM-boot
   those exact bytes on all four release-gate radios.
5. Run the full external release campaign, including muted metadata lifecycle,
   transient transport, signal quality, teardown, and cleanup. The internal
   stale-small-ADC clear/re-arm property is qualified by deterministic RTL at
   both supported clock ratios. Its release-image observer is optional,
   deliberately emits only `BLOCKED`, and cannot authorize promotion.
6. Only after the candidate passes, merge the exact qualified source to `main`,
   create `refs/tags/tandem-agc-v8-source/firmware-v1`, build the final v8
   identity, repeat the full four-radio campaign, then tag, publish, and write
   the immutable release manifest.

Protected dependency source locks must exist before the build so CI can resolve
and pack them. They are not release tags. Do not create the annotated
candidate release tag until the exact indexed bundle completes the full
four-radio RAM qualification. Never move or reuse a failed source lock, an
existing candidate lock, or a release tag.

## Procedure

1. **Decide the name.** Drop the candidate's `-rcNN`, keep the intended
   upstream-version prefix, and verify that neither the tag nor release already
   exists. For the current tandem promotion the exact name is
   `v0.41-plutoplus-spf-tandem-agc-v8`.

2. **Protect the final source and dispatch the build.** Create and push the
   lightweight source lock `refs/tags/tandem-agc-v8-source/firmware-v1` at the
   exact `main` commit, then dispatch `main` with `release_version` set to the
   exact name. This source lock is not the annotated release tag. Do not create
   the release tag first—if the build or testing fails, advance the source
   commit rather than moving any existing ref.

3. **Download and verify the Actions artifact.** No GitHub release exists yet;
   qualification must use the artifact from the exact workflow run in step 2,
   never `gh release download`. Record the intended 40-character `main` commit,
   the run ID, and the run attempt. Confirm that the run's `headSha` is that
   commit, then verify the bundle sidecar, internal checksums, and packed
   `/opt/VERSIONS`:

   ```bash
   set -euo pipefail
   shopt -s nullglob
   release_run_id='<run-id>'
   release_commit='<40-character-main-commit>'
   release_attempt='<attempt>'
   release_artifact="plutoplus-main-${release_commit}-${release_run_id}-${release_attempt}"
   release_work=$(mktemp -d)

   test "$(gh run view "$release_run_id" --repo misko/plutosdr-fw \
     --json headSha --jq .headSha)" = "$release_commit"
   gh run download "$release_run_id" --repo misko/plutosdr-fw \
     --name "$release_artifact" --dir "$release_work"
   release_bundles=("$release_work"/*.tar.gz)
   test "${#release_bundles[@]}" -eq 1
   release_bundle=${release_bundles[0]}
   release_bundle_sha=$(sha256sum "$release_bundle" | awk '{print $1}')
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
   jq -n --arg repository misko/plutosdr-fw \
     --arg head_sha "$release_commit" \
     --argjson run_id "$release_run_id" \
     --argjson run_attempt "$release_attempt" \
     --arg bundle "$(basename "$release_bundle")" \
     --arg bundle_sha "$release_bundle_sha" \
     '{schema:"plutosdr-fw.github-attestation-not-performed.v1",
       repository:$repository,head_sha:$head_sha,run_id:$run_id,
       run_attempt:$run_attempt,bundle_sha256:$bundle_sha,
       subject:{name:$bundle,sha256:$bundle_sha},
       verification_performed:false,
       reason:"single-owner-operator-trust-model"}' \
     > "$release_work/attestation-verification.json"
   ```

   The printed `device-fw` must equal the requested release name. The four
   packed component identities must equal the `versions_*` values in the source
   manifest. The exact not-performed record preserves the v1 evidence role
   without making a cryptographic claim. An operator may capture GitHub
   provenance as optional supporting metadata, but it cannot gate the build or
   replace any source-lock, checksum, routed, or hardware check.

4. **Hardware-qualify these exact bytes with the full campaign.** A rebuild for
   the final name is byte-different from the qualified RC, so the RC campaign
   does not transfer literally. The repository has no guarded reduced-
   confirmation runner or durable reduced verdict. Tandem v8 therefore repeats
   the complete four-radio RAM deployment, full/soak/lifecycle matrix, cleanup,
   and evidence-index assembly on the final bytes. A future release may use a
   reduced confirmation only after implementing and testing that executable
   gate.

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
