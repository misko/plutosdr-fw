> **STALE — do not read this tree as the current gadget.**
>
> This vendored copy predates protocol v3. It has no `spf_radio_frame_v3.c`, no
> `spf_ip_*` transport, and no `thread_read_v3.c`; its `spf_gain_metadata.h` is
> a v2-era header that happens to define some v3 constants, which makes the
> staleness easy to miss.
>
> The gadget actually built and shipped lives in tags on this repository:
>
> | What | Where |
> | --- | --- |
> | current (RC17, IP transport) | `gain-series-v4-rc17-source/ip-gadget-final-v2` |
> | last USB-transport gadget | `gain-series-v4-rc14-source/gadget` |
> | frame builder + metadata ABI | `gain-series-v4-rc14-source/gadget` |
>
> Extract one with `git archive <tag> | tar -x -C <dir>`. Patches against them
> live in `runtime/integration/`.
>
> Left in place rather than deleted because the build system still references
> this path; correcting that is tracked as a Stage 0 item in
> `tandem_agc_plan.md`.

# SDR USB Gadget

This repository implements a simple(ish) daemon which provides a Linux USB Gadget, attempting to perform a high performance interface to transfer IIO buffers.

It was specifically developed for the Analog Adalm Pluto, however could be adapted for other devices utilizing Linux's IIO interface.

Linux AIO and USB Gadget form provide a vendor specific USB interface.

Bulk IN transfers to the interface are queued for transmit via the DAC DMA with the help of its IIO interface.

ADC DMA transfers arriving via the IIO interface are queued for transmission on the USB bulk OUT interface.

## Building for testing

Typically this application will be built by buildroot as part of the rootfs build, however for testing it may be useful to build it outside of buildroot, while using the compiler and sysroot prepared by buildroot. Allowing the binary to be pushed to and run on the target.

```
cmake .. -DCMAKE_TOOLCHAIN_FILE=/media/user/Data1/plutosdr-fw/buildroot/output/host/share/buildroot/toolchainfile.cmake -DGENERATE_STATS=ON
```
