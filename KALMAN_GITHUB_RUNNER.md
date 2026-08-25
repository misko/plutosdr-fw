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
- Artifact attestation occurs in a separate GitHub-hosted job.
- Successful CI means offline validated and deployment-ready; it does not mean
  hardware-tested, QSPI-approved, or production-promoted.

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
6. uploads a commit-addressed deployment bundle for 90 days; and
7. downloads, verifies, and attests that bundle on a GitHub-hosted runner.

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
`plutoplus-main-<full-commit>-<run>-<attempt>`, verify the adjacent `.sha256`
file, extract the bundle, and run `sha256sum -c SHA256SUMS` inside it. Then
verify the GitHub attestation against the extracted `*.tar.gz` before using the
DFU:

```bash
gh attestation verify plutoplus-spf-*-<short-commit>.tar.gz \
  --repo misko/plutosdr-fw
```

The hardware agent must RAM-boot and complete the promotion campaign before
any QSPI or rover-production change.
