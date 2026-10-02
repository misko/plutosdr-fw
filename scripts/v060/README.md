# v0.60 integrated release

This release combines issues #119 and #120 on the exact v0.59 firmware base.
`scripts/v060/package.py` packages the qualified issue-119 kernel and integrated
iiOD into the v0.59 DFU. It checks the parent and kernel hashes and the iiOD
source commit, preserves rootfs metadata and all other payloads, and produces
FIT, DFU, FRM and an artifact binding. The original v0.59 libiio shared library
remains in the image: the combined source changes affect iiOD and its tests.

The published binary uses this component-replacement route. The main workflow
also selects `manifests/adaptive-native-fastlock-v060-source.yaml` for future
full builds; those builds require their own artifact qualification.

Reproduce packaging with the release source checkout and the ARM iiOD build
at `LIBIIO_SOURCE/build-arm/iiod/iiod`:

```sh
python3 scripts/v060/package.py --parent /absolute/v059.dfu \
  --libiio /absolute/LIBIIO_SOURCE --kernel /absolute/issue119-zImage \
  --output /absolute/new-output-directory
```

The exact immutable sources are in the manifest and artifact binding. Build
Linux using its v0.59 kernel configuration and the issue-119 procedure in
`scripts/issue119/README.md`. Build iiOD with the v0.59 ARM sysroot, the pinned
metadata provider, and the integrated libiio source using `scripts/v060/build_iiod.sh`
(the same five arguments as the issue-119 builder). Preserve the unstripped
iiOD used by the artifact binding.

`deploy.py` is a deliberately restricted PPU LAN procedure for radio `.15`.
It requires the exact previously installed image and component qualification
reports before flash. It verifies the updater, physical flash limits, protected
regions, written FIT and returned identity. It is not a general updater.
`qualify.py` records bounded RX-only visits, exact IQ geometry, gain mode,
restoration, ordinary capture and cancellation/DMA failure behavior under one
30-minute cumulative reservation ledger. It requires the matching PPU runtime
and the private pinned SSH known-hosts file. Run a new qualification for a new
binary; do not reuse this image's receipts to approve other builds.
