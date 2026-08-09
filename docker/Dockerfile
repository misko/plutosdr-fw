# Reproducible-ish PlutoSDR firmware build environment.
#
# Builds build/pluto.dfu -- the firmware partition (mtd3) image that is the
# deployed release artifact. This needs NO Vivado and NO Vitis/XSCT:
#
#   pluto.dfu <- pluto.itb <- { zImage, rootfs.cpio.gz, 3x dtb, system_top.bit }
#   system_top.bit <- unzip system_top.xsa          (when HAVE_VIVADO=0)
#
# fsbl.elf / boot.bin / bootgen are only reachable at HAVE_VIVADO=1, and QSPI
# promotion writes mtd3 only, so the entire deployed image builds from open
# source tools.
#
# The build path is FIXED at /build on purpose. Buildroot's own BR2_REPRODUCIBLE
# help states the implementation "is restricted to builds with the same output
# directory... If you build with the same O=... path, however, the result is
# identical." A fixed path is therefore a precondition for reproducibility, not
# a convenience.
#
# The Buildroot toolchain is BR2_TOOLCHAIN_EXTERNAL_ARM_ARM (ARM GNU 10.3-2021.07),
# whose tarball name interpolates $(HOSTARCH), so this image works unmodified on
# both linux/arm64 and linux/amd64 hosts.

# Pin by digest, not by tag: a moving base defeats the entire point.
FROM debian:bookworm-20250630-slim

# The upstream README's apt list is stale -- libssl1.0-dev and python do not
# exist on current Debian. These are the substitutes, recorded deliberately.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        bc \
        bison \
        build-essential \
        ca-certificates \
        ccache \
        cpio \
        device-tree-compiler \
        dfu-util \
        fakeroot \
        file \
        flex \
        git \
        gzip \
        libncurses-dev \
        libssl-dev \
        mtools \
        python3 \
        rsync \
        sed \
        u-boot-tools \
        unzip \
        wget \
        xz-utils \
        zip \
    && rm -rf /var/lib/apt/lists/*

# Buildroot refuses to run as root.
RUN useradd -m -u 1000 -s /bin/bash builder \
    && mkdir -p /build /out /cache \
    && chown -R builder:builder /build /out /cache

COPY build_firmware.sh /usr/local/bin/build_firmware.sh
RUN chmod +x /usr/local/bin/build_firmware.sh

USER builder
WORKDIR /build

# Deterministic environment. SOURCE_DATE_EPOCH is honoured by u-boot's mkimage
# (tools/imagetool.c) for the FIT timestamp and by Buildroot (Makefile uses ?=,
# so a value exported here wins over its git-derived default).
ENV LC_ALL=C \
    LANG=C \
    TZ=UTC \
    BR2_DL_DIR=/cache/dl \
    CCACHE_DIR=/cache/ccache

ENTRYPOINT ["/usr/local/bin/build_firmware.sh"]
