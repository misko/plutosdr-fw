# SPF PlutoPlus direct-USB gain metadata

This firmware adds a negotiated 96-byte v2 radio-metadata header before each
finite dual-RX IQ payload sent by the custom USB gadget. The v2 header carries
RX1/RX2 gain in whole dB and RSSI in quarter-dB units at the buffer-associated
start and end observations. Protocol v1's 80-byte raw-index header remains
available for rollback and diagnostics.

The complete gadget source used by this firmware is also vendored directly in
the firmware tree:

```text
third_party/pluto-sdr-usb-gadget/
```

The raw gain-register reads and active gain-table lookup are in
`spf_gain_read.c`. Local RSSI attribute reads are in `spf_rssi_read.c`. The
packed metadata protocol is in `spf_gain_metadata.h`, and `thread_read.c`
constructs one header and copies the IQ payload immediately after it.

The source is published in this repository using separate branches because the
upstream firmware uses independent Git repositories for its Buildroot and USB
gadget:

```text
firmware:
  branch  v0.38_plutoplus_timestamp_gain_metadata

Buildroot snapshot:
  branch  buildroot-gain-metadata
  commit  6d5b0298364dc03ae9fb1c0754b83355960b4d63

USB gadget:
  branch  usb-gadget-gain-metadata
  commit  54610e01c6fd6a69df77f148ea0dc88f9cb18063
```

The Buildroot package pins the gadget commit above. The firmware's `buildroot`
gitlink pins the published Buildroot snapshot, so a recursive checkout does
not require the original development machine's local source override.

The accepted RAM-boot image was:

```text
build/pluto.dfu
SHA-256:
f3cd4d689e7c9ad392edc00eeb6d20da178900fb092eb6afe38a8e003ddbfdf4
```

That image was hardware-tested through a 7,200-frame, one-hour soak before the
source commits were created. The commits capture the tested source content;
rebuilding the clean published commits changes embedded version metadata and
therefore produces a different binary hash.

The numerical gain and RSSI snapshots are buffer-associated ARM observations,
not sample-exact FPGA observations. Raw indices are retained on the Pluto only
for endpoint-change comparison. Equal endpoints do not prove that gain remained
stable throughout the IQ buffer.
