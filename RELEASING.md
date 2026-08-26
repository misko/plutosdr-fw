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

RC7 then corrected that validator without changing firmware behavior. Trusted
run `32948720383` completed the build and integrated route and uploaded a
bundle with SHA-256
`7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34`.
The bundle was rejected before evidence assembly because its member/checksum
ordering depended on locale and shell-array order. There was no deployment and
no hardware use. The RC7 branch and
`refs/tags/tandem-agc-v8-rc7-source/firmware-v1` are immutable rejected history
and must never move.

RC8 then made package ordering deterministic and locked exact commit
`cc62b65ea8082aad0625a891f0b79b81c78e78c7`. Trusted run `32952343526`
completed successfully: 32,908 of 32,908 nets routed, 4,399 of 4,400 slices
placed, 74 of 80 DSPs used, WNS `+0.645 ns`, WHS `+0.022 ns`, and minimum bus
skew `+8.606 ns`. Its candidate index verifies at SHA-256
`d94b9c37a8c6f1e5935df5ae4bdfd03be49b7aba40236a32386382a0f09004a8`.
The indexed bundle SHA-256 is
`d55b58e489a58c3c8868f4bfcec4a7901c229a25e801c172bf2dd1fa08965c77`;
the DFU SHA-256 is
`2c74f06bff072d9c3250e5e028e18ddda4f700f5960cd07153432f1a081a8f49`,
and the FIT SHA-256 is
`30f7816ea2f1b66aff928613b95748f952cafbb35bc7320a05bfdd5e3075b9d8`.
No radio was deployed because the deployer still required a redundant
historical transition-proof input in addition to its live safeguards, so RC8
performed zero hardware deployment. RC8's branch and
`refs/tags/tandem-agc-v8-rc8-source/firmware-v1` remain immutable successful
build history and must never move.

RC9 then removed the redundant transition-proof input and locked exact commit
`9f47ef1746eaf356e53fe52cd9eb608ee8421c62`. Trusted run `32957388515`,
attempt 1, completed the full integrated build; its verified candidate index is
SHA-256
`d2784863cfb74c34e98a2295a1b7532fc19f7f93ef90045b726055f1f99d3efd`
and its DFU is SHA-256
`407c560be90cfdbf459b92f1f76352f83f09cabf9c5f336375bd85868454975f`.
The first execute attempt stopped at the initial SSH read, before reboot, DFU,
or receipt: competing `192.168.2.0/24` routes selected another serial and the
factory password-only service rejected key-only authentication. The temporary
diagnostic `/32` route was removed and RC9 performed zero deployments. Its
branch, lock `refs/tags/tandem-agc-v8-rc9-source/firmware-v1`, run, artifact,
and candidate index remain immutable successful reproduction history.

RC10 then retained RC9's firmware behavior and deterministic package while
adding the exact per-interface `/32` route, private password-file SSH, verified
route cleanup, and measured receipt v3. Exact commit
`1b3ba3dbe942b9880f21ca99dda1de5227794c3d` and lock
`refs/tags/tandem-agc-v8-rc10-source/firmware-v1` passed trusted run
`32964460396`, attempt 1. The verified candidate index is SHA-256
`827cc1e6d5d36a7a7f6b61b5238dae7df986d0708eef4c2f4a2e41f2f2461b58`;
the bundle is SHA-256
`144aaef4ebab18e7b859f0855421060bcaae8031db3acc1d3b195561f1a2047d`;
the DFU is SHA-256
`c0a086eb945d27f728a7fb2504de85ef648fc1dcc1d70a928f9d8c999e523913`;
and the FIT is SHA-256
`7e725f5094f224126f98d923e2cb8668af69d2d79132a81f3ee5a74ff75d48cd`.

The first execute pre-attested `winbond-db6968136727402c` on topology `3-7`,
passed the route/auth/runtime/QSPI baseline, and sent
`/usr/sbin/device_reboot ram`. The device transitioned to exact `0456:b674`
but published no DFU sysfs serial, so RC10 stopped before any `dfu-util -D`.
Zero candidate bytes were downloaded, RC10 has zero candidate deployments, no
receipt was produced, and no QSPI write occurred. Exact-topology `dfu-util -e`
recovered the persistent RC1 safe runtime, and the temporary
`192.168.2.1/32` route is absent. RC10's branch, lock, run, artifact, candidate
index, and zero-deployment history are immutable.

RC11 then retained RC10's firmware behavior and corrected only serialless-b674
topology resolution. Exact commit
`4c332666ff054e21e10c1a8137fd5f1cbc73b568` and source lock
`refs/tags/tandem-agc-v8-rc11-source/firmware-v1` passed trusted run
`32970312166`, attempt 1. Its DFU SHA-256 is
`1dd94789dddefb7220caad75fb063ad0fdd2a8f3204f2f4fa48bd1cca2d31481`
and its verified candidate-index SHA-256 is
`ef8017c539f42d936bcde054e85864e331d4b383167201573c30419d98100831`.
The first guarded download reached unique exact serialless `0456:b674`, but
both the command planner and receipt validator selected only b674 while the
trusted DFU suffix identifies b673. dfu-util exited 64 before transferring any
candidate bytes. Paired-selector exact-topology `-e` recovered persistent RC1
in a verified safe state with the temporary route absent. RC11 has zero
candidate deployments, no receipt, and no QSPI write; its branch, lock, run,
artifact, index, and zero-deployment history are immutable.

RC12 then aligned both download and detach with the paired selector and locked
exact commit `12261ed055d4488d64aa7ff5353b680a37c3f93d` at source lock
`refs/tags/tandem-agc-v8-rc12-source/firmware-v1`. Owner-dispatched trusted run
`32978460325`, attempt 1, completed successfully and retained artifact ID
`9611124509`. Its verified candidate-index SHA-256 is
`a339c99eb7d16980b33249d5a8a5e8c0693a4d22cbf6333c5ce0b3aa2b0151cd`;
bundle SHA-256 is
`789aa4d9e8fc672a2040abeee89a34de5f62dafd9e933628ac09d0aac21444c2`;
DFU SHA-256 is
`6ffe6ddf898986b1fd6629db796b6b10422a4e5a00da268e0f63d1d258db52a0`;
and FIT SHA-256 is
`5db1c49f954e630e4d2a41860bc6bf3f1a6e58749c5c382398caa30887781957`.

On `winbond-db6968136727402c` at exact topology `3-7`, the first RC12 execute
stopped at initial SSH with exit 255 on the stale retained key, before reboot
or DFU. After isolated exact-current key enrollment, the second execute
requested RAM boot, completed paired-selector `-D` and `-e`, and returned the
exact b673 runtime running RC12 safely. Postboot and cleanup SSH both exited
255 because the RAM rootfs starts Dropbear with `-R` and has no persistent host
key. The route was removed, no deployment receipt/log/stderr was published,
and no QSPI write or persistent-target command was issued. No preboot QSPI
digest was retained, so postboot QSPI equality is not claimed. RC12 has one observed successful RC12 RAM deployment.
It has zero valid receipt-authorized deployments and is not hardware-qualified.
The exact RC12 source, successful build, artifact, evidence index, and observed
incident remain immutable.

RC13 locked exact commit `3361acb3446b517854ca1cfc144d28c4dd853743`
at `refs/tags/tandem-agc-v8-rc13-source/firmware-v1`. Owner dispatch
`32985347441`, attempt 1, remained queued without an allocated job and was
superseded before an artifact, candidate index, receipt, or hardware use. Its
host-key correction remains immutable but its in-repository device operator is
not the RC16 hardware-authorizing harness.

RC14 locked exact commit `2fb96f7a207848e6579293addbaa27fc0a59f5a9`
and passed trusted run `32993231088`, artifact `9616104711`, and candidate index
SHA-256 `7fb1616eee706350b124a84a053ea2340d25de9fa4a2366c421fc06fc78f306d`.
Its live preflight exposed utility-only global-discovery and capability-name
defects before reboot or DFU. It published no receipt and has zero RAM
transitions; its exact source, artifact, and index remain immutable.

RC15 locked exact commit `5e84a0cdd19f7635e688821d926ee7eca39c7eab`
and passed trusted run `32998047232` plus candidate index
`82838fe2e8d980c6097c80634c890eae30aac678f52708aafe07c112ad9e5dd9`.
Its first db696 transaction reached exact b674 but failed closed on the kernel
sysfs symlink before candidate bytes were downloaded. Guarded recovery returned
the board to persistent RC1, proved QSPI unchanged and the safe state, and
released the route. RC15 has no valid deployment receipt and is immutable.

The active candidate is RC16. It retains RC15's firmware implementation,
external source graph, deterministic package, topology-bound serialless-b674
resolver, paired `0456:b673,0456:b674` download/detach commands, exact `/32`
route, IIO/model/runtime checks, QSPI equality requirement, and safe-state
boundary. Exact pushed `pluto-plus-utils` commit
`2654f34eb909904ec65bc0526e0f8977cb30e2ed` is now the sole live device
operator. `plutosdr-fw` emits the private release-candidate plan and validates
the original utility plan, USB inventory, per-radio operation plan, and
measured receipt without translating them. Ephemeral RAM host keys are accepted
with password-only SSH and host-key files disabled. Exact topology remains
mandatory; nonempty serial mismatch, ambiguity, wrong VID/PID, serialless b673,
`-S`, `-R`, persistent targets, and returned-runtime mismatch remain forbidden
or fail closed. Its exact candidate source lock is
`refs/tags/tandem-agc-v8-rc16-source/firmware-v1`. The later
final build uses the different exact lock
`refs/tags/tandem-agc-v8-source/firmware-v1`; candidate and final evidence must
reject a cross-stage substitution of those refs.

The remaining gates, in order, are:

1. Commit the complete source and run the routed block-level OOC gate from a
   clean tree. Its PASS is useful fit/timing/CDC evidence but explicitly records
   `firmware_release_eligible=false`.
2. Create the exact RC16 firmware source lock and explicit trusted build route.
   Keep RC4 through RC12's external component pins only if source-graph checks
   prove they remain exact.
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
