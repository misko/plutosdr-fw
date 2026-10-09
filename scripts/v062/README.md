# Continuous fast scan firmware v0.62

## Motivation

Deliver the ordered eight-target IQ scanner independently of FPGA power
acceleration. The existing FPGA image remains byte-identical to v0.61.

## Problem

Repeated finite scan campaigns add setup gaps. The new negotiated v5 operation
owns the ordered loop on the device until STOP, retaining every IQ window for
software power measurement and offline GLRT. A total transition allowance does
not guarantee a minimum guard after a late tuning recall.

## Solution

The daemon schedules eight prepared IF targets repeatedly at 2.5 MS/s. Each
visit returns 50,000 complex CI16 samples per enabled receiver; dual receivers
capture simultaneously. It starts the valid window at least the configured
guard after the recall-completion counter (20 ms in qualification). Capture
duration remains 20 ms. STOP, bounded history and explicit fault accounting
are part of the wire protocol. Existing v1–v4 operations and v0.61 SCANDIAG
remain available. This release does not qualify 5 or 10 MS/s for v5.

Software power is computed by the companion host recorder from each returned
window. It detects energy, not Starlink identity. The firmware does not yet
provide autonomous FPGA power decisions or offline GLRT.

## Method

`package.py` starts with the published v0.61 DFU whose SHA-256 is pinned in
source. It replaces only installed `usr/sbin/iiod`, `usr/lib/libiio.so.0.25`,
and `opt/VERSIONS`. CPIO entry order, inode/ownership/permission/device metadata,
symlinks, all other file payloads, kernel, FPGA, device trees, FIT timestamps
and configuration properties are preserved. The rootfs integrity hash changes
with its payload. DFU and FRM contain the same FIT body with their respective
validated trailers. This is reproducible component replacement, not a complete
Buildroot rebuild; inherited `/opt/VERSIONS` entries identify inherited bytes.

Run offline tests with:

```sh
python3 -m unittest discover -s scripts/v062 -v
```

Use CMake-installed ARM binaries with no RPATH, from the exact clean source
commit in the release build binding. Pass both installed binary SHA-256 values
to `package.py --help`'s corresponding options. Package twice into separate
directories and compare artifacts. Linux `libfdt`, `readelf`, and Python 3 are
required; tests additionally use `dtc`.

RAM-boot the exact DFU on the explicitly selected development-radio serial via
the public PPU candidate lifecycle. Verify new boot identity, firmware version,
installed file hashes, protocol capabilities, unchanged QSPI, ordinary RX,
ordered complete windows, minimum post-recall guards, segment rotation, STOP,
restoration, and bounded low-level TX2 loopback. Publish the source/build binding
and qualification evidence with the firmware. The parent release's remaining
legacy 10 MS/s scheduled-scan feasibility limitation is not resolved by v5.

The counter guard is an implementation guarantee in the reported counter
domain. It is not a measurement of the minimum physical RF settling interval
or qualification of all target transitions, rates, gains and LNB settings.
