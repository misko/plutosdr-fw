# Building this firmware

Everything here was verified on 2026-08-07/08 by rebuilding from a clean clone
and by extracting the deployed release binary and reading its contents. Where a
statement is surprising, the evidence is given.

## Three ways to build, in increasing order of isolation

```bash
# 1. Source graph only -- seconds, no toolchain, run this first and in CI
scripts/check_source_graph.sh manifests/fingerprint-v3.yaml

# 2. Container: clone from scratch and compile (the reference method)
docker build -t plutosdr-fw-builder docker/
docker run --rm -e DRY_RUN=1 plutosdr-fw-builder          # pull + gates only
docker run --rm -v "$PWD/out:/out" -v "$PWD/cache:/cache" plutosdr-fw-builder

# 3. Local tree
make XSA_FILE=/path/to/system_top.xsa build/pluto.dfu
```

Then prove what you built:

```bash
scripts/verify_release.sh manifests/fingerprint-v3.yaml --image <dfu> --identity-only
```

## Things that will waste your time if you do not know them

### You do not need Vivado or Vitis

`build/pluto.dfu` is the firmware partition (mtd3) image and that is the entire
deployed artifact. Its dependency chain is:

```
pluto.dfu <- pluto.itb <- { zImage, rootfs.cpio.gz, 3x dtb, system_top.bit }
system_top.bit <- unzip system_top.xsa        # when HAVE_VIVADO=0
```

`fsbl.elf`, `boot.bin` and `bootgen` are only reachable at `HAVE_VIVADO=1`, and
QSPI promotion writes mtd3 only. Extracting the bitstream from the pinned XSA is
plain `unzip`.

### Do not run `make all`, and never pass `SKIP_LEGAL=1`

Build `build/pluto.dfu` directly. `make all` drags in `zip-all` and `legal-info`
packaging that is not part of the artifact.

`SKIP_LEGAL=1` looks like a free speedup. It is not. The Makefile guards both
`make -C buildroot legal-info` *and* the copy of the generated `LICENSE.html`
into `board/pluto/msd/` behind that flag, and the mass-storage image lists
`LICENSE.html` as a required file. The build then fails in `target-finalize`,
**after** the kernel and every package have compiled:

```
ERROR: file(LICENSE.html): stat(.../board/pluto/msd/LICENSE.html) failed
ERROR: vfat(boot.vfat): could not setup LICENSE.html
```

`docker/build_firmware.sh` refuses `SKIP_LEGAL=1` outright.

### Submodule depth is part of the recipe, not an optimisation

`Makefile:113-114` writes `/opt/VERSIONS` from `git describe --abbrev=4 --dirty
--always --tags` per component, so clone depth changes the recorded string. The
deployed image was built with:

| submodule | depth | recorded in /opt/VERSIONS |
|---|---|---|
| `linux` | 1 | `d798b` (bare short SHA) |
| `u-boot-xlnx` | 1 | `1ff04` |
| `hdl-quantulum` | 1 | *(not recorded)* |
| `buildroot` | shallow | `f37f` |
| `hdl` | **full + tags** | `dev_prj_2018_r1-1859-gbe89` |

Only `hdl` has a reachable tag, so only `hdl` needs full history. A blanket
`git submodule update --init --recursive` pulls ~2.8 GB of kernel history that
is never used and will drive a small builder into swap.

The **superproject** must always have full history and tags, or `device-fw`
degrades to a bare SHA and stops matching the manifest.

### Do not add `shallow = true` to .gitmodules

It is the obvious way to avoid the kernel clone and it silently builds the wrong
firmware. `git submodule update` shallow-clones a submodule's **default** branch
and then checks out the recorded gitlink SHA. Our pins live on
`v0.38_plutoplus` (and `codex/buildroot-gadget-supervisor-v3`), not on `master`,
so a depth-1 clone of the default branch cannot contain them.

Measured: with `shallow = true` on `linux` and `u-boot-xlnx`, a fresh
`git submodule update --init --recursive` left them at `16b5c2ea` and `f06dec3`
— the misko `master` tips — instead of `d798b0d8` and `1ff0468e`. It reports
success.

Only `hdl-quantulum` carries `shallow = true`, because its pin genuinely is its
default-branch tip. The real fix would be repointing each mirror's default
branch at the pin's branch.

### Do not re-home hdl into misko/plutosdr-fw

The hdl pin is archived at `misko/plutosdr-fw`
`refs/heads/hdl-v0.38-plutoplus-timestamp` so the objects survive independently
of pgreenland. **That archive must not become the submodule source.**

`/opt/VERSIONS` records `git describe --abbrev=4`, and `--abbrev=4` is a
*minimum* — git lengthens the hash until it is unique **within that repository**.
`plutosdr-fw` also carries the firmware, buildroot and gadget histories, so the
identical commit describes there as `dev_prj_2018_r1-1859-gbe89a7` (6 hex)
instead of `dev_prj_2018_r1-1859-gbe89` (5 hex). Re-homing hdl would silently
change the recorded firmware identity while every commit stayed the same.

The correct fix is a dedicated `misko/plutosdr-hdl` mirror, which needs repo
creation rights the build token does not have.

Consequently a plain `git submodule update --init --recursive` does full clones
and needs ~3 GB. On a memory-constrained builder use `docker/build_firmware.sh`,
which clones each submodule explicitly at the right depth and asserts every
resulting SHA against the manifest.

### The toolchain depends on your host architecture

`configs/zynq_pluto_defconfig` selects `BR2_TOOLCHAIN_EXTERNAL_LINARO_ARM`
(gcc 7.3.1, `arm-linux-gnueabihf`). On **aarch64** that option is unselectable,
so kconfig silently falls back to `BR2_TOOLCHAIN_EXTERNAL_ARM_ARM` (ARM GNU
10.3-2021.07, `arm-none-linux-gnueabihf`) — which is what actually built the
deployed release. On **x86_64** the Linaro option *is* selectable and wins, so
the same source builds with a different compiler.

**aarch64 is therefore canonical.** `docker/build_firmware.sh` resolves the
config early and refuses to continue on a mismatch rather than shipping a
differently-compiled image. Pinning `BR2_TOOLCHAIN_EXTERNAL_ARM_ARM` in the
defconfig would fix this properly, but it changes the buildroot commit and
therefore the pin, so it belongs on the next release line, not on v3.

### A local.mk override produces a binary that lies

Buildroot's `<PKG>_OVERRIDE_SRCDIR` replaces the source but the pinned `.mk`
still passes `-DGIT_VERSION_OVERRIDE=<pinned sha>`. An overridden build yields a
gadget that **reports the pinned SHA while containing different code**, which
defeats `pluto_gadget_build_id`. `check_source_graph.sh` and the container build
both refuse to proceed if one exists.

Check only `local.mk`, `buildroot/local.mk` and `buildroot/output/local.mk` —
upstream bison and autoconf ship dozens of unrelated `local.mk` files as
ordinary automake includes.

## Verification vs rebuilding

These are different operations and must not be conflated.

| | question | hash |
|---|---|---|
| `verify_release.sh` | is this the deployed release binary? | must match |
| `verify_release.sh --identity-only` | did we correctly recreate that build? | must **not** match |

The deployed v3 was built with `BR2_REPRODUCIBLE` off and no kernel timestamp
pinning, so a rebuild can never reproduce `image_sha256`. What a rebuild must
reproduce is every embedded identity: `device-fw`, the four `/opt/VERSIONS`
strings, the FPGA bitstream md5, and the gadget build ID read out of the shipped
binary. Bit-reproducibility is a property to build into the next release, and it
necessarily changes the output.

`REPRODUCIBLE=1` pins `SOURCE_DATE_EPOCH` and `KBUILD_BUILD_TIMESTAMP/_USER/_HOST`
only. It deliberately does **not** claim to set `BR2_REPRODUCIBLE`, because it
cannot: the Makefile's rootfs target re-runs `zynq_pluto_defconfig` immediately
before `make -C buildroot all`, overwriting any `.config` edit. Enabling it for
real means committing `BR2_REPRODUCIBLE=y` to `configs/zynq_pluto_defconfig`,
which changes the buildroot commit, the pin, and therefore `device-fw` — a next
release-line change, not a v3 one. Buildroot additionally documents
`BR2_REPRODUCIBLE` as restricted to builds using the same output directory,
which is why the container fixes the build path at `/build`.

## Known provenance defect in the v3 tag

The release tag `v0.38-plutoplus-spf-gain-rssi-fingerprint-v3` points at
`dac99758`, but the shipped binary was built from `f53dd006` — three commits
earlier. `git checkout <release tag>` gives you source that did not build that
release. The manifest records the true build commit, and
`check_source_graph.sh` warns about the mismatch.

This is also why the image reports `device-fw ...-v2-8-gf53d`: `git describe`
ran before the v3 tag existed, so it found the nearest earlier tag. **Tag the
build commit before building** and this cannot recur.
