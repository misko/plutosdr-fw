# Continuous multirate firmware v0.63

The v0.62 continuous scanner admitted only 2.5 MS/s and validated each visit
against a hard-coded 50,000-sample count. V0.63 admits 1.25, 2.5, 5, 7.5 and
10 MS/s. Every visit still captures exactly 20 ms on RX1 or simultaneous
RX1/RX2, with a minimum post-recall guard in the source-counter domain.

The matching PPU companion accepts `source_rate_hz` and computes window
geometry, guards and bounded queue bytes from that rate. New clients request
`SCANCAPS5M 96` and reject unadvertised rates before preparation. The original
`SCANCAPS5` response is preserved for existing 2.5 MS/s clients. Firmware alone
does not add rate selectors to a host application's UI. Rates above 10 MS/s
remain outside the continuous contract pending throughput qualification.

`package.py` replaces only installed iiOD, matching libiio and `/opt/VERSIONS`
in the SHA-pinned v0.62 image. Kernel, FPGA, device trees, FIT configurations,
all other rootfs bytes, CPIO order and file metadata are preserved. This is a
reproducible userspace component replacement; the immutable manifest also pins
the future full-build source graph. The shipped component identities retain
their inherited versions for unchanged content.

Run `python3 -m unittest discover -s scripts/v063 -v`. Package two times using
clean source and CMake-installed ARM binaries without RPATH, then compare the
DFU/FRM/binding bytes. `deploy.py` uses the existing exact-serial RAM lifecycle.
`qualify.py` performs bounded RX-only captures and writes IQ after closing the
stream. `verify_iq.py` independently re-reads the saved payloads, hashes,
ordering, sample geometry, guards and restoration receipts. `deploy_lan.py`
requires exact-image RAM, multirate, extended 5/10 MS/s and legacy/ordinary-RX
evidence before invoking the guarded firmware-partition updater.

The counter guard is an implementation guarantee, not a calibration of the
minimum physical settling time. These receive-only tests do not establish RF
identity, Starlink detection sensitivity, every LNB configuration, every
transition, or performance above 10 MS/s.
