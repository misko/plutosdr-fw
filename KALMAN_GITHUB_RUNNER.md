# Kalman GitHub Actions firmware runner

Kalman builds the complete firmware package after a trusted merge to `main`.
Pull-request checks remain on GitHub-hosted runners. The repository is public,
so pull-request-controlled work must never target Kalman.

## Security boundary

- The runner is repository-scoped to `misko/plutosdr-fw`.
- Its service account is `github-fw`, without sudo or supplementary groups.
- The systemd service hides home directories and physical devices, including
  radios and USB devices.
- The runner has no QNAP credentials, SSH keys, or deployment secrets.
- The trusted workflow has read-only repository permissions.
- Self-hosted jobs require the triggering GitHub actor to be `misko`.
- The RC12 trusted workflow ends after the build job uploads the exact deployment
  bundle and its detached SHA-256 sidecar.
- GitHub provenance attestation is optional operator-owned supporting metadata;
  it is not a required workflow job and cannot authorize deployment.
- Successful CI means offline validated and deployment-ready; it does not mean
  hardware-tested, QSPI-approved, or production-promoted.

RC7 trusted run `32948720383` successfully built and fully routed the design,
passed the integrated report gate, and uploaded a bundle whose SHA-256 was
`7f13d6dd3f814af1a1e0d06d65535d2f60499b4bb3c0ab0e5cc4e7b8c8836f34`.
The candidate was nevertheless rejected before evidence indexing or hardware
use because bundle member/checksum order depended on locale and shell-array
order. There was no deployment. Its branch, source lock, run, and bytes remain
immutable reproduction history; RC8 fixes only that deterministic packaging
boundary.

RC8 trusted run `32952343526` then completed the exact deterministic build:
32,908 of 32,908 nets routed, 4,399 of 4,400 slices placed, 74 of 80 DSPs used,
WNS `+0.645 ns`, WHS `+0.022 ns`, and minimum bus skew `+8.606 ns`. Bundle
SHA-256 was
`d55b58e489a58c3c8868f4bfcec4a7901c229a25e801c172bf2dd1fa08965c77`,
DFU SHA-256 was
`2c74f06bff072d9c3250e5e028e18ddda4f700f5960cd07153432f1a081a8f49`,
and the verifier-accepted candidate-index SHA-256 was
`d94b9c37a8c6f1e5935df5ae4bdfd03be49b7aba40236a32386382a0f09004a8`.
No radio was opened or deployed: the RAM deployer still required a redundant
historical transition-proof input in addition to its live safeguards. RC8's
source lock, run, bundle, DFU, and index remain immutable reproduction history.

RC9 removed that redundant input and locked exact source commit
`9f47ef1746eaf356e53fe52cd9eb608ee8421c62`. Trusted run `32957388515`,
attempt 1, fully routed 32,908 of 32,908 nets at WNS `+0.645 ns`, WHS
`+0.022 ns`, and minimum bus skew `+8.606 ns`. Bundle SHA-256 was
`5f3eb4a772fb808f4598c4cc11d6a10936fecdaf045636d33ddfeaeaa9927dc7`,
DFU SHA-256 was
`407c560be90cfdbf459b92f1f76352f83f09cabf9c5f336375bd85868454975f`,
and the verified candidate-index SHA-256 was
`d2784863cfb74c34e98a2295a1b7532fc19f7f93ef90045b726055f1f99d3efd`.
Its first live execute stopped before reboot or DFU: duplicate connected `/24`
routes selected the wrong serial, then a temporary exact `/32` route exposed
the factory image's password-only SSH service. No radio changed state and no
receipt was produced. RC9's source lock, run, artifact, and index remain
immutable reproduction history.

RC10 then advanced only the guarded host route/authentication boundary and
receipt schema; firmware behavior remained unchanged. Exact source commit
`1b3ba3dbe942b9880f21ca99dda1de5227794c3d` and lock
`refs/tags/tandem-agc-v8-rc10-source/firmware-v1` passed Trusted run `32964460396`,
attempt 1. The run fully routed 32,908 of 32,908 nets, used 74
of 80 DSPs, and closed timing at WNS `+0.645 ns`, WHS `+0.022 ns`, and minimum
bus skew `+8.606 ns`. Artifact ID `9605679961` is named
`plutoplus-main-1b3ba3dbe942b9880f21ca99dda1de5227794c3d-32964460396-1`.
Its outer ZIP SHA-256 is
`273f4b02cf7438c1c5983ea3b87140000d947cc3dc30c7d0631847c5d934ba2c`,
bundle SHA-256 is
`144aaef4ebab18e7b859f0855421060bcaae8031db3acc1d3b195561f1a2047d`,
DFU SHA-256 is
`c0a086eb945d27f728a7fb2504de85ef648fc1dcc1d70a928f9d8c999e523913`,
FIT SHA-256 is
`7e725f5094f224126f98d923e2cb8668af69d2d79132a81f3ee5a74ff75d48cd`,
source-manifest SHA-256 is
`5c04a354075ef7ce98958b82ab8ef03277461f24621b88f4a4d2bda5b6d0931f`,
and verified candidate-index SHA-256 is
`827cc1e6d5d36a7a7f6b61b5238dae7df986d0708eef4c2f4a2e41f2f2461b58`.

On `winbond-db6968136727402c` at pre-attested topology `3-7`, route,
authentication, runtime, and QSPI baseline checks passed, and
`/usr/sbin/device_reboot ram` transitioned the device to exact `0456:b674`.
The b674 sysfs serial was absent, so the exact-serial resolver stopped before any `dfu-util -D`:
zero candidate bytes were downloaded. RC10 has zero candidate deployments,
no receipt was published, and no QSPI write occurred.
Exact-topology `dfu-util -e` recovered the persistent RC1 safe runtime. The
temporary `192.168.2.1/32` route is absent. RC10's source lock, trusted run,
artifact, candidate index, and zero-deployment history remain immutable. RC11
advanced only the serialless-b674 resolver boundary: only a unique exact
`0456:b674` on the pre-attested topology may omit its serial; all b673 paths
and returned-runtime checks remain exact-serial.

RC11 locked exact commit
`4c332666ff054e21e10c1a8137fd5f1cbc73b568` and source lock
`refs/tags/tandem-agc-v8-rc11-source/firmware-v1`. Trusted run `32970312166`,
attempt 1, fully routed the design and retained artifact ID `9607927415`. Its
outer ZIP SHA-256 is
`583c52462725c037ba73aca32d78472ea6784b43764e13ab92996b322ee5b3d3`,
bundle SHA-256 is
`91410b15e458eac1a2190dd0fa40ee540b6f7e6bde9e71c70125a9f86dc05c09`,
DFU SHA-256 is
`1dd94789dddefb7220caad75fb063ad0fdd2a8f3204f2f4fa48bd1cca2d31481`,
and verified candidate-index SHA-256 is
`ef8017c539f42d936bcde054e85864e331d4b383167201573c30419d98100831`.

The guarded execute reached unique exact serialless b674 on topology `3-7`,
then dfu-util rejected the single `0456:b674` selector against the trusted
b673 DFU suffix and exited 64 before transferring bytes. Exact-topology
paired-selector `-e` recovered persistent RC1 in a verified safe state; the
temporary route is absent. RC11 has zero candidate deployments, no receipt,
and no QSPI write. Its source lock, trusted run, artifact, index, and
zero-deployment history remain immutable. RC12 corrects only the paired
normal/DFU selector and lineage.

The forward-only RC12 route uses branch
`codex/firmware-tandem-agc-v8-rc12`, exact version
`v0.41-plutoplus-spf-tandem-agc-v8-rc12`, and source lock
`refs/tags/tandem-agc-v8-rc12-source/firmware-v1`; it does not move or reuse
RC11's branch, source lock, artifact, or evidence index.

## One-time administrator installation

1. In GitHub, open **Settings → Actions → Runners → New self-hosted runner**.
2. Select Linux and x64 and copy the one-hour registration token.
3. From this repository, run:

   ```bash
   sudo scripts/ci/install_kalman_runner.sh
   ```

4. Paste the token only when the script prompts for it.
5. Confirm that `kalman-firmware` appears online with these labels:

   ```text
   self-hosted, Linux, X64, kalman, vivado-2022.2, plutosdr-fw
   ```

The installer downloads GitHub Actions Runner 2.336.0, verifies its published
SHA-256, verifies Vivado 2022.2 as the isolated account, registers the runner,
and installs a hardened systemd service. The registration token is not stored
in the repository.

## CI behavior

`.github/workflows/firmware.yml` performs four checks on GitHub-hosted runners
for pull requests targeting `main`:

1. radio-hardware metadata, continuity, quality, campaign, and RTL oracles
   (offline only; this job never opens a radio);
2. the immutable source graph and legal-info network boundary;
3. USB and IP gadget unit tests; and
4. coherent RX counter CDC, FIFO-reset, TX-diagnostic, and discard simulations.

`.github/workflows/firmware-main.yml` runs only for pushes to `main` initiated
by `misko`, or a manual dispatch initiated by `misko` from an explicitly
allowed maintainer source-lock branch. It:

1. checks out the full pinned source graph;
2. cleans persistent generated files from all nested worktrees;
3. runs source, host, and HDL simulation gates;
4. rebuilds the FPGA using Vivado 2022.2;
5. builds the DFU and validates its FIT, XSA, rootfs, gadget binaries, timing,
   bus skew, CDC report, legal page, and checksums;
6. uploads the commit-addressed deployment bundle and its detached checksum for
   90 days.

The RC12 workflow has no separate attestation job. An operator may capture GitHub
provenance later as optional supporting metadata, but its presence or absence
does not change the trusted build result and cannot replace source-lock,
checksum, evidence-index, routed-design, or hardware checks.

The workflow never flashes a radio and never connects to the QNAP.

## Immutable source locks

`manifests/tandem-agc-v8-source.yaml` is the source graph selected for `main`.
It pins libiio, Buildroot, HDL, timestamp HDL, Linux, U-Boot, and both gadget
implementations by exact 40-character commit and protected source-lock tag.
The final v8 graph advances libiio to the protected RC3 bounded-batch transport,
Buildroot to its matching RC3 recipe lock, and Linux to the tandem-v2
`linux-v11` cleanup lock. It deliberately reuses every unchanged gadget, HDL,
timestamp HDL, and U-Boot lock from the tandem-v2, gain-series, and
libiio-metadata families instead of minting aliases at the same commits. Active
GitHub rulesets prevent every referenced lock from being updated or deleted in
its owning repository.

The source check requires exact tag-to-commit equality and requires each packed
`/opt/VERSIONS` identity to equal its declared source-lock tag. The trusted
runner then synchronizes only those declared tags and checks the live
`git describe --tags` result before building. Moving development branches and
ambient persistent-runner tags are not build inputs.

For a later candidate, advance an existing protected, versioned component
lineage or create and protect a new source-lock namespace, then update the new
manifest in the same reviewed change. Never reuse or repoint an existing
source-lock tag. The firmware release tag remains separate and is created only
after the hardware promotion gate.

## Main-branch policy

Before merging the runner workflow:

- make `main` the default branch;
- require pull requests and all four GitHub-hosted checks:
  `radio hardware offline oracles`, `source graph`, `USB and IP gadget unit tests`, and
  `coherent RX counter CDC simulation`;
- require conversation resolution;
- require code-owner review when another eligible maintainer is available;
- prohibit force pushes and branch deletion;
- preserve the immutable RC tag's exact commit ancestry with a merge commit;
- protect `v*` tags from rewriting.

The post-merge Kalman build is deliberately not a pre-merge required check.
It is the authoritative build of the exact merged commit. A failed build blocks
deployment and must be fixed by a new reviewed commit; it does not authorize
rewriting an existing artifact or tag.

## Deployment handoff

Download the Actions artifact named
`plutoplus-main-<full-commit>-<run>-<attempt>`. Require exactly one deployment
bundle and its adjacent detached checksum, verify that sidecar, extract the
bundle, and verify its complete inner `SHA256SUMS` inventory before using the
DFU:

```bash
set -euo pipefail
shopt -s nullglob
artifact_dir=/absolute/path/to/downloaded-artifact
bundles=("$artifact_dir"/*.tar.gz)
sidecars=("$artifact_dir"/*.tar.gz.sha256)
test "${#bundles[@]}" -eq 1
test "${#sidecars[@]}" -eq 1
bundle=${bundles[0]}
sidecar=${sidecars[0]}
test "$sidecar" = "$bundle.sha256"
(
  cd "$artifact_dir"
  sha256sum -c "$(basename "$sidecar")"
)
extracted=$(mktemp -d)
tar -xzf "$bundle" -C "$extracted"
(
  cd "$extracted"
  sha256sum -c SHA256SUMS
)
```

GitHub attestation is not required for this handoff. The v1 evidence archive
still retains a supporting-attestation role: the normal single-owner route uses
the exact `plutosdr-fw.github-attestation-not-performed.v1` record documented in
the tandem release plan, while an operator may instead retain an optional
captured GitHub-provenance record. Neither form replaces the checks above or
grants hardware authority by itself.

The hardware agent must RAM-boot and complete the promotion campaign before
any QSPI or rover-production change.
