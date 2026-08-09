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

`.github/workflows/firmware.yml` performs source-graph, USB/IP gadget, and HDL
simulation checks on GitHub-hosted runners for pull requests targeting `main`.

`.github/workflows/firmware-main.yml` runs only for `main` pushes or a manual
dispatch whose selected ref is exactly `main`. It:

1. checks out the full pinned source graph;
2. cleans persistent generated files from all nested worktrees;
3. runs source, host, and HDL simulation gates;
4. rebuilds the FPGA using Vivado 2022.2;
5. builds the DFU and validates its FIT, XSA, rootfs, gadget binaries, timing,
   bus skew, CDC report, legal page, and checksums;
6. uploads a commit-addressed deployment bundle for 90 days; and
7. downloads, verifies, and attests that bundle on a GitHub-hosted runner.

The workflow never flashes a radio and never connects to the QNAP.

## Main-branch policy

Before merging the runner workflow:

- make `main` the default branch;
- require pull requests and the three GitHub-hosted checks;
- require conversation resolution;
- require code-owner review when another eligible maintainer is available;
- prohibit force pushes and branch deletion; and
- protect `v*` tags from rewriting.

The post-merge Kalman build is deliberately not a pre-merge required check.
It is the authoritative build of the exact merged commit. A failed build blocks
deployment and must be fixed by a new reviewed commit; it does not authorize
rewriting an existing artifact or tag.

## Deployment handoff

Download the Actions artifact named
`plutoplus-main-<commit>-<run>-<attempt>`, verify the adjacent `.sha256` file,
extract the bundle, and run `sha256sum -c SHA256SUMS` inside it. Then verify the
GitHub attestation before using the DFU:

```bash
gh attestation verify plutoplus-spf-main-<commit>.tar.gz \
  --repo misko/plutosdr-fw
```

The hardware agent must RAM-boot and complete the promotion campaign before
any QSPI or rover-production change.
