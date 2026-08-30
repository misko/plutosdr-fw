# SDR USB Gadget

This repository implements a simple(ish) daemon which provides a Linux USB Gadget, attempting to perform a high performance interface to transfer IIO buffers.

It was specifically developed for the Analog Adalm Pluto, however could be adapted for other devices utilizing Linux's IIO interface.

Linux AIO and USB Gadget form provide a vendor specific USB interface.

Bulk IN transfers to the interface are queued for transmit via the DAC DMA with the help of its IIO interface.

ADC DMA transfers arriving via the IIO interface are queued for transmission on the USB bulk OUT interface.

## Sample-aligned gain metadata

`spf_gain_timeline` is a transport-independent reducer for the authoritative
FPGA tandem-AGC event stream. It partitions post-change events into half-open
IQ frame intervals, advances pre-frame history, handles 32-bit event-sequence
wrap, and returns a new state only after the complete input validates.

Metadata record version 7 adds `FPGA_GAIN_TIMELINE` and
`FPGA_GAIN_TIMELINE_VALID`. Its gain endpoints and first-change offsets come
from that reducer. SPI gain observations and RSSI are optional diagnostics:
their validity flags report missing telemetry without invalidating IQ or the
FPGA timeline. Metadata versions 1 through 3 and the version 6 base remain
byte-for-byte unchanged.

## Building for testing

Typically this application will be built by buildroot as part of the rootfs build, however for testing it may be useful to build it outside of buildroot, while using the compiler and sysroot prepared by buildroot. Allowing the binary to be pushed to and run on the target.

```
cmake .. -DCMAKE_TOOLCHAIN_FILE=/media/user/Data1/plutosdr-fw/buildroot/output/host/share/buildroot/toolchainfile.cmake -DGENERATE_STATS=ON
```
