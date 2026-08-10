# SDR IP Gadget

This repository implements a simple(ish) daemon which implements a daemon, attempting to perform a high performance interface to transfer IIO buffers via Ethernet using UDP.

It was specifically developed for the Analog Adalm Pluto inspired Pluto+, however could be adapted for other devices utilizing Linux's IIO interface.

The daemon listens on two UDP ports. One for control and another for data.

The control port provides basic services to start / stop streaming on the data port.

Inbound datagrams are received and un-packaged on the data port, reassembled and queued for transmit via the DAC DMA with the help of its IIO interface.

ADC DMA transfers arriving via the IIO interface are broken into datagrams and queued for transmission over the data port.

## SPF finite protocol-v3 receive path

The versioned SPF receive path keeps radio-frame bytes identical to the direct
USB transport. IQ capture and network transmission are deliberately separated:

1. the IIO worker captures each requested finite frame into a preallocated
   frame slot and associates the sample-counter-bracketed gain observations;
2. a bounded FIFO transfers ownership of completed slots to a sender thread;
3. the sender creates MTU-safe UDP fragments and drains them with `sendmmsg`;
4. all requested slots are allocated before DMA starts, so network pacing can
   never make a finite burst overwrite or silently skip an IQ frame.

The normal capability query remains byte-compatible with older hosts. A host
may set `QUERY_TRANSPORT_CAPABILITIES` in a second capability request. New
firmware then advertises `BUFFERED_FINITE_RX` and `USB_CLASS_PACING`; requesting
both flags in `START_RX` selects the 40 MB/s payload profile. An older host sends
no transport flags and retains the conservative 11.36 MB/s profile.

UDP datagrams remain 1,472 bytes by default. Increasing the datagram beyond the
path MTU delegates fragmentation to IP and is not a supported performance
strategy.

## Building for testing

Typically this application will be built by buildroot as part of the rootfs build, however for testing it may be useful to build it outside of buildroot, while using the compiler and sysroot prepared by buildroot. Allowing the binary to be pushed to and run on the target.

```
cmake .. -DCMAKE_TOOLCHAIN_FILE=/media/user/Data1/plutosdr-fw/buildroot/output/host/share/buildroot/toolchainfile.cmake -DGENERATE_STATS=ON
```
